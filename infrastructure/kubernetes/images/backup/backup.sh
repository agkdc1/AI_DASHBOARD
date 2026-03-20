#!/bin/bash
# =============================================================================
# K8s Database Backup
# Dumps MySQL (InvenTree) and PostgreSQL (intranet), compresses, encrypts,
# uploads to GCS, prunes old backups. Runs as a K8s CronJob container.
# =============================================================================
set -euo pipefail

log()  { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
ok()   { echo "[$(date '+%Y-%m-%d %H:%M:%S')]   OK: $*"; }
err()  { echo "[$(date '+%Y-%m-%d %H:%M:%S')]   ERROR: $*" >&2; }
die()  { err "$*"; exit 1; }

# ---------------------------------------------------------------------------
# Required environment variables
# ---------------------------------------------------------------------------
: "${GCS_BUCKET:?GCS_BUCKET is required}"
: "${ENCRYPTION_PASSWORD:?ENCRYPTION_PASSWORD is required}"
: "${RETENTION_COUNT:=30}"

# MySQL (InvenTree) — optional (skip if DB_HOST not set)
: "${DB_HOST:=}"
: "${DB_PORT:=3306}"
: "${DB_USER:=}"
: "${DB_PASSWORD:=}"
: "${DB_NAME:=}"
: "${BACKUP_PREFIX:=k8s-inventree}"

# PostgreSQL (intranet) — optional (skip if PG_HOST not set)
: "${PG_HOST:=}"
: "${PG_PORT:=5432}"
: "${PG_USER:=}"
: "${PG_PASSWORD:=}"
: "${PG_DATABASES:=}"
: "${PG_BACKUP_PREFIX:=k8s-intranet}"

DATE=$(date +%Y%m%d-%H%M%S)
ERRORS=0

# ---------------------------------------------------------------------------
# 1. Authenticate to GCS
# ---------------------------------------------------------------------------
log "=== K8s Database Backup ==="

if [[ -f /etc/gcs/key.json ]]; then
  log "Authenticating to GCS..."
  gcloud auth activate-service-account --key-file=/etc/gcs/key.json --quiet
  ok "GCS authenticated"
else
  die "GCS service account key not found at /etc/gcs/key.json"
fi

# ---------------------------------------------------------------------------
# Helper: backup, encrypt, upload, prune
# ---------------------------------------------------------------------------
prune_old() {
  local prefix="$1" pattern="$2"
  if [[ "$RETENTION_COUNT" -gt 0 ]]; then
    log "Pruning old ${prefix} backups (keeping ${RETENTION_COUNT})..."
    local list count
    list=$(gcloud storage ls "gs://${GCS_BUCKET}/${pattern}" 2>/dev/null | sort)
    count=$(echo "$list" | grep -c . || true)
    if [[ "$count" -gt "$RETENTION_COUNT" ]]; then
      local del=$((count - RETENTION_COUNT))
      echo "$list" | head -n "$del" | while read -r old; do
        log "  Deleting: $(basename "$old")"
        gcloud storage rm "$old" --quiet
      done
      ok "Pruned ${del} old ${prefix} backup(s)"
    else
      ok "No ${prefix} pruning needed (${count} backups)"
    fi
  fi
}

# ---------------------------------------------------------------------------
# 2. MySQL dump (InvenTree)
# ---------------------------------------------------------------------------
if [[ -n "$DB_HOST" && -n "$DB_NAME" ]]; then
  MYSQL_FILE="${BACKUP_PREFIX}-${DATE}.sql.xz.enc"
  log "Dumping MySQL: ${DB_NAME} from ${DB_HOST}:${DB_PORT}..."

  if mysqldump -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" -p"$DB_PASSWORD" \
      --single-transaction --routines --triggers --no-tablespaces "$DB_NAME" \
    | xz -3 \
    | openssl enc -aes-256-cbc -salt -pbkdf2 -iter 600000 \
        -pass "pass:${ENCRYPTION_PASSWORD}" \
    | gcloud storage cp - "gs://${GCS_BUCKET}/${MYSQL_FILE}" --quiet; then
    ok "MySQL backup uploaded: gs://${GCS_BUCKET}/${MYSQL_FILE}"
  else
    err "MySQL backup FAILED"
    ERRORS=$((ERRORS + 1))
  fi

  prune_old "MySQL" "${BACKUP_PREFIX}-*.sql.xz.enc"
else
  log "Skipping MySQL backup (DB_HOST not set)"
fi

# ---------------------------------------------------------------------------
# 3. PostgreSQL dump (intranet databases)
# ---------------------------------------------------------------------------
if [[ -n "$PG_HOST" && -n "$PG_DATABASES" ]]; then
  export PGPASSWORD="$PG_PASSWORD"

  # PG_DATABASES is comma-separated: "vikunja,outline"
  IFS=',' read -ra PG_DBS <<< "$PG_DATABASES"
  for pgdb in "${PG_DBS[@]}"; do
    pgdb=$(echo "$pgdb" | xargs)  # trim whitespace
    PG_FILE="${PG_BACKUP_PREFIX}-${pgdb}-${DATE}.sql.xz.enc"
    log "Dumping PostgreSQL: ${pgdb} from ${PG_HOST}:${PG_PORT}..."

    if pg_dump -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$pgdb" \
        --no-owner --no-privileges \
      | xz -3 \
      | openssl enc -aes-256-cbc -salt -pbkdf2 -iter 600000 \
          -pass "pass:${ENCRYPTION_PASSWORD}" \
      | gcloud storage cp - "gs://${GCS_BUCKET}/${PG_FILE}" --quiet; then
      ok "PostgreSQL backup uploaded: gs://${GCS_BUCKET}/${PG_FILE}"
    else
      err "PostgreSQL backup of ${pgdb} FAILED"
      ERRORS=$((ERRORS + 1))
    fi

    prune_old "PostgreSQL/${pgdb}" "${PG_BACKUP_PREFIX}-${pgdb}-*.sql.xz.enc"
  done

  unset PGPASSWORD
else
  log "Skipping PostgreSQL backup (PG_HOST not set)"
fi

# ---------------------------------------------------------------------------
# 4. Summary
# ---------------------------------------------------------------------------
if [[ "$ERRORS" -gt 0 ]]; then
  err "Backup completed with ${ERRORS} error(s)"
  exit 1
fi

log "=== Backup complete ==="
