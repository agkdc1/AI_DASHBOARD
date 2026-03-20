#!/bin/bash
# save-authkey.sh — Store Tailscale auth key in GCP Secret Manager
#
# Run this ONCE before terraform apply (or whenever the key rotates).
# The key is prompted interactively — never passed as a CLI argument.
#
# Usage: ./save-authkey.sh [secret-id] [project-id]

set -euo pipefail

SECRET_ID="${1:-k3s-tailscale-authkey}"
PROJECT_ID="${2:-your-gcp-project-id}"

echo "Storing Tailscale auth key in Secret Manager"
echo "  Secret:  ${SECRET_ID}"
echo "  Project: ${PROJECT_ID}"
echo ""

# Check if gcloud is authenticated
if ! gcloud auth print-identity-token &>/dev/null; then
    echo "ERROR: Not authenticated. Run: gcloud auth login"
    exit 1
fi

# Check if the secret exists (terraform creates it, but handle pre-terraform use)
if ! gcloud secrets describe "${SECRET_ID}" --project="${PROJECT_ID}" &>/dev/null; then
    echo "Secret '${SECRET_ID}' does not exist yet."
    echo "Run 'terraform apply' first to create the secret resource,"
    echo "then re-run this script to add the auth key value."
    exit 1
fi

# Prompt for the auth key (masked)
read -rsp "Tailscale Auth Key: " TS_KEY
echo ""

if [ -z "${TS_KEY}" ]; then
    echo "ERROR: Auth key cannot be empty"
    exit 1
fi

# Add a new version (previous versions are automatically disabled)
echo -n "${TS_KEY}" | gcloud secrets versions add "${SECRET_ID}" \
    --project="${PROJECT_ID}" \
    --data-file=-

echo ""
echo "Auth key saved to Secret Manager (${SECRET_ID})"
echo "The GCE instance will read it at next boot via its service account."
