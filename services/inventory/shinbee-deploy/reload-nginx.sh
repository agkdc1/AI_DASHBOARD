#!/bin/bash
# Reload nginx configuration by sending SIGHUP via the Docker Engine API.
# Requires /var/run/docker.sock to be mounted into this container.
set -euo pipefail

SOCK="/var/run/docker.sock"

if [ ! -S "${SOCK}" ]; then
    echo "ERROR: Docker socket not found at ${SOCK}" >&2
    exit 1
fi

# Find the nginx container ID (inventree-proxy)
CONTAINER_ID=$(curl -s --unix-socket "${SOCK}" \
    "http://localhost/containers/json" | \
    jq -r '.[] | select(.Names[] | test("inventree-proxy")) | .Id' | head -1)

if [ -z "${CONTAINER_ID}" ]; then
    echo "ERROR: Could not find inventree-proxy container" >&2
    exit 1
fi

echo "Sending HUP to nginx container ${CONTAINER_ID:0:12}..."
curl -s --unix-socket "${SOCK}" \
    -X POST "http://localhost/containers/${CONTAINER_ID}/kill?signal=HUP"

echo "Nginx reload signal sent."
