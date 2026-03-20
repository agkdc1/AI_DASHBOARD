#!/bin/bash
# =============================================================================
# rollback.sh — Stop containers, restart bare-metal services
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== RasPBX Rollback: Docker -> Bare Metal ==="

if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: This script must be run as root (sudo)."
    exit 1
fi

echo "[1/3] Stopping containerized stack..."
cd "$PROJECT_DIR"
docker compose -f docker-compose.yml -f docker-compose.production.yml down 2>/dev/null || \
    docker compose down 2>/dev/null || echo "  Containers not running"

echo "[2/3] Restarting bare-metal services..."
systemctl start mariadb 2>/dev/null || echo "  mariadb start failed"
sleep 2
systemctl start asterisk 2>/dev/null || echo "  asterisk start failed"
systemctl start apache2 2>/dev/null || echo "  apache2 start failed"
systemctl start iaxmodem 2>/dev/null || echo "  iaxmodem start failed"
systemctl start hylafax 2>/dev/null || echo "  hylafax start failed"

echo "[3/3] Restarting mail2fax container..."
cd "$PROJECT_DIR/mail2fax"
docker compose up -d 2>/dev/null || echo "  mail2fax start failed"

echo ""
echo "=== Rollback complete ==="
echo "Bare-metal services restored."
