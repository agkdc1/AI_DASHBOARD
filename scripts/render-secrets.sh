#!/usr/bin/env bash
# =============================================================================
# render-secrets.sh — Fetch secrets from GCP Secret Manager and render them
#                     into local .env files and config files for each service.
#
# This replaces the old Vault-based approach. All application secrets are now
# stored in GCP Secret Manager. Only a single GCP credential (WIF X.509 mTLS
# certificate or service account key) is needed to deploy any service.
#
# The script fetches secrets and renders them to:
#   - .env files for docker-compose services (fax, inventory, etc.)
#   - Secret files for Docker secrets (mysql_password, oauth credentials)
#   - K8s secret manifests (delegated to render-k8s-secrets.sh)
#
# Usage:
#   ./render-secrets.sh [OPTIONS] [SERVICE...]
#
# Options:
#   --dry-run       Show what would be rendered without writing files
#   --project ID    Override GCP project ID
#   --help          Show this help message
#
# Services:
#   fax             Fax system (Asterisk, faxapi, mail2fax)
#   inventory       InvenTree (DB, OAuth, AWS)
#   selenium-daemon Carrier portal automation (Sagawa, Yamato)
#   rakuten-renewal Rakuten mobile renewal agent
#   ai-assistant    AI assistant (Gemini, Vikunja, LDAP)
#   kubernetes      K8s secrets (delegates to render-k8s-secrets.sh)
#   all             All services (default)
#
# Prerequisites:
#   - gcloud CLI installed and authenticated
#   - WIF credential config at Vault/pki/wif-credential-config.json
#     OR gcloud auth login / application-default credentials
#   - yq (https://github.com/mikefarah/yq) for reading config.yaml
#
# =============================================================================
#
# GCP SECRET MANAGER — COMPLETE SECRET INVENTORY
# -----------------------------------------------
# These secrets must exist in GCP SM (created by Terraform in secrets.tf).
# Each secret stores a JSON payload with the fields listed below.
#
# --- Fax system ---
#   fax-ami               {"username": "...", "secret": "..."}
#   fax-api-key           {"api_key": "..."}
#   fax-db                {"mysql_root_password": "...", "mysql_password": "...",
#                          "mysql_user": "...", "mysql_database": "..."}
#   fax-smtp              {"username": "...", "password": "..."}
#   fax-smtp-relay        {"username": "...", "password": "..."}
#   fax-aws               {"access_key_id": "...", "secret_access_key": "...",
#                          "hosted_zone_id": "..."}
#   fax-switch            {"username": "...", "password": "..."}
#   og810xi-credentials   {"username": "...", "password": "..."}
#
# --- Inventory (InvenTree) ---
#   inventree-db          {"mysql_password": "..."}
#   inventree-oauth       {"client_id": "...", "client_secret": "..."}
#   inventree-aws         {"access_key_id": "...", "secret_access_key": "..."}
#
# --- Selenium daemon ---
#   daemon-sagawa         {"user_id": "...", "password": "..."}
#   daemon-yamato         {"login_id": "...", "password": "..."}
#
# --- Rakuten renewal ---
#   (Uses Vault AppRole during transition; secrets read at runtime via GCP SM)
#
# --- AI assistant ---
#   ai-assistant-key      SA key JSON (service account for GCS/Gemini)
#   gsps-sa-key           SA key JSON (Google Password Sync)
#   samba-ad              {"admin_password": "..."}
#
# --- Authentik OIDC ---
#   authentik-oidc-clients {"inventree": {"client_id": "...", "client_secret": "..."},
#                           "vikunja":   {"client_id": "...", "client_secret": "..."},
#                           "outline":   {"client_id": "...", "client_secret": "..."}}
#
# --- Intranet ---
#   intranet-db           {"vikunja_password": "...", "outline_password": "..."}
#   intranet-outline      {"secret_key": "...", "utils_secret": "..."}
#   intranet-minio        {"access_key": "...", "secret_key": "..."}
#
# --- System / infrastructure ---
#   system-backup         {"encryption_password": "..."}
#   cert-manager-dns-key  SA key JSON (Cloud DNS for ACME DNS-01)
#   k8s-backup-key        SA key JSON (GCS backup uploads)
#   google-admin-sdk      SA key JSON (Google Workspace directory sync)
#   admin-aws             {"access_key_id": "...", "secret_access_key": "..."}
#   system-gcp-terraform  SA key JSON (Terraform deployer)
#   k3s-tailscale-authkey Tailscale auth key (plain text)
#
# =============================================================================

set -euo pipefail

# ---------- Defaults ----------
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
GCP_PROJECT="${GCP_PROJECT_ID:-your-gcp-project-id}"
DRY_RUN=false
SERVICES=()

# WIF credential paths (X.509 mTLS)
WIF_CREDENTIAL_CONFIG="${REPO_ROOT}/Vault/pki/wif-credential-config.json"
CERT_CONFIG="${HOME}/.config/gcloud/certificate_config.json"

# ---------- Colors ----------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# ---------- Parse arguments ----------
usage() {
    sed -n '2,/^# =====/p' "$0" | grep '^#' | sed 's/^# \?//'
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)  DRY_RUN=true; shift ;;
        --project)  GCP_PROJECT="$2"; shift 2 ;;
        --help|-h)  usage ;;
        -*)         echo "Unknown option: $1" >&2; exit 1 ;;
        *)          SERVICES+=("$1"); shift ;;
    esac
done

# Default to all services
if [[ ${#SERVICES[@]} -eq 0 ]]; then
    SERVICES=("all")
fi

# ---------- Helper functions ----------

log_info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
log_ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# Fetch a raw secret value from GCP Secret Manager
gsm_get() {
    gcloud secrets versions access latest --secret="$1" --project="${GCP_PROJECT}" 2>/dev/null
}

# Fetch a specific field from a JSON secret in GCP Secret Manager
gsm_get_field() {
    local secret_id="$1" field="$2"
    local json value
    json=$(gsm_get "${secret_id}")
    if [[ -z "${json}" ]]; then
        log_error "Failed to fetch secret '${secret_id}' from GCP SM"
        return 1
    fi
    value=$(echo "${json}" | python3 -c "import sys,json; print(json.load(sys.stdin)['${field}'])" 2>/dev/null)
    if [[ -z "${value}" ]] || [[ "${value}" == "None" ]]; then
        log_error "Field '${field}' not found in secret '${secret_id}'"
        return 1
    fi
    echo "${value}"
}

# Read a value from config.yaml using yq (falls back to python3)
config_get() {
    local yaml_path="$1"
    local config_file="${2:-${REPO_ROOT}/services/fax/config.yaml}"
    if command -v yq &>/dev/null; then
        yq eval "${yaml_path}" "${config_file}" 2>/dev/null
    else
        python3 -c "
import yaml, sys
with open('${config_file}') as f:
    data = yaml.safe_load(f)
keys = '${yaml_path}'.lstrip('.').split('.')
for k in keys:
    data = data[k]
print(data)
" 2>/dev/null
    fi
}

# Write content to a file (respects --dry-run)
write_file() {
    local filepath="$1"
    local content="$2"
    local description="${3:-}"

    if $DRY_RUN; then
        log_warn "[DRY-RUN] Would write ${filepath}"
        if [[ -n "${description}" ]]; then
            echo "           ${description}"
        fi
        echo "           ($(echo "${content}" | wc -l) lines, $(echo "${content}" | wc -c) bytes)"
        return 0
    fi

    mkdir -p "$(dirname "${filepath}")"
    echo "${content}" > "${filepath}"
    chmod 600 "${filepath}"
    log_ok "Wrote ${filepath}"
}

# Check if a service should be rendered
should_render() {
    local service="$1"
    for s in "${SERVICES[@]}"; do
        if [[ "${s}" == "all" ]] || [[ "${s}" == "${service}" ]]; then
            return 0
        fi
    done
    return 1
}

# ---------- Pre-flight checks ----------
log_info "SHINBEEHUB Secret Renderer"
log_info "GCP Project: ${GCP_PROJECT}"
log_info "Repo root:   ${REPO_ROOT}"
$DRY_RUN && log_warn "DRY-RUN MODE — no files will be written"
echo ""

# Set up WIF authentication if credential files exist
if [[ -f "${WIF_CREDENTIAL_CONFIG}" ]]; then
    export CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE="${WIF_CREDENTIAL_CONFIG}"
    log_info "Using WIF credentials: ${WIF_CREDENTIAL_CONFIG}"
fi
if [[ -f "${CERT_CONFIG}" ]]; then
    export GOOGLE_API_CERTIFICATE_CONFIG="${CERT_CONFIG}"
fi

# Verify GCP access
log_info "Verifying GCP Secret Manager access..."
if ! gcloud secrets list --project="${GCP_PROJECT}" --limit=1 &>/dev/null; then
    log_error "Cannot access GCP Secret Manager. Check your credentials."
    log_error "  Option 1: Place WIF config at ${WIF_CREDENTIAL_CONFIG}"
    log_error "  Option 2: Run 'gcloud auth login' or 'gcloud auth application-default login'"
    exit 1
fi
log_ok "GCP Secret Manager access verified"
echo ""

# Check for yq (optional but preferred)
if ! command -v yq &>/dev/null; then
    log_warn "yq not found — falling back to python3+PyYAML for config.yaml parsing"
    if ! python3 -c "import yaml" 2>/dev/null; then
        log_error "Neither yq nor python3 PyYAML available. Install one of them."
        exit 1
    fi
fi

ERRORS=0

# =============================================================================
# SERVICE: fax
# Renders .env for docker-compose (fax stack on Raspberry Pi)
# =============================================================================
if should_render "fax"; then
    echo "============================================"
    log_info "Rendering secrets for: fax"
    echo "============================================"

    FAX_DIR="${REPO_ROOT}/services/fax"

    # Fetch secrets
    log_info "Fetching fax secrets from GCP SM..."
    AMI_USERNAME=$(gsm_get_field "fax-ami" "username")          || { ERRORS=$((ERRORS+1)); log_error "Skipping fax"; }
    AMI_SECRET=$(gsm_get_field "fax-ami" "secret")              || true
    FAX_API_KEY=$(gsm_get_field "fax-api-key" "api_key")        || true
    MYSQL_ROOT_PW=$(gsm_get_field "fax-db" "mysql_root_password") || true
    MYSQL_PW=$(gsm_get_field "fax-db" "mysql_password")         || true
    MYSQL_USER=$(gsm_get_field "fax-db" "mysql_user")           || true
    MYSQL_DB=$(gsm_get_field "fax-db" "mysql_database")         || true
    SMTP_USER=$(gsm_get_field "fax-smtp" "username")            || true
    SMTP_PASS=$(gsm_get_field "fax-smtp" "password")            || true
    RELAY_USER=$(gsm_get_field "fax-smtp-relay" "username")     || true
    RELAY_PASS=$(gsm_get_field "fax-smtp-relay" "password")     || true
    FAX_AWS_KEY=$(gsm_get_field "fax-aws" "access_key_id")      || true
    FAX_AWS_SECRET=$(gsm_get_field "fax-aws" "secret_access_key") || true
    FAX_AWS_ZONE=$(gsm_get_field "fax-aws" "hosted_zone_id")    || true
    SWITCH_USER=$(gsm_get_field "fax-switch" "username")        || true
    SWITCH_PASS=$(gsm_get_field "fax-switch" "password")        || true

    # Render .env for docker-compose
    ENV_CONTENT="# Auto-generated by render-secrets.sh — DO NOT EDIT
# Fax system docker-compose environment
# Generated: $(date -Iseconds)

# MariaDB (legacy FreePBX profile)
MYSQL_ROOT_PASSWORD=${MYSQL_ROOT_PW}
MYSQL_DATABASE=${MYSQL_DB}
MYSQL_USER=${MYSQL_USER}
MYSQL_PASSWORD=${MYSQL_PW}

# Asterisk AMI (faxapi)
AMI_USERNAME=${AMI_USERNAME}
AMI_SECRET=${AMI_SECRET}

# Fax API key
FAX_API_KEY=${FAX_API_KEY}

# Timezone
TZ=Asia/Tokyo"
    write_file "${FAX_DIR}/.env" "${ENV_CONTENT}" "docker-compose .env for fax stack"

    # Render mail2fax config.yaml secrets
    MAIL2FAX_DIR="${FAX_DIR}/mail2fax"
    if [[ -f "${MAIL2FAX_DIR}/config.yaml" ]]; then
        log_info "Updating mail2fax/config.yaml secret values..."
        if ! $DRY_RUN; then
            if command -v yq &>/dev/null; then
                yq eval -i ".fax_api.api_key = \"${FAX_API_KEY}\"" "${MAIL2FAX_DIR}/config.yaml"
                yq eval -i ".smtp_auth.username = \"${SMTP_USER}\"" "${MAIL2FAX_DIR}/config.yaml"
                yq eval -i ".smtp_auth.password = \"${SMTP_PASS}\"" "${MAIL2FAX_DIR}/config.yaml"
                yq eval -i ".smtp_relay.username = \"${RELAY_USER}\"" "${MAIL2FAX_DIR}/config.yaml"
                yq eval -i ".smtp_relay.password = \"${RELAY_PASS}\"" "${MAIL2FAX_DIR}/config.yaml"
                log_ok "Updated mail2fax/config.yaml"
            else
                log_warn "yq not found — skipping in-place config.yaml update for mail2fax"
                log_warn "Manually set fax_api.api_key, smtp_auth.*, and smtp_relay.* in ${MAIL2FAX_DIR}/config.yaml"
            fi
        else
            log_warn "[DRY-RUN] Would update mail2fax/config.yaml secret fields"
        fi
    fi

    # Render fax/config.yaml switch credentials
    if [[ -f "${FAX_DIR}/config.yaml" ]]; then
        log_info "Updating fax/config.yaml switch credentials..."
        if ! $DRY_RUN && command -v yq &>/dev/null; then
            yq eval -i ".switch.username = \"${SWITCH_USER}\"" "${FAX_DIR}/config.yaml"
            yq eval -i ".switch.password = \"${SWITCH_PASS}\"" "${FAX_DIR}/config.yaml"
            log_ok "Updated fax/config.yaml switch credentials"
        fi
    fi

    # Render AWS credentials for Route53 DNS (mail2fax certbot)
    AWS_DIR="${FAX_DIR}/.aws"
    AWS_CREDS="[default]
aws_access_key_id = ${FAX_AWS_KEY}
aws_secret_access_key = ${FAX_AWS_SECRET}"
    write_file "${AWS_DIR}/credentials" "${AWS_CREDS}" "AWS credentials for Route53 (certbot DNS-01)"

    echo ""
fi

# =============================================================================
# SERVICE: inventory
# Renders secret files for InvenTree docker-compose (Docker secrets)
# =============================================================================
if should_render "inventory"; then
    echo "============================================"
    log_info "Rendering secrets for: inventory"
    echo "============================================"

    INV_DIR="${REPO_ROOT}/services/inventory/shinbee-deploy"
    SECRETS_DIR="${INV_DIR}/secrets"

    # Fetch secrets
    log_info "Fetching inventory secrets from GCP SM..."
    INV_MYSQL_PW=$(gsm_get_field "inventree-db" "mysql_password")          || { ERRORS=$((ERRORS+1)); true; }
    INV_OAUTH_ID=$(gsm_get_field "inventree-oauth" "client_id")            || true
    INV_OAUTH_SECRET=$(gsm_get_field "inventree-oauth" "client_secret")    || true
    INV_AWS_KEY=$(gsm_get_field "inventree-aws" "access_key_id")           || true
    INV_AWS_SECRET=$(gsm_get_field "inventree-aws" "secret_access_key")    || true

    # Docker secrets are single-value files
    write_file "${SECRETS_DIR}/mysql_password" "${INV_MYSQL_PW}" "MySQL password for InvenTree"
    write_file "${SECRETS_DIR}/google_client_id" "${INV_OAUTH_ID}" "Google OAuth client ID"
    write_file "${SECRETS_DIR}/google_client_secret" "${INV_OAUTH_SECRET}" "Google OAuth client secret"

    # Update config.yaml social_providers section
    if [[ -f "${INV_DIR}/config.yaml" ]]; then
        log_info "Updating InvenTree config.yaml OAuth credentials..."
        if ! $DRY_RUN && command -v yq &>/dev/null; then
            yq eval -i ".social_providers.google.APP.client_id = \"${INV_OAUTH_ID}\"" "${INV_DIR}/config.yaml"
            yq eval -i ".social_providers.google.APP.secret = \"${INV_OAUTH_SECRET}\"" "${INV_DIR}/config.yaml"
            log_ok "Updated InvenTree config.yaml"
        fi
    fi

    # Render AWS credentials for Route53 (InvenTree certbot)
    INV_AWS_DIR="${REPO_ROOT}/services/inventory/.aws"
    INV_AWS_CREDS="[default]
aws_access_key_id = ${INV_AWS_KEY}
aws_secret_access_key = ${INV_AWS_SECRET}"
    write_file "${INV_AWS_DIR}/credentials" "${INV_AWS_CREDS}" "AWS credentials for InvenTree certbot"

    echo ""
fi

# =============================================================================
# SERVICE: selenium-daemon
# Renders .env for docker-compose (carrier portal credentials)
# =============================================================================
if should_render "selenium-daemon"; then
    echo "============================================"
    log_info "Rendering secrets for: selenium-daemon"
    echo "============================================"

    SELENIUM_DIR="${REPO_ROOT}/services/selenium-daemon"

    # Fetch secrets
    log_info "Fetching selenium-daemon secrets from GCP SM..."
    SAGAWA_USER=$(gsm_get_field "daemon-sagawa" "user_id")     || { ERRORS=$((ERRORS+1)); true; }
    SAGAWA_PASS=$(gsm_get_field "daemon-sagawa" "password")    || true
    YAMATO_ID=$(gsm_get_field "daemon-yamato" "login_id")      || true
    YAMATO_PASS=$(gsm_get_field "daemon-yamato" "password")    || true

    ENV_CONTENT="# Auto-generated by render-secrets.sh — DO NOT EDIT
# Selenium daemon docker-compose environment
# Generated: $(date -Iseconds)

# Sagawa carrier portal
SAGAWA_USER_ID=${SAGAWA_USER}
SAGAWA_PASSWORD=${SAGAWA_PASS}

# Yamato carrier portal
YAMATO_LOGIN_ID=${YAMATO_ID}
YAMATO_PASSWORD=${YAMATO_PASS}

# GCP credentials (WIF X.509 mTLS — mounted via docker-compose volumes)
GOOGLE_APPLICATION_CREDENTIALS=/app/Vault/pki/wif-credential-config.json
GOOGLE_API_CERTIFICATE_CONFIG=/home/pi/.config/gcloud/certificate_config.json"
    write_file "${SELENIUM_DIR}/.env" "${ENV_CONTENT}" "docker-compose .env for selenium-daemon"

    echo ""
fi

# =============================================================================
# SERVICE: rakuten-renewal
# Renders .env for docker-compose (Rakuten credentials)
# Note: This service is transitioning from Vault AppRole to GCP SM.
#       During transition, it reads secrets at runtime via Vault.
#       Once fully migrated, secrets will be rendered here.
# =============================================================================
if should_render "rakuten-renewal"; then
    echo "============================================"
    log_info "Rendering secrets for: rakuten-renewal"
    echo "============================================"

    RAKUTEN_DIR="${REPO_ROOT}/services/rakuten-renewal"

    log_info "Rakuten renewal currently reads secrets at runtime via Vault AppRole."
    log_info "Once migration is complete, this section will render a .env file."

    # Placeholder for post-migration .env rendering:
    # RAKUTEN_USER=$(gsm_get_field "rakuten-credentials" "username")
    # RAKUTEN_PASS=$(gsm_get_field "rakuten-credentials" "password")
    # GEMINI_API_KEY=$(gsm_get_field "rakuten-credentials" "gemini_api_key")

    ENV_CONTENT="# Auto-generated by render-secrets.sh — DO NOT EDIT
# Rakuten renewal docker-compose environment
# Generated: $(date -Iseconds)

# GCP credentials (WIF X.509 mTLS — mounted via docker-compose volumes)
GOOGLE_APPLICATION_CREDENTIALS=/app/Vault/pki/wif-credential-config.json

# Vault AppRole (transition period — will be removed after full SM migration)
VAULT_ADDR=http://host.docker.internal:8200
VAULT_APPROLE_ROLE_ID_PATH=/run/secrets/role-id
VAULT_APPROLE_SECRET_ID_PATH=/run/secrets/secret-id"
    write_file "${RAKUTEN_DIR}/.env" "${ENV_CONTENT}" "docker-compose .env for rakuten-renewal"

    echo ""
fi

# =============================================================================
# SERVICE: ai-assistant
# Renders .env for the AI assistant service
# =============================================================================
if should_render "ai-assistant"; then
    echo "============================================"
    log_info "Rendering secrets for: ai-assistant"
    echo "============================================"

    AI_DIR="${REPO_ROOT}/services/ai-assistant"

    # Fetch secrets
    log_info "Fetching ai-assistant secrets from GCP SM..."
    SAMBA_ADMIN_PW=$(gsm_get_field "samba-ad" "admin_password") || { ERRORS=$((ERRORS+1)); true; }
    FAX_API_KEY_AI=$(gsm_get_field "fax-api-key" "api_key")    || true

    # Fetch the Vikunja API token (stored in the ai-assistant runtime config
    # or passed via env var; not a GCP SM secret — read from config.yaml)
    VIKUNJA_TOKEN=""
    if [[ -f "${REPO_ROOT}/services/fax/config.yaml" ]]; then
        VIKUNJA_TOKEN=$(config_get ".inventree.api_token" "${REPO_ROOT}/services/fax/config.yaml") || true
    fi

    # Write SA key files for local development
    log_info "Fetching AI assistant SA key..."
    AI_SA_KEY=$(gsm_get "ai-assistant-key") || { log_warn "ai-assistant-key not available"; true; }
    if [[ -n "${AI_SA_KEY}" ]]; then
        write_file "${AI_DIR}/secrets/ai-assistant-key.json" "${AI_SA_KEY}" "AI assistant GCS/Gemini SA key"
    fi

    GSPS_SA_KEY=$(gsm_get "gsps-sa-key") || { log_warn "gsps-sa-key not available"; true; }
    if [[ -n "${GSPS_SA_KEY}" ]]; then
        write_file "${AI_DIR}/secrets/gsps-sa-key.json" "${GSPS_SA_KEY}" "GSPS SA key (password sync)"
    fi

    ENV_CONTENT="# Auto-generated by render-secrets.sh — DO NOT EDIT
# AI assistant environment (local development / docker-compose)
# Generated: $(date -Iseconds)

# GCP
AI_GCP_PROJECT=${GCP_PROJECT}
AI_GCP_LOCATION=asia-northeast1

# Gemini (uses default credentials from GOOGLE_APPLICATION_CREDENTIALS)
GOOGLE_APPLICATION_CREDENTIALS=/app/secrets/ai-assistant-key.json

# LDAP (Samba AD)
AI_LDAP_SERVER=ldap://samba-ad-internal.shinbee.svc.cluster.local:389
AI_LDAP_BASE_DN=DC=ad,DC=your-domain,DC=com
AI_LDAP_BIND_DN=CN=Administrator,CN=Users,DC=ad,DC=your-domain,DC=com
AI_LDAP_BIND_PASSWORD=${SAMBA_ADMIN_PW}

# Fax API
AI_FAXAPI_URL=http://10.0.0.254:8010
AI_FAXAPI_KEY=${FAX_API_KEY_AI}

# Vikunja
AI_VIKUNJA_URL=https://tasks.your-domain.com
AI_VIKUNJA_TOKEN=${VIKUNJA_TOKEN}

# GSPS (password sync)
AI_GSPS_SA_KEY_PATH=/app/secrets/gsps-sa-key.json
AI_GSPS_ADMIN_EMAIL=admin@your-domain.com"
    write_file "${AI_DIR}/.env" "${ENV_CONTENT}" "Environment for ai-assistant"

    echo ""
fi

# =============================================================================
# SERVICE: kubernetes
# Delegates to render-k8s-secrets.sh for K8s secret manifest creation
# =============================================================================
if should_render "kubernetes"; then
    echo "============================================"
    log_info "Rendering secrets for: kubernetes"
    echo "============================================"

    K8S_RENDER="${REPO_ROOT}/infrastructure/kubernetes/scripts/render-k8s-secrets.sh"
    if [[ -f "${K8S_RENDER}" ]]; then
        log_info "Delegating to ${K8S_RENDER}..."
        if $DRY_RUN; then
            log_warn "[DRY-RUN] Would execute: ${K8S_RENDER} all"
        else
            bash "${K8S_RENDER}" all
        fi
    else
        log_error "K8s secret renderer not found at ${K8S_RENDER}"
        ERRORS=$((ERRORS+1))
    fi

    echo ""
fi

# =============================================================================
# Summary
# =============================================================================
echo "============================================"
if [[ ${ERRORS} -gt 0 ]]; then
    log_error "Completed with ${ERRORS} error(s)"
    echo ""
    log_info "Troubleshooting:"
    log_info "  1. Verify secrets exist: gcloud secrets list --project=${GCP_PROJECT}"
    log_info "  2. Check access: gcloud secrets versions access latest --secret=<name> --project=${GCP_PROJECT}"
    log_info "  3. Check WIF config: ${WIF_CREDENTIAL_CONFIG}"
    exit 1
else
    log_ok "All secrets rendered successfully"
    $DRY_RUN && log_warn "DRY-RUN MODE — no files were actually written"
fi

echo ""
log_info "Rendered .env and config files are chmod 600 (owner-only read/write)."
log_info "These files are gitignored and should never be committed."
log_info ""
log_info "Next steps:"
log_info "  - Start services: cd services/<name> && docker compose up -d"
log_info "  - For K8s: ./infrastructure/kubernetes/scripts/render-k8s-secrets.sh"
