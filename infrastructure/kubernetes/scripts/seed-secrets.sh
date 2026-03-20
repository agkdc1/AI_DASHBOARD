#!/usr/bin/env bash
# seed-secrets.sh — One-time migration: Vault KV v2 → GCP Secret Manager
#
# Reads all application secrets from Vault and writes them as JSON payloads
# into GCP Secret Manager. Run once during Phase 5 cutover.
#
# Prerequisites:
#   - Vault running and unsealed
#   - Admin AppRole credentials in /root/vault-approle-admin-{role-id,secret-id}
#   - GCP SM secrets created by Terraform (secrets.tf)
#   - gcloud auth via WIF or service account
#
# Usage: sudo ./seed-secrets.sh [--dry-run]

set -euo pipefail

DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

VAULT_ADDR="${VAULT_ADDR:-http://127.0.0.1:8200}"
GCP_PROJECT="your-gcp-project-id"

# ---------- Vault → GCP SM mapping ----------
# Format: "vault_path:gsm_secret_id"
MAPPINGS=(
    "admin/aws:admin-aws"
    "daemon/sagawa:daemon-sagawa"
    "daemon/yamato:daemon-yamato"
    "shinbee_japan_fax/ami:fax-ami"
    "shinbee_japan_fax/aws:fax-aws"
    "shinbee_japan_fax/db:fax-db"
    "shinbee_japan_fax/fax:fax-api-key"
    "shinbee_japan_fax/smtp:fax-smtp"
    "shinbee_japan_fax/smtp_relay:fax-smtp-relay"
    "shinbee_japan_fax/switch:fax-switch"
    "shinbee_japan_fax/terraform:fax-terraform"
    "shinbeeinventree/aws:inventree-aws"
    "shinbeeinventree/db:inventree-db"
    "shinbeeinventree/oauth:inventree-oauth"
    "system/backup:system-backup"
    "system/gcp/fax_terraform_sa:system-gcp-terraform"
)

# ---------- Authenticate to Vault ----------
echo "Authenticating to Vault..."
ROLE_ID=$(cat /root/vault-approle-admin-role-id)
SECRET_ID=$(cat /root/vault-approle-admin-secret-id)
VAULT_TOKEN=$(curl -sf "${VAULT_ADDR}/v1/auth/approle/login" \
    -d "{\"role_id\":\"${ROLE_ID}\",\"secret_id\":\"${SECRET_ID}\"}" \
    | python3 -c "import sys,json;print(json.load(sys.stdin)['auth']['client_token'])")

if [ -z "${VAULT_TOKEN}" ] || [ "${VAULT_TOKEN}" = "null" ]; then
    echo "ERROR: Failed to authenticate to Vault"
    exit 1
fi
echo "Vault authenticated"

# ---------- Verify gcloud auth ----------
echo "Verifying GCP access..."
if ! gcloud secrets list --project="${GCP_PROJECT}" --limit=1 &>/dev/null; then
    echo "ERROR: Cannot access GCP Secret Manager. Check gcloud auth."
    exit 1
fi
echo "GCP access verified"

# ---------- Seed each secret ----------
ERRORS=0
for mapping in "${MAPPINGS[@]}"; do
    vault_path="${mapping%%:*}"
    gsm_id="${mapping##*:}"

    echo -n "  ${vault_path} → ${gsm_id} ... "

    # Read from Vault KV v2
    JSON=$(curl -sf -H "X-Vault-Token: ${VAULT_TOKEN}" \
        "${VAULT_ADDR}/v1/secret/data/${vault_path}" \
        | python3 -c "import sys,json;print(json.dumps(json.load(sys.stdin)['data']['data']))" 2>/dev/null)

    if [ -z "${JSON}" ] || [ "${JSON}" = "null" ]; then
        echo "SKIP (not found in Vault)"
        continue
    fi

    if $DRY_RUN; then
        echo "OK (dry-run, $(echo "${JSON}" | wc -c) bytes)"
        continue
    fi

    # Write to GCP SM as new version
    if echo "${JSON}" | gcloud secrets versions add "${gsm_id}" \
        --project="${GCP_PROJECT}" --data-file=- 2>/dev/null; then
        echo "OK"
    else
        echo "FAILED"
        ERRORS=$((ERRORS + 1))
    fi
done

# ---------- Cleanup ----------
echo ""
echo "Revoking Vault token..."
curl -sf -X POST -H "X-Vault-Token: ${VAULT_TOKEN}" \
    "${VAULT_ADDR}/v1/auth/token/revoke-self" &>/dev/null || true

if [ ${ERRORS} -gt 0 ]; then
    echo "WARNING: ${ERRORS} secret(s) failed to seed"
    exit 1
fi

echo "All secrets seeded successfully"
$DRY_RUN && echo "(dry-run mode — no secrets were actually written)"
