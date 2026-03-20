#!/usr/bin/env bash
# insert-rakuten-keys.sh — Securely insert Rakuten RMS API keys into GCP Secret Manager.
#
# Reads serviceSecret and licenseKey interactively (no echo) so they
# never appear in shell history, process list, or log files.
#
# Usage:  bash phone/insert-rakuten-keys.sh

set -euo pipefail

PROJECT="your-gcp-project-id"
SECRET_ID="rakuten-api-keys"
export GOOGLE_APPLICATION_CREDENTIALS="/home/pi/keys/fax-terraform-deploy.json"

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

log() { echo -e "${GREEN}[OK]${NC} $*"; }
err() { echo -e "${RED}[ERR]${NC} $*" >&2; }

# --- Read keys securely (no echo) ---
read -rsp "Enter serviceSecret: " SERVICE_SECRET
echo
read -rsp "Enter licenseKey: " LICENSE_KEY
echo

if [[ -z "$SERVICE_SECRET" || -z "$LICENSE_KEY" ]]; then
    err "Both serviceSecret and licenseKey are required."
    exit 1
fi

# --- Build JSON payload ---
RENEWED_AT=$(date -u +"%Y-%m-%dT%H:%M:%S+00:00")
PAYLOAD=$(python3 -c "
import json, sys
print(json.dumps({
    'service_secret': sys.argv[1],
    'license_key': sys.argv[2],
    'renewed_at': sys.argv[3],
    'submitted_by': 'cli',
    'assigned_employees': []
}, ensure_ascii=False))
" "$SERVICE_SECRET" "$LICENSE_KEY" "$RENEWED_AT")

# --- Create secret if it doesn't exist ---
if ! gcloud secrets describe "$SECRET_ID" --project="$PROJECT" &>/dev/null; then
    echo "Creating secret $SECRET_ID..."
    gcloud secrets create "$SECRET_ID" \
        --project="$PROJECT" \
        --replication-policy="automatic" \
        --quiet
    log "Secret $SECRET_ID created"
fi

# --- Add new version ---
echo -n "$PAYLOAD" | gcloud secrets versions add "$SECRET_ID" \
    --project="$PROJECT" \
    --data-file=- \
    --quiet

log "Secret version added to $SECRET_ID"
echo "  renewed_at: $RENEWED_AT"

# --- Verify ---
echo "Verifying..."
STORED=$(gcloud secrets versions access latest \
    --secret="$SECRET_ID" \
    --project="$PROJECT" 2>/dev/null)

STORED_SECRET=$(echo "$STORED" | python3 -c "import json,sys; print(json.load(sys.stdin)['service_secret'][:4] + '****')")
STORED_LICENSE=$(echo "$STORED" | python3 -c "import json,sys; print(json.load(sys.stdin)['license_key'][:4] + '****')")

log "Verified — service_secret: ${STORED_SECRET}, license_key: ${STORED_LICENSE}"

# --- Clear variables ---
SERVICE_SECRET=""
LICENSE_KEY=""
PAYLOAD=""
