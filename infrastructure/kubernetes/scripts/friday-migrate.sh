#!/usr/bin/env bash
# friday-migrate.sh — Full fax stack migration from Docker to K8s
#
# Run from Pi as root (or with sudo).
# Requires: kubectl, docker, tailscale
#
# Usage:
#   sudo ./friday-migrate.sh                    # Full migration
#   sudo ./friday-migrate.sh --phase <phase>    # Run specific phase
#   sudo ./friday-migrate.sh --dry-run          # Show plan without executing

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
KC="KUBECONFIG=/etc/rancher/k3s/k3s.yaml kubectl"
REGISTRY="asia-northeast1-docker.pkg.dev/your-gcp-project-id/shinbee"
GCP_PROJECT="your-gcp-project-id"

# WIF credentials for gcloud commands
export CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE="${REPO_ROOT}/Vault/pki/wif-credential-config.json"
export GOOGLE_API_CERTIFICATE_CONFIG="/home/pi/.config/gcloud/certificate_config.json"
DRY_RUN=0
PHASE=""

while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run) DRY_RUN=1; shift ;;
        --phase) PHASE="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

run() {
    echo "  → $*"
    if [ "$DRY_RUN" = "0" ]; then
        eval "$@"
    fi
}

check() {
    echo "  ✓ $1"
}

phase_header() {
    echo ""
    echo "=========================================="
    echo "  $1"
    echo "=========================================="
}


# ==========================================================================
# PRE-FLIGHT CHECKS
# ==========================================================================
preflight() {
    phase_header "PRE-FLIGHT CHECKS"

    echo "Checking kubectl access..."
    run "$KC get nodes -o wide"

    echo ""
    echo "Checking Docker images in AR..."
    for img in asterisk-core asterisk-headless faxapi mail2fax; do
        if gcloud artifacts docker images describe \
            "${REGISTRY}/${img}:latest" \
            --project=your-gcp-project-id &>/dev/null; then
            check "$img:latest exists in AR"
        else
            echo "  ✗ $img:latest NOT FOUND in AR"
            echo "    Build it first: infrastructure/kubernetes/scripts/cloud-build.sh $img"
            exit 1
        fi
    done

    echo ""
    echo "Checking fax-system namespace..."
    run "$KC get namespace fax-system" || {
        echo "Creating fax-system namespace..."
        run "$KC apply -f ${REPO_ROOT}/infrastructure/kubernetes/manifests/fax-system/namespace.yaml"
    }

    echo ""
    echo "Checking fax-system secrets..."
    if eval $KC -n fax-system get secret fax-ami-secret &>/dev/null; then
        check "fax-ami-secret exists"
    else
        echo "  ✗ fax-ami-secret missing"
        echo "    Run: sudo ${SCRIPT_DIR}/render-k8s-secrets.sh fax-system"
        exit 1
    fi

    echo ""
    echo "Creating/updating confgen ConfigMap from file..."
    run "$KC -n fax-system create configmap confgen \
        --from-file=confgen.py=${REPO_ROOT}/services/fax/docker/faxapi/confgen.py \
        --dry-run=client -o yaml | $KC apply -f -"

    echo ""
    echo "Applying static manifests (namespace, PVCs, ConfigMaps, Certificate)..."
    run "$KC apply -f ${REPO_ROOT}/infrastructure/kubernetes/manifests/fax-system/namespace.yaml"
    run "$KC apply -f ${REPO_ROOT}/infrastructure/kubernetes/manifests/fax-system/pvc.yaml"
    run "$KC apply -f ${REPO_ROOT}/infrastructure/kubernetes/manifests/fax-system/configmap-asterisk-data.yaml"
    run "$KC apply -f ${REPO_ROOT}/infrastructure/kubernetes/manifests/fax-system/configmap-hylafax.yaml"
    run "$KC apply -f ${REPO_ROOT}/infrastructure/kubernetes/manifests/fax-system/configmap-mail2fax.yaml"
    run "$KC apply -f ${REPO_ROOT}/infrastructure/kubernetes/manifests/fax-system/certificate-mail2fax.yaml"

    echo ""
    echo "Checking PVCs..."
    run "$KC -n fax-system get pvc"

    echo ""
    echo "Checking MetalLB..."
    if eval $KC get namespace metallb-system &>/dev/null; then
        check "MetalLB installed"
    else
        echo "  ✗ MetalLB not installed"
        echo "    Install: kubectl apply -f https://raw.githubusercontent.com/metallb/metallb/v0.14.9/config/manifests/metallb-native.yaml"
        exit 1
    fi

    check "Pre-flight complete"
}


# ==========================================================================
# PHASE A: WORKERS TO ETHERNET
# ==========================================================================
phase_a() {
    phase_header "PHASE A: WORKERS TO ETHERNET"
    echo "Run worker-to-ethernet.sh on each worker via Tailscale SSH."
    echo "Then add static DHCP leases in MikroTik and label the Asterisk node."
    echo ""
    echo "Commands:"
    echo "  tailscale ssh root@node-a5dd21 < ${SCRIPT_DIR}/worker-to-ethernet.sh"
    echo "  tailscale ssh root@node-d15f51 < ${SCRIPT_DIR}/worker-to-ethernet.sh"
    echo "  sudo $KC label node <asterisk-node> shinbee/workload=asterisk"
    echo ""
    read -p "Press Enter when workers are on Ethernet and labeled..."
    run "$KC get nodes -o wide"
}


# ==========================================================================
# PHASE B: METALLB + SERVICES
# ==========================================================================
phase_b() {
    phase_header "PHASE B: METALLB CONFIGURATION"

    echo "Applying MetalLB IP pool and L2 advertisement..."
    run "$KC apply -f ${REPO_ROOT}/infrastructure/kubernetes/manifests/metallb/ipaddresspool.yaml"
    run "$KC apply -f ${REPO_ROOT}/infrastructure/kubernetes/manifests/metallb/l2advertisement.yaml"

    echo ""
    echo "Applying nginx-ingress LoadBalancer service (VIP 10.0.0.253)..."
    run "$KC apply -f ${REPO_ROOT}/infrastructure/kubernetes/manifests/nginx-ingress-lb-service.yaml"

    echo ""
    echo "Applying phone-provision LoadBalancer service (VIP 10.0.0.251)..."
    run "$KC apply -f ${REPO_ROOT}/infrastructure/kubernetes/manifests/phone-provision/service.yaml"

    echo ""
    echo "Waiting for LoadBalancer IPs..."
    sleep 5
    run "$KC -n ingress-nginx get svc ingress-nginx-lb"
    run "$KC -n shinbee get svc phone-provision"

    echo ""
    echo "Verifying nginx-ingress VIP..."
    if ping -c 2 -W 2 10.0.0.253 &>/dev/null; then
        check "10.0.0.253 (nginx-ingress) reachable"
    else
        echo "  WARNING: 10.0.0.253 not reachable yet"
    fi
}


# ==========================================================================
# PHASE C: MIKROTIK HTTPS/SMTP UPDATES
# ==========================================================================
phase_c() {
    phase_header "PHASE C: MIKROTIK UPDATES (HTTPS/SMTP)"
    echo "Apply MIKROTIC_ADD.rsc on the MikroTik router."
    echo "This updates DNS, HTTPS→253. SMTP stays on 254 (shared VIP with Asterisk)."
    echo "SIP stays at 10.0.0.254 (still Pi for now)."
    echo ""
    echo "File: ${REPO_ROOT}/system/network/MIKROTIC_ADD.rsc"
    echo ""
    read -p "Press Enter when MikroTik rules are applied..."

    echo "Verifying external HTTPS..."
    if curl -sS -o /dev/null -w "%{http_code}" --connect-to portal.your-domain.com:443:10.0.0.253:443 https://portal.your-domain.com/ 2>/dev/null | grep -q "200\|301\|302"; then
        check "HTTPS via 10.0.0.253 works"
    else
        echo "  WARNING: HTTPS check failed (may need DNS propagation)"
    fi
}


# ==========================================================================
# PHASE D: ASTERISK MIGRATION (DOWNTIME)
# ==========================================================================
phase_d() {
    phase_header "PHASE D: ASTERISK MIGRATION (⚠ DOWNTIME STARTS)"

    echo "Step 1: Backup Pi fax data..."
    BACKUP_FILE="/tmp/fax-backup-$(date +%Y%m%d-%H%M%S).tar.gz"
    run "tar czf ${BACKUP_FILE} -C ${REPO_ROOT}/services/fax/data asterisk-etc asterisk-lib asterisk-spool hylafax-spool pbx.db 2>/dev/null || tar czf ${BACKUP_FILE} -C ${REPO_ROOT}/services/fax/data . 2>/dev/null"
    check "Backup: ${BACKUP_FILE}"

    echo ""
    echo "Step 2: Copy backup to Asterisk worker node..."
    ASTERISK_NODE=$(eval $KC get nodes -l shinbee/workload=asterisk -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
    if [ -z "$ASTERISK_NODE" ]; then
        echo "  ERROR: No node labeled shinbee/workload=asterisk"
        echo "  Run: sudo $KC label node <node> shinbee/workload=asterisk"
        exit 1
    fi
    echo "  Asterisk node: $ASTERISK_NODE"
    run "tailscale file cp ${BACKUP_FILE} ${ASTERISK_NODE}:"
    check "Backup copied to $ASTERISK_NODE"

    echo ""
    echo "Step 3: Stop Docker fax stack..."
    run "cd ${REPO_ROOT}/services/fax && sg docker -c 'docker compose stop asterisk-headless faxapi mail2fax'"
    check "Docker fax stack stopped"

    echo ""
    echo "Step 4: Release Pi IP (10.0.0.254)..."
    echo "  ⚠ Pi will only be accessible via Tailscale after this!"
    if [ "$DRY_RUN" = "0" ]; then
        read -p "  Confirm release of 10.0.0.254? [y/N] " confirm
        if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
            echo "  Aborted."
            exit 1
        fi
    fi
    run "ip addr del 10.0.0.254/23 dev eth0 2>/dev/null || true"
    check "Pi IP 10.0.0.254 released"

    echo ""
    echo "Step 5: Apply Asterisk + mail2fax deployments and services..."
    run "$KC apply -f ${REPO_ROOT}/infrastructure/kubernetes/manifests/fax-system/deployment-asterisk.yaml"
    run "$KC apply -f ${REPO_ROOT}/infrastructure/kubernetes/manifests/fax-system/deployment-mail2fax.yaml"
    run "$KC apply -f ${REPO_ROOT}/infrastructure/kubernetes/manifests/fax-system/service-asterisk.yaml"
    run "$KC apply -f ${REPO_ROOT}/infrastructure/kubernetes/manifests/fax-system/service-faxapi-internal.yaml"
    run "$KC apply -f ${REPO_ROOT}/infrastructure/kubernetes/manifests/fax-system/service-mail2fax.yaml"
    check "Deployments and services applied"

    echo ""
    echo "Step 6: Waiting for pods..."
    if [ "$DRY_RUN" = "0" ]; then
        eval $KC -n fax-system rollout status deployment/asterisk --timeout=120s || true
        eval $KC -n fax-system rollout status deployment/mail2fax --timeout=120s || true
        eval $KC -n fax-system get pods -o wide
    fi

    echo ""
    echo "Step 7: Verify Asterisk..."
    if [ "$DRY_RUN" = "0" ]; then
        sleep 5
        eval $KC -n fax-system exec deploy/asterisk -c asterisk -- \
            asterisk -rx "core show uptime" 2>/dev/null && check "Asterisk running" || echo "  WARNING: Asterisk not ready yet"
    fi

    echo ""
    echo "Step 8: Update AI assistant..."
    run "$KC apply -f ${REPO_ROOT}/infrastructure/kubernetes/manifests/ai-assistant/deployment.yaml"
    if [ "$DRY_RUN" = "0" ]; then
        eval $KC -n shinbee rollout status deployment/ai-assistant --timeout=120s || true
    fi
    check "AI assistant updated"

    echo ""
    check "⚠ DOWNTIME ENDS — Verify calls now!"
}


# ==========================================================================
# PHASE E: PI REDUCTION
# ==========================================================================
phase_e() {
    phase_header "PHASE E: PI REDUCTION"

    echo "Step 1: Stop nginx proxy..."
    run "systemctl stop nginx shinbee-proxy-refresh.timer 2>/dev/null || true"
    run "systemctl disable nginx shinbee-proxy-refresh.timer 2>/dev/null || true"
    check "nginx proxy stopped and disabled"

    echo ""
    echo "Step 2: Switch Pi to DHCP (VLAN90 static lease → 10.0.7.100)..."
    run "nmcli con mod 'Wired connection 1' ipv4.method auto ipv4.addresses '' ipv4.gateway '' ipv4.dns '' 2>/dev/null || true"
    check "Pi NM set to DHCP"

    echo ""
    echo "Step 3: Move Pi cable from ether2 → ether4 (VLAN90 admin)."
    echo "  MikroTik static lease gives Pi 10.0.7.100."
    echo "  Tailscale dst-nat already points to 10.0.7.100 (MIKROTIC_ADD.rsc)."
    read -p "Press Enter when cable is moved..."
    check "Pi on VLAN90"
}


# ==========================================================================
# PHASE F: FULL VERIFICATION
# ==========================================================================
phase_f() {
    phase_header "PHASE F: FULL VERIFICATION"

    echo "1. Asterisk status:"
    run "$KC -n fax-system exec deploy/asterisk -c asterisk -- asterisk -rx 'core show uptime'" || true
    run "$KC -n fax-system exec deploy/asterisk -c asterisk -- asterisk -rx 'pjsip show endpoints'" || true

    echo ""
    echo "2. Faxapi health:"
    run "curl -sS http://10.0.0.254:8010/health" || true

    echo ""
    echo "3. MetalLB VIPs:"
    run "$KC get svc -A -o wide | grep LoadBalancer"

    echo ""
    echo "4. All pods:"
    run "$KC -n fax-system get pods -o wide"
    run "$KC -n shinbee get pods -o wide"

    echo ""
    echo "Manual verification checklist:"
    echo "  [ ] Inbound call (NTT → DID → daynight → announcement)"
    echo "  [ ] Outbound call (phone → 9+number → NTT)"
    echo "  [ ] Fax test (email → mail2fax → HylaFAX)"
    echo "  [ ] HTTPS (portal.your-domain.com via 10.0.0.253)"
    echo "  [ ] Phone provisioning (reboot phone → XML fetch)"
    echo "  [ ] AI assistant faxapi connectivity"
    echo ""
    check "Verification phase complete"
}


# ==========================================================================
# PHASE G: SAMBA AD DEPLOYMENT
# ==========================================================================
phase_g() {
    phase_header "PHASE G: SAMBA AD DEPLOYMENT"

    echo "Step 1: Verify samba nodes are labeled..."
    SAMBA_NODES=$(eval $KC get nodes -l shinbee/role=samba -o jsonpath='{.items[*].metadata.name}' 2>/dev/null || true)
    if [ -z "$SAMBA_NODES" ]; then
        echo "  ERROR: No nodes labeled shinbee/role=samba"
        echo "  Run: sudo $KC label node <node1> <node2> <node3> shinbee/role=samba"
        exit 1
    fi
    check "Samba nodes: $SAMBA_NODES"

    echo ""
    echo "Step 2: Check Samba images in AR..."
    for img in samba-ad-dc samba-fileserver google-workspace-sync; do
        if gcloud artifacts docker images describe \
            "${REGISTRY}/${img}:latest" \
            --project="${GCP_PROJECT}" &>/dev/null; then
            check "$img:latest exists in AR"
        else
            echo "  ✗ $img:latest NOT FOUND in AR"
            echo "    Build: infrastructure/kubernetes/scripts/cloud-build.sh $img"
            exit 1
        fi
    done

    echo ""
    echo "Step 3: Check samba-ad-secret exists..."
    if eval $KC -n shinbee get secret samba-ad-secret &>/dev/null; then
        check "samba-ad-secret exists"
    else
        echo "  ✗ samba-ad-secret missing"
        echo "    Run: sudo ${SCRIPT_DIR}/render-k8s-secrets.sh"
        exit 1
    fi

    echo ""
    echo "Step 4: Apply extended MetalLB pool (248-254)..."
    run "$KC apply -f ${REPO_ROOT}/infrastructure/kubernetes/manifests/metallb/ipaddresspool.yaml"

    echo ""
    echo "Step 5: Apply Samba storage classes and PVCs..."
    run "$KC apply -f ${REPO_ROOT}/infrastructure/kubernetes/manifests/samba-ad/storage-classes.yaml"
    run "$KC apply -f ${REPO_ROOT}/infrastructure/kubernetes/manifests/samba-ad/pvc.yaml"
    echo "Waiting for PVCs to bind..."
    if [ "$DRY_RUN" = "0" ]; then
        sleep 10
        eval $KC -n shinbee get pvc | grep samba
    fi

    echo ""
    echo "Step 6: Deploy Samba AD DC..."
    run "$KC apply -f ${REPO_ROOT}/infrastructure/kubernetes/manifests/samba-ad/deployment-dc.yaml"
    run "$KC apply -f ${REPO_ROOT}/infrastructure/kubernetes/manifests/samba-ad/service-dc.yaml"
    if [ "$DRY_RUN" = "0" ]; then
        echo "Waiting for Samba AD DC to start (this may take a few minutes on first boot)..."
        eval $KC -n shinbee rollout status deployment/samba-ad-dc --timeout=300s || true
        sleep 10
    fi

    echo ""
    echo "Step 7: Verify AD DC..."
    if [ "$DRY_RUN" = "0" ]; then
        eval $KC -n shinbee exec deploy/samba-ad-dc -- \
            samba-tool domain level show 2>/dev/null && check "Samba AD DC healthy" || echo "  WARNING: AD DC not ready yet"
    fi

    echo ""
    echo "Step 8: Seed users from ldap-seed.ldif..."
    if [ "$DRY_RUN" = "0" ]; then
        SAMBA_ADMIN_PASSWORD=$(eval $KC -n shinbee get secret samba-ad-secret -o jsonpath='{.data.admin-password}' | base64 -d)
        SAMBA_ADMIN_PASSWORD="$SAMBA_ADMIN_PASSWORD" python3 "${REPO_ROOT}/infrastructure/kubernetes/scripts/seed-samba-users.py" \
            --ldap-url "ldap://10.0.0.250:389" \
            --ldif "${REPO_ROOT}/services/phone-provisioning/ldap-seed.ldif" || echo "  WARNING: User seeding had errors"
    fi

    echo ""
    echo "Step 9: Deploy Samba file server..."
    run "$KC apply -f ${REPO_ROOT}/infrastructure/kubernetes/manifests/samba-ad/deployment-fileserver.yaml"
    run "$KC apply -f ${REPO_ROOT}/infrastructure/kubernetes/manifests/samba-ad/service-fileserver.yaml"
    if [ "$DRY_RUN" = "0" ]; then
        echo "Waiting for file server to join domain..."
        eval $KC -n shinbee rollout status deployment/samba-fileserver --timeout=300s || true
    fi

    echo ""
    echo "Step 10: Verify file server..."
    if [ "$DRY_RUN" = "0" ]; then
        eval $KC -n shinbee exec deploy/samba-fileserver -- wbinfo -t 2>/dev/null && \
            check "File server domain trust OK" || echo "  WARNING: Domain trust check failed"
    fi

    echo ""
    echo "Step 11: Deploy Google Workspace sync CronJob..."
    run "$KC apply -f ${REPO_ROOT}/infrastructure/kubernetes/manifests/samba-ad/cronjob-workspace-sync.yaml"

    echo ""
    echo "Step 12: Run initial Workspace sync..."
    if [ "$DRY_RUN" = "0" ]; then
        eval $KC -n shinbee create job --from=cronjob/google-workspace-sync workspace-sync-initial 2>/dev/null || true
        echo "  Sync job started. Check: sudo $KC -n shinbee logs job/workspace-sync-initial"
    fi

    echo ""
    echo "Step 13: Apply MikroTik Samba config..."
    echo "  File: ${REPO_ROOT}/system/network/MIKROTIK_SAMBA_ADD.rsc"
    read -p "Press Enter when MikroTik rules are applied..."

    check "Phase G complete — Samba AD deployed"
}


# ==========================================================================
# PHASE H: OPENLDAP CUTOVER
# ==========================================================================
phase_h() {
    phase_header "PHASE H: OPENLDAP → SAMBA AD CUTOVER"

    echo "Step 1: Update AI assistant deployment (LDAP → Samba AD)..."
    run "$KC apply -f ${REPO_ROOT}/infrastructure/kubernetes/manifests/ai-assistant/deployment.yaml"
    if [ "$DRY_RUN" = "0" ]; then
        eval $KC -n shinbee rollout status deployment/ai-assistant --timeout=120s || true
    fi
    check "AI assistant updated for Samba AD"

    echo ""
    echo "Step 2: Regenerate phone provisioning XMLs..."
    if [ "$DRY_RUN" = "0" ]; then
        cd "${REPO_ROOT}"
        python3 services/phone-provisioning/generate.py
        cd infrastructure/kubernetes/manifests/phone-provision && bash create-files-configmap.sh && cd "${REPO_ROOT}"
        echo "  ConfigMap updated. Phones will pick up new LDAP config on next reboot."
    fi
    check "Phone provisioning XMLs regenerated"

    echo ""
    echo "Step 3: Verify phone LDAP phonebook..."
    if [ "$DRY_RUN" = "0" ]; then
        eval $KC -n shinbee exec deploy/samba-ad-dc -- \
            samba-tool user list 2>/dev/null | head -20 || echo "  WARNING: Could not list AD users"
    fi

    echo ""
    echo "Step 4: Scale OpenLDAP to 0 (keep manifests for rollback)..."
    if [ "$DRY_RUN" = "0" ]; then
        if eval $KC -n shinbee get deploy/openldap &>/dev/null; then
            run "$KC -n shinbee scale deploy/openldap --replicas=0"
            check "OpenLDAP scaled to 0"
        else
            check "OpenLDAP deployment not found (already removed or in different namespace)"
        fi
    fi

    echo ""
    echo "Manual verification:"
    echo "  [ ] Phone LDAP phonebook works (reboot one phone, check directory)"
    echo "  [ ] AI assistant auto-provision creates AD users"
    echo "  [ ] smbclient //10.0.0.249/profiles -U Administrator"
    echo "  [ ] smbclient //10.0.0.249/shared -U Administrator"
    echo ""
    check "Phase H complete — OpenLDAP cutover done"
}


# ==========================================================================
# MAIN
# ==========================================================================
echo "========================================"
echo "  SHINBEE Friday Migration"
echo "  $(date)"
echo "  Dry run: $DRY_RUN"
echo "========================================"

if [ -n "$PHASE" ]; then
    case "$PHASE" in
        preflight) preflight ;;
        a|A) phase_a ;;
        b|B) phase_b ;;
        c|C) phase_c ;;
        d|D) phase_d ;;
        e|E) phase_e ;;
        f|F) phase_f ;;
        g|G) phase_g ;;
        h|H) phase_h ;;
        *) echo "Unknown phase: $PHASE"; exit 1 ;;
    esac
else
    preflight
    phase_a
    phase_b
    phase_c
    phase_d
    phase_e
    phase_f
    phase_g
    phase_h
fi

echo ""
echo "========================================"
echo "  Migration complete!"
echo "========================================"
