#!/bin/bash
# =============================================================================
# SHINBEE Fax Stack Backup (Pi host)
# Backs up fax MariaDB + Vault data + fax directories, encrypts with a
# password from Vault, compresses to .tar.xz.enc, and uploads to GCS.
#
# K8s databases (InvenTree MySQL + intranet PostgreSQL) are backed up
# separately by the K8s CronJob at 03:00 JST daily.
# See: infrastructure/kubernetes/manifests/backup/cronjob.yaml
#
# Longhorn PVCs use 2 replicas across 3 worker nodes. If a node is lost,
# data survives on the remaining replica. Full DB restore is available
# from daily GCS backups. See restore.sh for restore procedures.
#
# Runs on the host (not containerized). Intended for systemd timer.
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/../config.yaml"
DATE=$(date +%Y%m%d-%H%M%S)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
log()  { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
ok()   { echo "[$(date '+%Y-%m-%d %H:%M:%S')]   OK: $*"; }
err()  { echo "[$(date '+%Y-%m-%d %H:%M:%S')]   ERROR: $*" >&2; }
die()  { err "$*"; cleanup; exit 1; }

# ---------------------------------------------------------------------------
# Config reader (same pattern as install.sh)
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

# cfg_count: return number of items in a list
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
# Validate config
# ---------------------------------------------------------------------------
[[ -f "$CONFIG_FILE" ]] || { echo "Config not found: $CONFIG_FILE"; exit 1; }
python3 -c "import yaml; yaml.safe_load(open('$CONFIG_FILE'))" 2>/dev/null \
  || { echo "Invalid YAML: $CONFIG_FILE"; exit 1; }

REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
STAGING_DIR="$(cfg backup.staging_dir)/shinbee-backup-${DATE}"
GCS_BUCKET="gs://$(cfg gcp.backup_bucket)"
PREFIX="$(cfg backup.prefix)"
ARCHIVE_NAME="${PREFIX}-${DATE}.tar.xz.enc"
VAULT_ARCHIVE_NAME="${PREFIX}-vault-${DATE}.tar.xz"
RETENTION=$(cfg backup.retention_count)

# ---------------------------------------------------------------------------
# WIF / GCS auth (same as old vault backup)
# ---------------------------------------------------------------------------
WIF_CRED="${REPO_ROOT}/Vault/pki/wif-credential-config.json"
export CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE="${WIF_CRED}"
export CLOUDSDK_PYTHON_SITEPACKAGES=1
export GOOGLE_API_CERTIFICATE_CONFIG="/home/pi/.config/gcloud/certificate_config.json"

# ---------------------------------------------------------------------------
# Cleanup handler
# ---------------------------------------------------------------------------
cleanup() {
  if [[ -d "$STAGING_DIR" ]]; then
    log "Cleaning up staging directory..."
    rm -rf "$STAGING_DIR"
  fi
  # Remove the final archives from /tmp if they still exist
  rm -f "$(cfg backup.staging_dir)/${ARCHIVE_NAME}"
  rm -f "$(cfg backup.staging_dir)/${VAULT_ARCHIVE_NAME}"
}
trap cleanup EXIT

# ---------------------------------------------------------------------------
# 1. Vault AppRole login
# ---------------------------------------------------------------------------
log "=== SHINBEE Unified Backup ==="
log "Logging in to Vault..."

source "${REPO_ROOT}/Vault/scripts/vault-env.sh"
vault_approle_login /root/vault-approle-fax-role-id /root/vault-approle-fax-secret-id

# ---------------------------------------------------------------------------
# 2. Read encryption password from Vault
# ---------------------------------------------------------------------------
log "Reading encryption password from Vault..."
VAULT_SECRET_PATH="$(cfg backup.vault_secret)"
VAULT_FIELD="$(cfg backup.vault_field)"
# vault_secret is the KV v2 data path; strip "secret/data/" to get the kv get path
KV_PATH="${VAULT_SECRET_PATH#secret/data/}"
ENCRYPTION_PASSWORD=$(vault kv get -field="$VAULT_FIELD" "secret/${KV_PATH}")
[[ -n "$ENCRYPTION_PASSWORD" ]] || die "Encryption password is empty"
ok "Encryption password retrieved"

# ---------------------------------------------------------------------------
# 3. Create staging directory
# ---------------------------------------------------------------------------
mkdir -p "$STAGING_DIR"
log "Staging directory: $STAGING_DIR"

# ---------------------------------------------------------------------------
# 4. Database dumps
# LEGACY: fax-mariadb dump targets Docker container "raspbx-db" which was part
# of the FreePBX stack. Fax stack migrated to K8s (fax-system namespace)
# 2026-03-08 — no MariaDB in the K8s fax stack. This section will be skipped
# harmlessly when the container is not running.
# ---------------------------------------------------------------------------
DB_COUNT=$(cfg_count backup.databases)
for ((i=0; i<DB_COUNT; i++)); do
  DB_NAME=$(cfg "backup.databases.${i}.name")
  DB_CONTAINER=$(cfg "backup.databases.${i}.container")
  DB_DUMP_CMD=$(cfg "backup.databases.${i}.dump_cmd")
  DB_PASSWORD_ENV=$(cfg "backup.databases.${i}.password_env")

  log "Dumping database: $DB_NAME (container: $DB_CONTAINER)..."

  # Check if container is running
  if ! docker inspect --format='{{.State.Running}}' "$DB_CONTAINER" 2>/dev/null | grep -q true; then
    err "Container $DB_CONTAINER is not running, skipping $DB_NAME"
    continue
  fi

  # Get the DB password from the container's environment
  DB_PASSWORD=$(docker inspect --format='{{range .Config.Env}}{{println .}}{{end}}' "$DB_CONTAINER" \
    | grep "^${DB_PASSWORD_ENV}=" | cut -d= -f2- || true)

  if [[ -z "$DB_PASSWORD" ]]; then
    # Try Docker secrets (inventree uses MYSQL_ROOT_PASSWORD_FILE)
    DB_PASSWORD=$(docker exec "$DB_CONTAINER" sh -c "cat /run/secrets/mysql_password 2>/dev/null" || true)
  fi

  if [[ -z "$DB_PASSWORD" ]]; then
    err "Could not find $DB_PASSWORD_ENV for container $DB_CONTAINER, skipping"
    continue
  fi

  # Execute dump, substituting the password env var
  docker exec -e "${DB_PASSWORD_ENV}=${DB_PASSWORD}" "$DB_CONTAINER" \
    sh -c "$DB_DUMP_CMD" > "${STAGING_DIR}/${DB_NAME}.sql" 2>/dev/null

  DUMP_SIZE=$(stat -c%s "${STAGING_DIR}/${DB_NAME}.sql" 2>/dev/null || echo 0)
  if [[ "$DUMP_SIZE" -lt 100 ]]; then
    err "Dump for $DB_NAME looks too small (${DUMP_SIZE} bytes), check for errors"
  else
    ok "$DB_NAME dumped ($(numfmt --to=iec "$DUMP_SIZE"))"
  fi
done

# ---------------------------------------------------------------------------
# 5. Vault data
# ---------------------------------------------------------------------------
log "Backing up Vault data (separate unencrypted archive)..."
VAULT_DATA_DIR="$(cfg backup.vault.data_dir)"
VAULT_EXCLUDE_COUNT=$(cfg_count backup.vault.exclude)
EXCLUDE_ARGS=()
for ((i=0; i<VAULT_EXCLUDE_COUNT; i++)); do
  EXCLUDE_ARGS+=(--exclude="$(cfg "backup.vault.exclude.${i}")")
done

VAULT_ARCHIVE="$(cfg backup.staging_dir)/${VAULT_ARCHIVE_NAME}"
tar cf - -C "${REPO_ROOT}" "${EXCLUDE_ARGS[@]}" "$VAULT_DATA_DIR" \
  | xz -3 > "$VAULT_ARCHIVE"
VAULT_SIZE=$(stat -c%s "$VAULT_ARCHIVE" 2>/dev/null || echo 0)
ok "Vault data archived ($(numfmt --to=iec "$VAULT_SIZE"))"

# ---------------------------------------------------------------------------
# 6. Bind-mount directories
# LEGACY: Fax bind-mount dirs under services/fax/data/ were used by the
# Docker fax stack. Since 2026-03-08, fax containers run in K8s (fax-system
# namespace) with Longhorn PVCs. These dirs may still exist on disk but are
# no longer actively written to. PVC data is backed up via K8s export above.
# ---------------------------------------------------------------------------
DIR_COUNT=$(cfg_count backup.directories)
for ((i=0; i<DIR_COUNT; i++)); do
  DIR_PATH=$(cfg "backup.directories.${i}.path")
  DIR_LABEL=$(cfg "backup.directories.${i}.label")
  FULL_PATH="${REPO_ROOT}/${DIR_PATH}"

  if [[ -d "$FULL_PATH" ]]; then
    log "Backing up directory: $DIR_LABEL ($DIR_PATH)..."
    tar cf "${STAGING_DIR}/${DIR_LABEL}.tar" -C "${REPO_ROOT}" "$DIR_PATH"
    TAR_SIZE=$(stat -c%s "${STAGING_DIR}/${DIR_LABEL}.tar" 2>/dev/null || echo 0)
    ok "$DIR_LABEL archived ($(numfmt --to=iec "$TAR_SIZE"))"
  else
    err "Directory not found: $FULL_PATH, skipping $DIR_LABEL"
  fi
done

# ---------------------------------------------------------------------------
# 7. Create final encrypted archive
# ---------------------------------------------------------------------------
log "Creating encrypted archive: $ARCHIVE_NAME"
FINAL_ARCHIVE="$(cfg backup.staging_dir)/${ARCHIVE_NAME}"

tar cf - -C "$STAGING_DIR" . \
  | xz -3 \
  | openssl enc -aes-256-cbc -salt -pbkdf2 -iter 600000 \
      -pass "pass:${ENCRYPTION_PASSWORD}" \
      -out "$FINAL_ARCHIVE"

FINAL_SIZE=$(stat -c%s "$FINAL_ARCHIVE" 2>/dev/null || echo 0)
ok "Archive created ($(numfmt --to=iec "$FINAL_SIZE"))"

# ---------------------------------------------------------------------------
# 8. Upload to GCS
# ---------------------------------------------------------------------------
log "Uploading main archive to ${GCS_BUCKET}/${ARCHIVE_NAME}..."
gcloud storage cp "$FINAL_ARCHIVE" "${GCS_BUCKET}/${ARCHIVE_NAME}" --quiet
ok "Main archive uploaded"

log "Uploading vault archive to ${GCS_BUCKET}/${VAULT_ARCHIVE_NAME}..."
gcloud storage cp "$VAULT_ARCHIVE" "${GCS_BUCKET}/${VAULT_ARCHIVE_NAME}" --quiet
ok "Vault archive uploaded"

# ---------------------------------------------------------------------------
# 9. Prune old backups
# ---------------------------------------------------------------------------
if [[ "$RETENTION" -gt 0 ]]; then
  # Prune main backups (.enc files)
  log "Pruning old main backups (keeping $RETENTION)..."
  BACKUP_LIST=$(gcloud storage ls "${GCS_BUCKET}/${PREFIX}-*.tar.xz.enc" 2>/dev/null | sort)
  BACKUP_COUNT=$(echo "$BACKUP_LIST" | grep -c . || true)

  if [[ "$BACKUP_COUNT" -gt "$RETENTION" ]]; then
    DELETE_COUNT=$((BACKUP_COUNT - RETENTION))
    echo "$BACKUP_LIST" | head -n "$DELETE_COUNT" | while read -r old_backup; do
      log "  Deleting: $(basename "$old_backup")"
      gcloud storage rm "$old_backup" --quiet
    done
    ok "Pruned $DELETE_COUNT old main backup(s)"
  else
    ok "No main pruning needed ($BACKUP_COUNT backups, keeping $RETENTION)"
  fi

  # Prune vault backups
  log "Pruning old vault backups (keeping $RETENTION)..."
  VAULT_LIST=$(gcloud storage ls "${GCS_BUCKET}/${PREFIX}-vault-*.tar.xz" 2>/dev/null | sort)
  VAULT_COUNT=$(echo "$VAULT_LIST" | grep -c . || true)

  if [[ "$VAULT_COUNT" -gt "$RETENTION" ]]; then
    DELETE_COUNT=$((VAULT_COUNT - RETENTION))
    echo "$VAULT_LIST" | head -n "$DELETE_COUNT" | while read -r old_backup; do
      log "  Deleting: $(basename "$old_backup")"
      gcloud storage rm "$old_backup" --quiet
    done
    ok "Pruned $DELETE_COUNT old vault backup(s)"
  else
    ok "No vault pruning needed ($VAULT_COUNT backups, keeping $RETENTION)"
  fi
fi

# ---------------------------------------------------------------------------
# 10. K8s resource export (Flutter dashboard + AI assistant manifests state)
# ---------------------------------------------------------------------------
log "Exporting K8s resource state..."
KUBECONFIG="/etc/rancher/k3s/k3s.yaml"
K8S_DIR="${STAGING_DIR}/k8s-state"
mkdir -p "$K8S_DIR"

for ns in shinbee intranet fax-system; do
  for kind in deployment service ingress cronjob configmap; do
    if sudo KUBECONFIG="$KUBECONFIG" kubectl -n "$ns" get "$kind" -o yaml > "${K8S_DIR}/${ns}-${kind}.yaml" 2>/dev/null; then
      ok "Exported $ns/$kind"
    fi
  done
done
ok "K8s resource state exported"

# ---------------------------------------------------------------------------
# 11. Flutter build artifacts inventory (list, not download — artifacts are in GCS)
# ---------------------------------------------------------------------------
log "Recording Flutter artifacts inventory..."
FLUTTER_BUCKET="gs://$(cfg flutter.artifacts_bucket)"
gcloud storage ls -l "${FLUTTER_BUCKET}/" 2>/dev/null > "${STAGING_DIR}/flutter-artifacts-inventory.txt" || true
ok "Flutter artifacts inventory saved"

# ---------------------------------------------------------------------------
# 12. AI assistant logs inventory (list — logs are in GCS with 90-day lifecycle)
# ---------------------------------------------------------------------------
log "Recording AI logs inventory..."
AI_LOGS_BUCKET="gs://$(cfg ai_assistant.gcs.ai_logs_bucket)"
gcloud storage ls -l "${AI_LOGS_BUCKET}/" 2>/dev/null > "${STAGING_DIR}/ai-logs-inventory.txt" || true
AI_SOPS_BUCKET="gs://$(cfg ai_assistant.gcs.sop_bucket)"
gcloud storage ls -l "${AI_SOPS_BUCKET}/" 2>/dev/null > "${STAGING_DIR}/ai-sops-inventory.txt" || true
ok "AI logs/SOPs inventory saved"

# ---------------------------------------------------------------------------
# Done (cleanup runs via trap)
# ---------------------------------------------------------------------------
log "=== Backup complete ==="
log "  Main:  ${GCS_BUCKET}/${ARCHIVE_NAME}"
log "  Vault: ${GCS_BUCKET}/${VAULT_ARCHIVE_NAME}"
