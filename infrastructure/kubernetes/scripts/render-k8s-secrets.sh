#!/usr/bin/env bash
# render-k8s-secrets.sh — Fetch secrets from GCP Secret Manager and create K8s Secrets
#
# Usage: sudo ./render-k8s-secrets.sh [namespace]
# Default namespace: shinbee
#
# Requires: kubectl, gcloud, python3, sudo
# Auth: GCP WIF X.509 mTLS (certs at Vault/pki/)

set -euo pipefail

NAMESPACE="${1:-shinbee}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
GCP_PROJECT="your-gcp-project-id"

# WIF credentials
export CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE="${REPO_ROOT}/Vault/pki/wif-credential-config.json"
export GOOGLE_API_CERTIFICATE_CONFIG="/home/pi/.config/gcloud/certificate_config.json"

echo "=== Rendering K8s secrets from GCP Secret Manager into namespace '${NAMESPACE}' ==="

gsm_get() {
    local secret_id="$1" field="$2"
    local json value
    json=$(gcloud secrets versions access latest \
        --secret="${secret_id}" --project="${GCP_PROJECT}" 2>/dev/null)
    value=$(echo "${json}" | python3 -c "import sys,json;print(json.load(sys.stdin)['${field}'])" 2>/dev/null)
    if [ -z "${value}" ] || [ "${value}" = "None" ]; then
        echo "ERROR: Failed to read ${secret_id}/${field}" >&2
        exit 1
    fi
    echo "${value}"
}

# Verify GCP access
echo "Verifying GCP Secret Manager access..."
gcloud secrets list --project="${GCP_PROJECT}" --limit=1 &>/dev/null || {
    echo "ERROR: Cannot access GCP Secret Manager"
    exit 1
}

# Ensure namespace exists
sudo KUBECONFIG=/etc/rancher/k3s/k3s.yaml kubectl get namespace "${NAMESPACE}" &>/dev/null || \
    sudo KUBECONFIG=/etc/rancher/k3s/k3s.yaml kubectl create namespace "${NAMESPACE}"

KC="sudo KUBECONFIG=/etc/rancher/k3s/k3s.yaml kubectl"

# ---------- InvenTree DB secret ----------
echo "Creating inventree-db-secret..."
MYSQL_PASSWORD=$(gsm_get "inventree-db" "mysql_password")
eval $KC -n "${NAMESPACE}" create secret generic inventree-db-secret \
    --from-literal=mysql-password="${MYSQL_PASSWORD}" \
    --from-literal=mysql-root-password="${MYSQL_PASSWORD}" \
    --dry-run=client -o yaml | eval $KC apply -f -

# ---------- Authentik OIDC credentials ----------
# Each service has its own Authentik OAuth2 provider (stored in authentik-oidc-clients GSM secret).
echo "Reading Authentik OIDC client configs..."
OIDC_JSON=$(gsm_get_json "authentik-oidc-clients")
INVENTREE_OIDC_ID=$(echo "$OIDC_JSON" | python3 -c "import json,sys; print(json.load(sys.stdin)['inventree']['client_id'])")
INVENTREE_OIDC_SECRET=$(echo "$OIDC_JSON" | python3 -c "import json,sys; print(json.load(sys.stdin)['inventree']['client_secret'])")
VIKUNJA_OIDC_ID=$(echo "$OIDC_JSON" | python3 -c "import json,sys; print(json.load(sys.stdin)['vikunja']['client_id'])")
VIKUNJA_OIDC_SECRET=$(echo "$OIDC_JSON" | python3 -c "import json,sys; print(json.load(sys.stdin)['vikunja']['client_secret'])")
OUTLINE_OIDC_ID=$(echo "$OIDC_JSON" | python3 -c "import json,sys; print(json.load(sys.stdin)['outline']['client_id'])")
OUTLINE_OIDC_SECRET=$(echo "$OIDC_JSON" | python3 -c "import json,sys; print(json.load(sys.stdin)['outline']['client_secret'])")

# ---------- InvenTree OAuth secret ----------
echo "Creating inventree-oauth-secret (Authentik OIDC)..."
eval $KC -n "${NAMESPACE}" create secret generic inventree-oauth-secret \
    --from-literal=oidc-client-id="${INVENTREE_OIDC_ID}" \
    --from-literal=oidc-client-secret="${INVENTREE_OIDC_SECRET}" \
    --dry-run=client -o yaml | eval $KC apply -f -

# ---------- InvenTree AWS secret ----------
echo "Creating inventree-aws-secret..."
INV_AWS_KEY=$(gsm_get "inventree-aws" "access_key_id")
INV_AWS_SECRET=$(gsm_get "inventree-aws" "secret_access_key")
eval $KC -n "${NAMESPACE}" create secret generic inventree-aws-secret \
    --from-literal=aws-access-key-id="${INV_AWS_KEY}" \
    --from-literal=aws-secret-access-key="${INV_AWS_SECRET}" \
    --dry-run=client -o yaml | eval $KC apply -f -

# ---------- Selenium daemon credentials (from GCP SM) ----------
echo "Creating selenium-daemon-secrets..."
SAGAWA_USER=$(gsm_get "daemon-sagawa" "user_id")
SAGAWA_PASS=$(gsm_get "daemon-sagawa" "password")
YAMATO_ID=$(gsm_get "daemon-yamato" "login_id")
YAMATO_PASS=$(gsm_get "daemon-yamato" "password")
eval $KC -n "${NAMESPACE}" create secret generic selenium-daemon-secret \
    --from-literal=sagawa-user-id="${SAGAWA_USER}" \
    --from-literal=sagawa-password="${SAGAWA_PASS}" \
    --from-literal=yamato-login-id="${YAMATO_ID}" \
    --from-literal=yamato-password="${YAMATO_PASS}" \
    --dry-run=client -o yaml | eval $KC apply -f -

# ---------- WIF credentials (for workloads needing GCP access) ----------
echo "Creating wif-secret..."
CERT_CONFIG_TMP=$(mktemp)
cat > "${CERT_CONFIG_TMP}" << 'CERTCFG'
{
  "cert_configs": {
    "workload": {
      "cert_path": "/app/Vault/pki/client.crt",
      "key_path": "/app/Vault/pki/client.key"
    }
  }
}
CERTCFG
eval $KC -n "${NAMESPACE}" create secret generic wif-secret \
    --from-file=wif-credential-config.json="${REPO_ROOT}/Vault/pki/wif-credential-config.json" \
    --from-file=client.crt="${REPO_ROOT}/Vault/pki/client.crt" \
    --from-file=client.key="${REPO_ROOT}/Vault/pki/client.key" \
    --from-file=ca.crt="${REPO_ROOT}/Vault/pki/ca.crt" \
    --from-file=certificate_config.json="${CERT_CONFIG_TMP}" \
    --dry-run=client -o yaml | eval $KC apply -f -
rm -f "${CERT_CONFIG_TMP}"

# Keep legacy names as copies for backward compatibility during transition
eval $KC -n "${NAMESPACE}" get secret wif-secret -o yaml \
    | sed 's/name: wif-secret/name: selenium-wif-secret/' \
    | grep -v 'uid:\|resourceVersion:\|creationTimestamp:' \
    | eval $KC apply -f -
eval $KC -n "${NAMESPACE}" get secret wif-secret -o yaml \
    | sed 's/name: wif-secret/name: rakuten-wif-secret/' \
    | grep -v 'uid:\|resourceVersion:\|creationTimestamp:' \
    | eval $KC apply -f -

# ---------- Cloud DNS credentials for cert-manager ----------
echo "Creating clouddns-credentials..."
CERT_MANAGER_KEY=$(gcloud secrets versions access latest \
    --secret=cert-manager-dns-key --project="${GCP_PROJECT}")
echo "$CERT_MANAGER_KEY" > /tmp/clouddns-key.json
eval $KC -n "${NAMESPACE}" create secret generic clouddns-credentials \
    --from-file=key.json=/tmp/clouddns-key.json \
    --dry-run=client -o yaml | eval $KC apply -f -

if eval $KC get namespace cert-manager &>/dev/null; then
    echo "Creating clouddns-credentials in cert-manager namespace..."
    eval $KC -n cert-manager create secret generic clouddns-credentials \
        --from-file=key.json=/tmp/clouddns-key.json \
        --dry-run=client -o yaml | eval $KC apply -f -
fi
rm -f /tmp/clouddns-key.json

# ---------- Backup GCS credentials ----------
echo "Creating backup-gcs-secret..."
K8S_BACKUP_KEY=$(gcloud secrets versions access latest \
    --secret=k8s-backup-key --project="${GCP_PROJECT}")
echo "$K8S_BACKUP_KEY" > /tmp/gcs-backup-key.json
eval $KC -n "${NAMESPACE}" create secret generic backup-gcs-secret \
    --from-file=key.json=/tmp/gcs-backup-key.json \
    --dry-run=client -o yaml | eval $KC apply -f -
rm -f /tmp/gcs-backup-key.json

# ---------- Backup encryption password ----------
echo "Creating backup-encryption-secret..."
BACKUP_ENC_PW=$(gsm_get "system-backup" "encryption_password")
eval $KC -n "${NAMESPACE}" create secret generic backup-encryption-secret \
    --from-literal=encryption-password="${BACKUP_ENC_PW}" \
    --dry-run=client -o yaml | eval $KC apply -f -

# ---------- AI Assistant GCS credentials ----------
echo "Creating ai-assistant-gcs-secret..."
AI_KEY=$(gcloud secrets versions access latest \
    --secret=ai-assistant-key --project="${GCP_PROJECT}")
echo "$AI_KEY" > /tmp/ai-assistant-key.json
eval $KC -n "${NAMESPACE}" create secret generic ai-assistant-gcs-secret \
    --from-file=key.json=/tmp/ai-assistant-key.json \
    --dry-run=client -o yaml | eval $KC apply -f -
rm -f /tmp/ai-assistant-key.json

# ---------- GSPS (Password Sync) SA key ----------
echo "Creating gsps-sa-key..."
GSPS_KEY=$(gcloud secrets versions access latest \
    --secret=gsps-sa-key --project="${GCP_PROJECT}")
echo "$GSPS_KEY" > /tmp/gsps-sa-key.json
eval $KC -n "${NAMESPACE}" create secret generic gsps-sa-key \
    --from-file=key.json=/tmp/gsps-sa-key.json \
    --dry-run=client -o yaml | eval $KC apply -f -
rm -f /tmp/gsps-sa-key.json

# ---------- Samba AD secret ----------
echo "Creating samba-ad-secret..."
SAMBA_ADMIN_PW=$(gsm_get "samba-ad" "admin_password")
eval $KC -n "${NAMESPACE}" create secret generic samba-ad-secret \
    --from-literal=admin-password="${SAMBA_ADMIN_PW}" \
    --dry-run=client -o yaml | eval $KC apply -f -

# ---------- Google Admin SDK secret ----------
echo "Creating google-admin-sdk-secret..."
GOOGLE_ADMIN_SDK_KEY=$(gcloud secrets versions access latest \
    --secret=google-admin-sdk --project="${GCP_PROJECT}")
echo "$GOOGLE_ADMIN_SDK_KEY" > /tmp/google-admin-sdk-key.json
eval $KC -n "${NAMESPACE}" create secret generic google-admin-sdk-secret \
    --from-file=key.json=/tmp/google-admin-sdk-key.json \
    --dry-run=client -o yaml | eval $KC apply -f -
rm -f /tmp/google-admin-sdk-key.json

# ---------- Central config.yaml as ConfigMap ----------
echo "Creating shinbee-config ConfigMap..."
eval $KC -n "${NAMESPACE}" create configmap shinbee-config \
    --from-file=config.yaml="${REPO_ROOT}/config.yaml" \
    --dry-run=client -o yaml | eval $KC apply -f -

# ---------- Intranet namespace secrets ----------
if [ "${NAMESPACE}" = "intranet" ] || [ "${NAMESPACE}" = "all" ]; then
    INTRANET_NS="intranet"
    eval $KC get namespace "${INTRANET_NS}" &>/dev/null || eval $KC create namespace "${INTRANET_NS}"

    echo ""
    echo "=== Rendering intranet secrets ==="

    echo "Creating intranet-db-secret..."
    PG_VIKUNJA_PW=$(gsm_get "intranet-db" "vikunja_password")
    PG_OUTLINE_PW=$(gsm_get "intranet-db" "outline_password")
    eval $KC -n "${INTRANET_NS}" create secret generic intranet-db-secret \
        --from-literal=vikunja-password="${PG_VIKUNJA_PW}" \
        --from-literal=outline-password="${PG_OUTLINE_PW}" \
        --dry-run=client -o yaml | eval $KC apply -f -

    # Authentik OIDC credentials (read earlier from authentik-oidc-clients)
    echo "Creating vikunja-oauth-secret (Authentik OIDC)..."
    eval $KC -n "${INTRANET_NS}" create secret generic vikunja-oauth-secret \
        --from-literal=client-id="${VIKUNJA_OIDC_ID}" \
        --from-literal=client-secret="${VIKUNJA_OIDC_SECRET}" \
        --dry-run=client -o yaml | eval $KC apply -f -

    echo "Creating outline-oauth-secret (Authentik OIDC)..."
    eval $KC -n "${INTRANET_NS}" create secret generic outline-oauth-secret \
        --from-literal=client-id="${OUTLINE_OIDC_ID}" \
        --from-literal=client-secret="${OUTLINE_OIDC_SECRET}" \
        --dry-run=client -o yaml | eval $KC apply -f -

    echo "Creating outline-app-secret..."
    OUT_SECRET_KEY=$(gsm_get "intranet-outline" "secret_key")
    OUT_UTILS_SECRET=$(gsm_get "intranet-outline" "utils_secret")
    eval $KC -n "${INTRANET_NS}" create secret generic outline-app-secret \
        --from-literal=secret-key="${OUT_SECRET_KEY}" \
        --from-literal=utils-secret="${OUT_UTILS_SECRET}" \
        --dry-run=client -o yaml | eval $KC apply -f -

    echo "Creating outline-db-url secret..."
    OUTLINE_DB_URL="postgres://outline:${PG_OUTLINE_PW}@intranet-db.intranet.svc.cluster.local:5432/outline?sslmode=disable"
    eval $KC -n "${INTRANET_NS}" create secret generic outline-db-url \
        --from-literal=url="${OUTLINE_DB_URL}" \
        --dry-run=client -o yaml | eval $KC apply -f -

    echo "Creating minio-secret..."
    MINIO_ACCESS=$(gsm_get "intranet-minio" "access_key")
    MINIO_SECRET=$(gsm_get "intranet-minio" "secret_key")
    eval $KC -n "${INTRANET_NS}" create secret generic minio-secret \
        --from-literal=access-key="${MINIO_ACCESS}" \
        --from-literal=secret-key="${MINIO_SECRET}" \
        --dry-run=client -o yaml | eval $KC apply -f -

    echo ""
    echo "Intranet secrets:"
    eval $KC -n "${INTRANET_NS}" get secrets --no-headers | awk '{print "  - " $1}'
fi

# ---------- Fax system namespace secrets ----------
if [ "${NAMESPACE}" = "fax-system" ] || [ "${NAMESPACE}" = "all" ]; then
    FAX_NS="fax-system"
    eval $KC get namespace "${FAX_NS}" &>/dev/null || eval $KC create namespace "${FAX_NS}"

    echo ""
    echo "=== Rendering fax-system secrets ==="

    echo "Creating fax-ami-secret..."
    AMI_USERNAME=$(gsm_get "fax-ami" "username")
    AMI_SECRET=$(gsm_get "fax-ami" "secret")
    eval $KC -n "${FAX_NS}" create secret generic fax-ami-secret \
        --from-literal=ami-username="${AMI_USERNAME}" \
        --from-literal=ami-secret="${AMI_SECRET}" \
        --dry-run=client -o yaml | eval $KC apply -f -

    echo "Creating fax-api-key-secret..."
    FAX_API_KEY=$(gsm_get "fax-api-key" "api_key")
    eval $KC -n "${FAX_NS}" create secret generic fax-api-key-secret \
        --from-literal=api-key="${FAX_API_KEY}" \
        --dry-run=client -o yaml | eval $KC apply -f -

    echo "Creating mail2fax-secret..."
    SMTP_AUTH_USER=$(gsm_get "fax-smtp" "username")
    SMTP_AUTH_PASS=$(gsm_get "fax-smtp" "password")
    RELAY_HOST="smtp.gmail.com"
    RELAY_PORT="587"
    RELAY_USER=$(gsm_get "fax-smtp-relay" "username")
    RELAY_PASS=$(gsm_get "fax-smtp-relay" "password")
    eval $KC -n "${FAX_NS}" create secret generic mail2fax-secret \
        --from-literal=fax-api-key="${FAX_API_KEY}" \
        --from-literal=smtp-auth-user="${SMTP_AUTH_USER}" \
        --from-literal=smtp-auth-pass="${SMTP_AUTH_PASS}" \
        --from-literal=relay-host="${RELAY_HOST}" \
        --from-literal=relay-port="${RELAY_PORT}" \
        --from-literal=relay-user="${RELAY_USER}" \
        --from-literal=relay-pass="${RELAY_PASS}" \
        --dry-run=client -o yaml | eval $KC apply -f -

    echo "Creating og810xi-secret..."
    OG810XI_CREDS=$(gcloud secrets versions access latest \
        --secret=og810xi-credentials --project="${GCP_PROJECT}")
    OG810XI_USER=$(echo "$OG810XI_CREDS" | python3 -c "import sys,json; print(json.load(sys.stdin)['username'])")
    OG810XI_PASS=$(echo "$OG810XI_CREDS" | python3 -c "import sys,json; print(json.load(sys.stdin)['password'])")
    eval $KC -n "${FAX_NS}" create secret generic og810xi-secret \
        --from-literal=username="${OG810XI_USER}" \
        --from-literal=password="${OG810XI_PASS}" \
        --dry-run=client -o yaml | eval $KC apply -f -

    echo "Creating clouddns-credentials in fax-system namespace..."
    CERT_MANAGER_KEY_FAX=$(gcloud secrets versions access latest \
        --secret=cert-manager-dns-key --project="${GCP_PROJECT}")
    echo "$CERT_MANAGER_KEY_FAX" > /tmp/clouddns-key-fax.json
    eval $KC -n "${FAX_NS}" create secret generic clouddns-credentials \
        --from-file=key.json=/tmp/clouddns-key-fax.json \
        --dry-run=client -o yaml | eval $KC apply -f -
    rm -f /tmp/clouddns-key-fax.json

    echo ""
    echo "Fax-system secrets:"
    eval $KC -n "${FAX_NS}" get secrets --no-headers | awk '{print "  - " $1}'
fi

echo ""
echo "=== All K8s secrets created/updated ==="
echo ""
if [ "${NAMESPACE}" != "intranet" ] && [ "${NAMESPACE}" != "fax-system" ]; then
    echo "Secrets in ${NAMESPACE}:"
    eval $KC -n "${NAMESPACE}" get secrets --no-headers | awk '{print "  - " $1}'
fi
