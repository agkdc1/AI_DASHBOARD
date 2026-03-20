#!/bin/bash
# =============================================================================
# migrate-data.sh — Export bare-metal data to Docker bind mount directories
# Run this BEFORE starting the containerized stack.
# No downtime — reads from live system.
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DATA_DIR="$PROJECT_DIR/data"
DB_INIT_DIR="$PROJECT_DIR/docker/db/init"

echo "=== RasPBX Data Migration ==="
echo "Project dir: $PROJECT_DIR"
echo "Data dir:    $DATA_DIR"
echo ""

# Check we're running as root
if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: This script must be run as root (sudo)."
    exit 1
fi

# ---------------------------------------------------------------
# 1. Database dump
# ---------------------------------------------------------------
echo "[1/6] Dumping MariaDB databases..."
mkdir -p "$DB_INIT_DIR"
mysqldump --all-databases --single-transaction --routines --triggers \
    > "$DB_INIT_DIR/00-full-dump.sql"
echo "  -> $(du -h "$DB_INIT_DIR/00-full-dump.sql" | cut -f1) written"

# ---------------------------------------------------------------
# 2. Asterisk config (/etc/asterisk/)
# ---------------------------------------------------------------
echo "[2/6] Copying Asterisk config..."
mkdir -p "$DATA_DIR/asterisk-etc"
rsync -a --delete /etc/asterisk/ "$DATA_DIR/asterisk-etc/"
echo "  -> $(du -sh "$DATA_DIR/asterisk-etc" | cut -f1)"

# ---------------------------------------------------------------
# 3. Asterisk lib (/var/lib/asterisk/)
# ---------------------------------------------------------------
echo "[3/6] Copying Asterisk lib (sounds, AGI, MOH, keys)..."
mkdir -p "$DATA_DIR/asterisk-lib"
rsync -a --delete /var/lib/asterisk/ "$DATA_DIR/asterisk-lib/"
echo "  -> $(du -sh "$DATA_DIR/asterisk-lib" | cut -f1)"

# ---------------------------------------------------------------
# 4. Asterisk spool (/var/spool/asterisk/)
# ---------------------------------------------------------------
echo "[4/6] Copying Asterisk spool (voicemail, fax)..."
mkdir -p "$DATA_DIR/asterisk-spool"
rsync -a --delete /var/spool/asterisk/ "$DATA_DIR/asterisk-spool/"
echo "  -> $(du -sh "$DATA_DIR/asterisk-spool" | cut -f1)"

# ---------------------------------------------------------------
# 5. HylaFAX spool (/var/spool/hylafax/)
# ---------------------------------------------------------------
echo "[5/6] Copying HylaFAX spool..."
mkdir -p "$DATA_DIR/hylafax-spool"
rsync -a --delete /var/spool/hylafax/ "$DATA_DIR/hylafax-spool/"
echo "  -> $(du -sh "$DATA_DIR/hylafax-spool" | cut -f1)"

# ---------------------------------------------------------------
# 6. FreePBX web root (/var/www/html/)
# ---------------------------------------------------------------
echo "[6/6] Copying FreePBX web root..."
mkdir -p "$DATA_DIR/freepbx-web"
rsync -a --delete /var/www/html/ "$DATA_DIR/freepbx-web/"
echo "  -> $(du -sh "$DATA_DIR/freepbx-web" | cut -f1)"

# ---------------------------------------------------------------
# Create empty log dir
# ---------------------------------------------------------------
mkdir -p "$DATA_DIR/asterisk-log"

echo ""
echo "=== Migration complete ==="
echo "Total data size: $(du -sh "$DATA_DIR" | cut -f1)"
echo ""
echo "Next steps:"
echo "  1. Review .env file and set passwords"
echo "  2. Build: sudo docker compose build"
echo "  3. Start (quarantine): sudo docker compose up -d"
