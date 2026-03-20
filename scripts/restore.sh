#!/bin/bash
# =============================================================================
# SHINBEE Fax Stack Restore
# Decrypts and restores backups created by backup.sh (fax stack only).
# InvenTree is restored separately from K8s backup (see RUNBOOK.md).
# Usage:
#   ./restore.sh <archive_file>      — restore from a local .tar.xz.enc file
#   ./restore.sh --latest             — download and restore the latest from GCS
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/../config.yaml"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
log()  { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
ok()   { echo "[$(date '+%Y-%m-%d %H:%M:%S')]   OK: $*"; }
err()  { echo "[$(date '+%Y-%m-%d %H:%M:%S')]   ERROR: $*" >&2; }
warn() { echo "[$(date '+%Y-%m-%d %H:%M:%S')]   WARN: $*"; }
die()  { err "$*"; exit 1; }

# ---------------------------------------------------------------------------
# Config reader
# ---------------------------------------------------------------------------
cfg() {
  python3 -c "
import yaml,sys,functools
with open('${CONFIG_FILE}') as f: c=yaml.safe_load(f)
keys=sys.argv[1].split('.')
v=functools.reduce(lambda d,k: d[int(k)] if isinstance(d,list) else d[k], keys, c)
if isinstance(v,list): print('\n'.join(str(x) for x in v))
elif isinstance(v,bool): print(str(v).lower())
else: print(v)
" "$1"
}

cfg_count() {
  python3 -c "
import yaml,sys,functools
with open('${CONFIG_FILE}') as f: c=yaml.safe_load(f)
keys=sys.argv[1].split('.')
v=functools.reduce(lambda d,k: d[int(k)] if isinstance(d,list) else d[k], keys, c)
print(len(v) if isinstance(v,list) else 0)
" "$1"
}

# ---------------------------------------------------------------------------
# Validate
# ---------------------------------------------------------------------------
[[ -f "$CONFIG_FILE" ]] || die "Config not found: $CONFIG_FILE"

REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
GCS_BUCKET="gs://$(cfg gcp.backup_bucket)"
PREFIX="$(cfg backup.prefix)"
STAGING_DIR=""
GOT_PASSWORD_FROM_VAULT=false

# ---------------------------------------------------------------------------
# WIF / GCS auth
# ---------------------------------------------------------------------------
setup_gcs_auth() {
  local wif_cred="${REPO_ROOT}/Vault/pki/wif-credential-config.json"
  local cert_config="/home/pi/.config/gcloud/certificate_config.json"
  if [[ -f "$wif_cred" && -f "$cert_config" ]]; then
    export CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE="${wif_cred}"
    export CLOUDSDK_PYTHON_SITEPACKAGES=1
    export GOOGLE_API_CERTIFICATE_CONFIG="$cert_config"
    ok "Using WIF certificate authentication"
  else
    warn "WIF credentials not found (bare-metal restore?)"
    log "Falling back to interactive gcloud authentication..."
    echo ""
    echo "  You need to authenticate with GCP to access the backup bucket."
    echo "  A browser URL will be shown — open it on another device to complete login."
    echo ""
    gcloud auth login --no-launch-browser
    ok "Authenticated via gcloud login"
  fi
}

# ---------------------------------------------------------------------------
# Cleanup handler
# ---------------------------------------------------------------------------
cleanup() {
  if [[ -n "$STAGING_DIR" && -d "$STAGING_DIR" ]]; then
    log "Cleaning up staging directory..."
    rm -rf "$STAGING_DIR"
  fi
}
trap cleanup EXIT

# ---------------------------------------------------------------------------
# Restore Vault from a .tar.xz archive (unencrypted)
# ---------------------------------------------------------------------------
restore_vault() {
  local vault_archive="$1"
  local vault_data_dir
  vault_data_dir="$(cfg backup.vault.data_dir)"

  log "--- Restoring Vault data ---"

  # Stop Vault container
  log "Stopping Vault container..."
  docker stop vault 2>/dev/null && ok "Vault stopped" || warn "Vault container not running"

  # Decompress and extract
  log "Extracting Vault data from $(basename "$vault_archive")..."
  xz -d < "$vault_archive" | tar xf - -C "${REPO_ROOT}"

  # Fix ownership (UID 100 = vault user in container)
  log "Fixing Vault data ownership (UID 100)..."
  sudo chown -R 100:100 "${REPO_ROOT}/${vault_data_dir}"

  # Preserve KMS SA key permissions
  local sa_key="${REPO_ROOT}/${vault_data_dir}/gcp-kms-sa.json"
  if [[ -f "$sa_key" ]]; then
    sudo chown 100:100 "$sa_key"
  fi

  # Start Vault
  log "Starting Vault container..."
  docker start vault 2>/dev/null && ok "Vault started" || warn "Failed to start Vault"

  # Wait for auto-unseal (up to 60s)
  log "Waiting for Vault auto-unseal..."
  for attempt in $(seq 1 12); do
    if vault status -address=http://127.0.0.1:8200 &>/dev/null; then
      ok "Vault is ready (auto-unsealed)"
      return 0
    fi
    sleep 5
  done
  die "Vault did not become ready within 60 seconds"
}

# ---------------------------------------------------------------------------
# Read encryption password from Vault
# ---------------------------------------------------------------------------
get_password_from_vault() {
  local vault_field
  local vault_secret_path kv_path

  vault_secret_path="$(cfg backup.vault_secret)"
  vault_field="$(cfg backup.vault_field)"
  kv_path="${vault_secret_path#secret/data/}"

  log "Reading encryption password from Vault..."
  source "${REPO_ROOT}/Vault/scripts/vault-env.sh"
  vault_approle_login /root/vault-approle-fax-role-id /root/vault-approle-fax-secret-id

  vault kv get -field="$vault_field" "secret/${kv_path}"
}

# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------
usage() {
  echo "Usage: $0 <archive_file.tar.xz.enc>"
  echo "       $0 --latest"
  echo ""
  echo "Options:"
  echo "  <archive_file>   Path to a local .tar.xz.enc backup archive (password prompted)"
  echo "  --latest         Two-phase restore: vault first (auto), then main backup"
  echo "  --list           List available backups in GCS (main + vault)"
  echo "  -h, --help       Show this help"
  exit 1
}

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------
[[ $# -ge 1 ]] || usage

ARCHIVE_FILE=""
MODE=""

case "$1" in
  --latest)
    MODE="latest"
    ;;
  --list)
    MODE="list"
    ;;
  -h|--help)
    usage
    ;;
  *)
    MODE="local"
    ARCHIVE_FILE="$1"
    [[ -f "$ARCHIVE_FILE" ]] || die "Archive file not found: $ARCHIVE_FILE"
    ;;
esac

# ---------------------------------------------------------------------------
# List mode
# ---------------------------------------------------------------------------
if [[ "$MODE" == "list" ]]; then
  setup_gcs_auth

  log "Main backups (encrypted) in ${GCS_BUCKET}:"
  MAIN_LIST=$(gcloud storage ls "${GCS_BUCKET}/${PREFIX}-*.tar.xz.enc" 2>/dev/null | sort)
  if [[ -n "$MAIN_LIST" ]]; then
    echo "$MAIN_LIST" | while read -r f; do
      SIZE=$(gcloud storage ls -l "$f" 2>/dev/null | awk 'NR==1{print $1}')
      echo "  $(basename "$f")  ($SIZE)"
    done
  else
    echo "  (none)"
  fi

  echo ""
  log "Vault backups (unencrypted) in ${GCS_BUCKET}:"
  VAULT_LIST=$(gcloud storage ls "${GCS_BUCKET}/${PREFIX}-vault-*.tar.xz" 2>/dev/null | sort)
  if [[ -n "$VAULT_LIST" ]]; then
    echo "$VAULT_LIST" | while read -r f; do
      SIZE=$(gcloud storage ls -l "$f" 2>/dev/null | awk 'NR==1{print $1}')
      echo "  $(basename "$f")  ($SIZE)"
    done
  else
    echo "  (none)"
  fi

  exit 0
fi

# ---------------------------------------------------------------------------
# Download latest from GCS
# ---------------------------------------------------------------------------
if [[ "$MODE" == "latest" ]]; then
  setup_gcs_auth

  # Phase 1: Download and restore Vault (unencrypted)
  log "Phase 1: Restoring Vault..."
  LATEST_VAULT=$(gcloud storage ls "${GCS_BUCKET}/${PREFIX}-vault-*.tar.xz" 2>/dev/null | sort | tail -1)
  [[ -n "$LATEST_VAULT" ]] || die "No vault backups found in ${GCS_BUCKET}"

  VAULT_FILE="/tmp/$(basename "$LATEST_VAULT")"
  log "Downloading vault backup: $(basename "$LATEST_VAULT")..."
  gcloud storage cp "$LATEST_VAULT" "$VAULT_FILE" --quiet
  ok "Downloaded vault backup"

  restore_vault "$VAULT_FILE"
  rm -f "$VAULT_FILE"

  # Phase 2: Get encryption password from the just-restored Vault
  log "Phase 2: Retrieving encryption password from Vault..."
  ENCRYPTION_PASSWORD=$(get_password_from_vault)
  [[ -n "$ENCRYPTION_PASSWORD" ]] || die "Encryption password is empty"
  GOT_PASSWORD_FROM_VAULT=true
  ok "Encryption password retrieved from Vault"

  # Phase 3: Download main backup (encrypted)
  log "Phase 3: Downloading main backup..."
  LATEST_MAIN=$(gcloud storage ls "${GCS_BUCKET}/${PREFIX}-*.tar.xz.enc" 2>/dev/null | sort | tail -1)
  [[ -n "$LATEST_MAIN" ]] || die "No main backups found in ${GCS_BUCKET}"

  ARCHIVE_FILE="/tmp/$(basename "$LATEST_MAIN")"
  log "Downloading main backup: $(basename "$LATEST_MAIN")..."
  gcloud storage cp "$LATEST_MAIN" "$ARCHIVE_FILE" --quiet
  ok "Downloaded main backup"
fi

# ---------------------------------------------------------------------------
# Prompt for encryption password (interactive — NOT from Vault)
# ---------------------------------------------------------------------------
log "=== SHINBEE Unified Restore ==="
log "Archive: $ARCHIVE_FILE"

if [[ "$GOT_PASSWORD_FROM_VAULT" != "true" ]]; then
  echo ""
  echo "  The encryption password is needed to decrypt this backup."
  echo "  (This is NOT read from Vault, since Vault itself may be being restored.)"
  echo ""
  read -rsp "  Enter encryption password: " ENCRYPTION_PASSWORD
  echo ""
  [[ -n "$ENCRYPTION_PASSWORD" ]] || die "Password cannot be empty"
fi

# ---------------------------------------------------------------------------
# Decrypt + decompress into staging
# ---------------------------------------------------------------------------
STAGING_DIR="$(mktemp -d /tmp/shinbee-restore-XXXXXX)"
log "Decrypting and decompressing to $STAGING_DIR..."

if ! openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 \
    -pass "pass:${ENCRYPTION_PASSWORD}" \
    -in "$ARCHIVE_FILE" \
  | xz -d \
  | tar xf - -C "$STAGING_DIR" 2>/dev/null; then
  die "Decryption failed — wrong password or corrupt archive?"
fi
ok "Archive decrypted"

# ---------------------------------------------------------------------------
# Show contents and confirm
# ---------------------------------------------------------------------------
echo ""
log "Archive contents:"
for f in "$STAGING_DIR"/*; do
  FNAME=$(basename "$f")
  FSIZE=$(stat -c%s "$f" 2>/dev/null || echo 0)
  echo "  ${FNAME}  ($(numfmt --to=iec "$FSIZE"))"
done
echo ""

# Determine what's available
HAS_DBS=false
HAS_VAULT=false
HAS_DIRS=false

DB_COUNT=$(cfg_count backup.databases)
for ((i=0; i<DB_COUNT; i++)); do
  DB_NAME=$(cfg "backup.databases.${i}.name")
  [[ -f "${STAGING_DIR}/${DB_NAME}.sql" ]] && HAS_DBS=true
done

# Vault is in the main archive only for legacy backups (vault-data.tar).
# In the new two-file scheme, vault was already restored before decryption.
[[ -f "${STAGING_DIR}/vault-data.tar" ]] && HAS_VAULT=true
# If vault was already restored in the two-phase flow, hide the option
if [[ "$GOT_PASSWORD_FROM_VAULT" == "true" ]]; then
  HAS_VAULT=false
fi

DIR_COUNT=$(cfg_count backup.directories)
for ((i=0; i<DIR_COUNT; i++)); do
  DIR_LABEL=$(cfg "backup.directories.${i}.label")
  [[ -f "${STAGING_DIR}/${DIR_LABEL}.tar" ]] && HAS_DIRS=true
done

echo "  Restore options:"
echo "    [a] ALL — restore everything"
$HAS_DBS   && echo "    [d] Databases only"
$HAS_VAULT && echo "    [v] Vault data only"
$HAS_DIRS  && echo "    [f] Directories (bind-mounts) only"
echo "    [q] Quit"
if [[ "$GOT_PASSWORD_FROM_VAULT" == "true" ]]; then
  echo ""
  echo "  (Vault was already restored in the two-phase flow)"
fi
echo ""
read -rp "  Choose what to restore [a/d/v/f/q]: " RESTORE_CHOICE

case "$RESTORE_CHOICE" in
  a) RESTORE_DBS=true;  RESTORE_VAULT=$HAS_VAULT;  RESTORE_DIRS=true ;;
  d) RESTORE_DBS=true;  RESTORE_VAULT=false; RESTORE_DIRS=false ;;
  v) RESTORE_DBS=false; RESTORE_VAULT=true;  RESTORE_DIRS=false ;;
  f) RESTORE_DBS=false; RESTORE_VAULT=false; RESTORE_DIRS=true ;;
  q) log "Restore cancelled."; exit 0 ;;
  *) die "Invalid choice: $RESTORE_CHOICE" ;;
esac

echo ""
read -rp "  This will overwrite existing data. Are you sure? (yes/no): " CONFIRM
[[ "$CONFIRM" == "yes" ]] || { log "Restore cancelled."; exit 0; }

# ---------------------------------------------------------------------------
# Restore databases
# ---------------------------------------------------------------------------
if $RESTORE_DBS; then
  log "--- Restoring databases ---"

  for ((i=0; i<DB_COUNT; i++)); do
    DB_NAME=$(cfg "backup.databases.${i}.name")
    DB_CONTAINER=$(cfg "backup.databases.${i}.container")
    DB_ENGINE=$(cfg "backup.databases.${i}.engine")
    DB_PASSWORD_ENV=$(cfg "backup.databases.${i}.password_env")

    DUMP_FILE="${STAGING_DIR}/${DB_NAME}.sql"
    [[ -f "$DUMP_FILE" ]] || { warn "No dump found for $DB_NAME, skipping"; continue; }

    if ! docker inspect --format='{{.State.Running}}' "$DB_CONTAINER" 2>/dev/null | grep -q true; then
      warn "Container $DB_CONTAINER is not running, skipping $DB_NAME"
      continue
    fi

    log "Restoring $DB_NAME into $DB_CONTAINER..."

    # Get the DB password
    DB_PASSWORD=$(docker inspect --format='{{range .Config.Env}}{{println .}}{{end}}' "$DB_CONTAINER" \
      | grep "^${DB_PASSWORD_ENV}=" | cut -d= -f2- || true)
    if [[ -z "$DB_PASSWORD" ]]; then
      DB_PASSWORD=$(docker exec "$DB_CONTAINER" sh -c "cat /run/secrets/mysql_password 2>/dev/null" || true)
    fi

    # Stop dependent containers before restore
    log "  Stopping dependent containers..."
    if [[ "$DB_NAME" == "fax-mariadb" ]]; then
      for dep in raspbx-core raspbx-faxapi raspbx-mail2fax; do
        docker stop "$dep" 2>/dev/null && ok "  Stopped $dep" || true
      done
    fi

    # Restore
    if [[ "$DB_ENGINE" == "mariadb" ]]; then
      docker exec -i -e "${DB_PASSWORD_ENV}=${DB_PASSWORD}" "$DB_CONTAINER" \
        mariadb -u root -p"${DB_PASSWORD}" < "$DUMP_FILE"
    else
      docker exec -i -e "${DB_PASSWORD_ENV}=${DB_PASSWORD}" "$DB_CONTAINER" \
        mysql -u root -p"${DB_PASSWORD}" < "$DUMP_FILE"
    fi
    ok "$DB_NAME restored"

    # Restart dependent containers
    log "  Restarting dependent containers..."
    if [[ "$DB_NAME" == "fax-mariadb" ]]; then
      for dep in raspbx-core raspbx-faxapi raspbx-mail2fax; do
        docker start "$dep" 2>/dev/null && ok "  Started $dep" || true
      done
    fi
  done
fi

# ---------------------------------------------------------------------------
# Restore Vault data (legacy path — only for old backups with vault-data.tar)
# ---------------------------------------------------------------------------
if $RESTORE_VAULT; then
  VAULT_TAR="${STAGING_DIR}/vault-data.tar"
  if [[ ! -f "$VAULT_TAR" ]]; then
    warn "No vault-data.tar found in archive, skipping Vault restore"
  else
    log "--- Restoring Vault data (legacy archive) ---"
    VAULT_DATA_DIR="$(cfg backup.vault.data_dir)"

    # Stop Vault container
    log "Stopping Vault container..."
    docker stop vault 2>/dev/null && ok "Vault stopped" || warn "Vault container not running"

    # Extract (overwrite existing data)
    log "Extracting Vault data..."
    tar xf "$VAULT_TAR" -C "${REPO_ROOT}"

    # Fix ownership (UID 100 = vault user in container)
    log "Fixing Vault data ownership (UID 100)..."
    sudo chown -R 100:100 "${REPO_ROOT}/${VAULT_DATA_DIR}"

    # Preserve KMS SA key permissions
    local_sa_key="${REPO_ROOT}/${VAULT_DATA_DIR}/gcp-kms-sa.json"
    if [[ -f "$local_sa_key" ]]; then
      sudo chown 100:100 "$local_sa_key"
    fi

    # Restart Vault
    log "Starting Vault container..."
    docker start vault 2>/dev/null && ok "Vault started" || warn "Failed to start Vault"

    # Wait for Vault to be ready
    log "Waiting for Vault to be ready..."
    for attempt in $(seq 1 30); do
      if vault status -address=http://127.0.0.1:8200 &>/dev/null; then
        ok "Vault is ready"
        break
      fi
      sleep 2
    done
  fi
fi

# ---------------------------------------------------------------------------
# Restore bind-mount directories
# ---------------------------------------------------------------------------
if $RESTORE_DIRS; then
  log "--- Restoring directories ---"

  for ((i=0; i<DIR_COUNT; i++)); do
    DIR_PATH=$(cfg "backup.directories.${i}.path")
    DIR_LABEL=$(cfg "backup.directories.${i}.label")
    TAR_FILE="${STAGING_DIR}/${DIR_LABEL}.tar"

    [[ -f "$TAR_FILE" ]] || { warn "No ${DIR_LABEL}.tar found, skipping"; continue; }

    log "Restoring $DIR_LABEL..."
    # Extract to repo root (tar contains relative path from repo root)
    tar xf "$TAR_FILE" -C "${REPO_ROOT}"
    ok "$DIR_LABEL restored to ${REPO_ROOT}/${DIR_PATH}"
  done
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
log "=== Restore Summary ==="
[[ "$GOT_PASSWORD_FROM_VAULT" == "true" ]] && log "  Vault data:   restored (two-phase)"
$RESTORE_DBS   && log "  Databases:    restored"
$RESTORE_VAULT && log "  Vault data:   restored (legacy)"
$RESTORE_DIRS  && log "  Directories:  restored"
log "=== Restore complete ==="
echo ""
echo "  Next steps:"
echo "    - Verify services are running: docker ps"
echo "    - Check Vault status: vault status -address=http://127.0.0.1:8200"
echo "    - Run render script to re-inject secrets if needed:"
echo "        sudo systemctl start vault-render-fax.service"
echo ""
echo "  K8s database restore (InvenTree MySQL + intranet PostgreSQL):"
echo "    1. List K8s backups:"
echo "         gcloud storage ls gs://your-project-vault-backup/k8s-inventree-*.sql.xz.enc | sort | tail -5"
echo "         gcloud storage ls gs://your-project-vault-backup/k8s-intranet-*.sql.xz.enc | sort | tail -5"
echo "    2. Download and decrypt:"
echo "         gcloud storage cp gs://your-project-vault-backup/<backup-file> /tmp/"
echo "         openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 -pass 'pass:<pw>' < /tmp/<file>.sql.xz.enc | xz -d > /tmp/dump.sql"
echo "    3. Restore InvenTree MySQL:"
echo "         kubectl -n shinbee exec -i statefulset/inventree-db -- mysql -u inventree -p<pw> inventree < /tmp/dump.sql"
echo "    4. Restore intranet PostgreSQL (vikunja or outline):"
echo "         kubectl -n intranet exec -i statefulset/intranet-db -- psql -U postgres <db> < /tmp/dump.sql"
echo "    5. Restart dependent pods:"
echo "         kubectl -n shinbee rollout restart deployment/inventree-server deployment/inventree-worker"
echo "         kubectl -n intranet rollout restart deployment/intranet-vikunja deployment/intranet-outline"
echo ""
echo "  K8s fax-system restore (Asterisk PBX):"
echo "    1. List fax-system backups:"
echo "         gcloud storage ls gs://your-project-vault-backup/k8s-fax-system-*.sql.xz.enc | sort | tail -5"
echo "    2. Download and decrypt PBX database:"
echo "         gcloud storage cp gs://your-project-vault-backup/<backup-file> /tmp/"
echo "         openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 -pass 'pass:<pw>' < /tmp/<file>.sql.xz.enc | xz -d > /tmp/pbx.db"
echo "    3. Copy PBX database into running pod:"
echo "         kubectl -n fax-system cp /tmp/pbx.db deployment/asterisk:/var/lib/asterisk/pbx.db"
echo "    4. Run confgen + reload inside the pod:"
echo "         kubectl -n fax-system exec deployment/asterisk -c faxapi -- python3 /opt/confgen.py --db /var/lib/asterisk/pbx.db --output-dir /etc/asterisk"
echo "         kubectl -n fax-system exec deployment/asterisk -c asterisk -- asterisk -rx 'core reload'"
echo "    5. Or restart the pod to regenerate all configs from entrypoint:"
echo "         kubectl -n fax-system rollout restart deployment/asterisk"
