#!/bin/bash
# extract-frontend.sh — Copy the built React frontend from a running
# InvenTree container to the local portal/web/ directory.
#
# For future standalone serving; not needed for the current sub_filter approach.
#
# Usage:
#   cd services/inventory/portal
#   bash extract-frontend.sh [container_name]

set -euo pipefail

CONTAINER="${1:-shinbee-deploy-inventree-server-1}"
DEST="$(dirname "$0")/web"

echo "Extracting frontend from container '${CONTAINER}'..."

rm -rf "${DEST}"
mkdir -p "${DEST}"

docker cp "${CONTAINER}:/home/inventree/data/static/web/." "${DEST}/"

echo "Done. Frontend extracted to ${DEST}/ ($(find "${DEST}" -type f | wc -l) files)"
