#!/bin/bash
# =============================================================================
# Rollback: Headless Asterisk → FreePBX
# Restores FreePBX containers and config files.
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")"; pwd)"
FAX_DIR="$SCRIPT_DIR/.."
ASTERISK_ETC="$FAX_DIR/data/asterisk-etc"

echo "=== Rollback: Headless Asterisk → FreePBX ==="
echo "  Time: $(date)"

# Find latest backup
BACKUP_DIR=$(ls -td "$ASTERISK_ETC"/backup-freepbx-* 2>/dev/null | head -1)
if [ -z "$BACKUP_DIR" ]; then
    echo "ERROR: No backup found in $ASTERISK_ETC/backup-freepbx-*"
    exit 1
fi
echo "  Restoring from: $BACKUP_DIR"

# Stop headless Asterisk
cd "$FAX_DIR"
echo "  Stopping headless Asterisk..."
sg docker -c "docker compose --profile headless stop asterisk-headless" 2>/dev/null || true

# Restore FreePBX configs
cp "$BACKUP_DIR/pjsip.conf" "$ASTERISK_ETC/pjsip.conf"
cp "$BACKUP_DIR/extensions.conf" "$ASTERISK_ETC/extensions.conf"
echo "  Restored pjsip.conf and extensions.conf from backup"

# Start FreePBX containers
echo "  Starting FreePBX containers..."
sg docker -c "docker compose up -d db core"

# Restart faxapi
echo "  Restarting faxapi..."
sg docker -c "docker compose restart faxapi"

echo ""
echo "=== Rollback complete ==="
echo "  Verify: sg docker -c 'docker exec raspbx-core asterisk -rx \"pjsip show endpoints\"'"
