#!/bin/bash
# =============================================================================
# Switchover: FreePBX → Headless Asterisk
# Replaces FreePBX config includes with confgen-generated ones.
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")"; pwd)"
FAX_DIR="$SCRIPT_DIR/.."
ASTERISK_ETC="$FAX_DIR/data/asterisk-etc"

echo "=== Switchover: FreePBX → Headless Asterisk ==="
echo "  Time: $(date)"

# Backup current configs
BACKUP_DIR="$ASTERISK_ETC/backup-freepbx-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR"
cp "$ASTERISK_ETC/pjsip.conf" "$BACKUP_DIR/"
cp "$ASTERISK_ETC/extensions.conf" "$BACKUP_DIR/"
echo "  Backed up to: $BACKUP_DIR"

# Replace config files with headless versions
cp "$ASTERISK_ETC/pjsip_headless.conf" "$ASTERISK_ETC/pjsip.conf"
cp "$ASTERISK_ETC/extensions_headless.conf" "$ASTERISK_ETC/extensions.conf"
echo "  Replaced pjsip.conf and extensions.conf"

# Stop FreePBX containers
cd "$FAX_DIR"
echo "  Stopping FreePBX containers..."
sg docker -c "docker compose stop core db"

# Start headless Asterisk
echo "  Starting headless Asterisk..."
sg docker -c "docker compose --profile headless up -d asterisk-headless"

# Restart faxapi (now uses SQLite instead of MariaDB for extensions)
echo "  Restarting faxapi..."
sg docker -c "docker compose restart faxapi"

echo ""
echo "=== Switchover complete ==="
echo "  Verify: sg docker -c 'docker exec asterisk-headless asterisk -rx \"pjsip show endpoints\"'"
echo "  Rollback: bash $SCRIPT_DIR/rollback-headless.sh"
