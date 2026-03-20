#!/bin/bash
# =============================================================================
# cutover.sh — Stop bare-metal services, start containerized stack
# ONLY run after thorough quarantine testing and user approval.
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== RasPBX Cutover: Bare Metal -> Docker ==="
echo ""
echo "WARNING: This will stop all bare-metal PBX services."
echo "Voice and fax will be DOWN until containers are running."
echo ""
read -p "Are you sure? (type YES to confirm): " confirm
if [ "$confirm" != "YES" ]; then
    echo "Aborted."
    exit 1
fi

if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: This script must be run as root (sudo)."
    exit 1
fi

echo ""
echo "[1/5] Stopping bare-metal services..."
systemctl stop asterisk 2>/dev/null || echo "  asterisk already stopped"
systemctl stop apache2 2>/dev/null || echo "  apache2 already stopped"
systemctl stop iaxmodem 2>/dev/null || echo "  iaxmodem already stopped"
systemctl stop hylafax 2>/dev/null || echo "  hylafax already stopped"
systemctl stop mariadb 2>/dev/null || echo "  mariadb already stopped"
# Also stop php-fpm if running
systemctl stop php8.2-fpm 2>/dev/null || true

# Stop existing mail2fax container if running
echo "[2/5] Stopping existing mail2fax container..."
cd "$PROJECT_DIR/mail2fax"
docker compose down 2>/dev/null || echo "  mail2fax not running"

echo "[3/5] Stopping quarantine containers if running..."
cd "$PROJECT_DIR"
docker compose down 2>/dev/null || true

echo "[4/5] Starting containerized stack (production mode)..."
cd "$PROJECT_DIR"
docker compose -f docker-compose.yml -f docker-compose.production.yml up -d

echo "[5/5] Waiting for services to stabilize..."
sleep 10

echo ""
echo "=== Verification ==="
docker exec raspbx-core asterisk -rx "core show version" 2>/dev/null || echo "WARNING: Asterisk not responding"
docker exec raspbx-core asterisk -rx "pjsip show endpoints" 2>/dev/null || echo "WARNING: PJSIP not loaded"
curl -sf http://localhost:8010/health 2>/dev/null && echo "Fax API: OK" || echo "WARNING: Fax API not responding"

echo ""
echo "=== Cutover complete ==="
echo "If issues arise, run: sudo $SCRIPT_DIR/rollback.sh"
