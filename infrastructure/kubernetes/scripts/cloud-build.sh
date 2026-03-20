#!/usr/bin/env bash
# cloud-build.sh — Build Docker images via GCP Cloud Build
#
# Usage:
#   ./cloud-build.sh [image...]    # Build specific images (default: all)
#   ./cloud-build.sh ai-assistant  # Build only ai-assistant
#   ./cloud-build.sh --list        # List available images
#
# Requires: gcloud, GOOGLE_APPLICATION_CREDENTIALS or gcloud auth

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
GCP_PROJECT="your-gcp-project-id"
REGISTRY="asia-northeast1-docker.pkg.dev/${GCP_PROJECT}/shinbee"
TAG="${TAG:-latest}"

export GOOGLE_APPLICATION_CREDENTIALS="${GOOGLE_APPLICATION_CREDENTIALS:-/home/pi/keys/fax-terraform-deploy.json}"

# Available images and their build contexts
declare -A IMAGE_DOCKERFILE=(
    [selenium-daemon]="infrastructure/kubernetes/images/selenium-daemon/Dockerfile"
    [rakuten-renewal]="infrastructure/kubernetes/images/rakuten-renewal/Dockerfile"
    [backup]="infrastructure/kubernetes/images/backup/Dockerfile"
    [ai-assistant]="services/ai-assistant/Dockerfile"
    [flutter-builder]="infrastructure/kubernetes/images/flutter-builder/Dockerfile"
    [playwright-test]="infrastructure/kubernetes/images/playwright-test/Dockerfile"
    [asterisk-core]="infrastructure/kubernetes/images/asterisk-core/Dockerfile"
    [asterisk-headless]="infrastructure/kubernetes/images/asterisk-headless/Dockerfile"
    [faxapi]="infrastructure/kubernetes/images/faxapi/Dockerfile"
    [mail2fax]="infrastructure/kubernetes/images/mail2fax/Dockerfile"
    [samba-ad-dc]="infrastructure/kubernetes/images/samba-ad-dc/Dockerfile"
    [samba-fileserver]="infrastructure/kubernetes/images/samba-fileserver/Dockerfile"
    [google-workspace-sync]="infrastructure/kubernetes/images/google-workspace-sync/Dockerfile"
)
declare -A IMAGE_CONTEXT=(
    [selenium-daemon]="."
    [rakuten-renewal]="."
    [backup]="infrastructure/kubernetes/images/backup/"
    [ai-assistant]="services/ai-assistant/"
    [flutter-builder]="infrastructure/kubernetes/images/flutter-builder/"
    [playwright-test]="infrastructure/kubernetes/images/playwright-test/"
    [asterisk-core]="."
    [asterisk-headless]="."
    [faxapi]="."
    [mail2fax]="."
    [samba-ad-dc]="infrastructure/kubernetes/images/samba-ad-dc/"
    [samba-fileserver]="infrastructure/kubernetes/images/samba-fileserver/"
    [google-workspace-sync]="infrastructure/kubernetes/images/google-workspace-sync/"
)

if [ "${1:-}" = "--list" ]; then
    echo "Available images:"
    for img in "${!IMAGE_DOCKERFILE[@]}"; do
        echo "  ${img}"
    done | sort
    exit 0
fi

# Determine which images to build
IMAGES=("$@")
if [ ${#IMAGES[@]} -eq 0 ]; then
    echo "Building ALL images via Cloud Build..."
    cd "${REPO_ROOT}"
    gcloud builds submit \
        --config=cloudbuild.yaml \
        --substitutions="_TAG=${TAG}" \
        --project="${GCP_PROJECT}" \
        .
    exit $?
fi

# Build individual images
cd "${REPO_ROOT}"
for img in "${IMAGES[@]}"; do
    if [ -z "${IMAGE_DOCKERFILE[$img]:-}" ]; then
        echo "ERROR: Unknown image '${img}'. Use --list to see available images."
        exit 1
    fi
    echo "=== Building ${img} ==="
    context="${IMAGE_CONTEXT[$img]}"
    dockerfile="${IMAGE_DOCKERFILE[$img]}"
    image_tag="${REGISTRY}/${img}:${TAG}"
    # Make Dockerfile path relative to context (Cloud Build uploads context as workspace root)
    if [[ "${context}" != "." ]]; then
        # Strip context prefix from Dockerfile path
        rel_dockerfile="${dockerfile#${context}}"
    else
        rel_dockerfile="${dockerfile}"
    fi
    # Use inline cloudbuild config to support -f (Dockerfile outside context root)
    gcloud builds submit \
        --config=/dev/stdin \
        --project="${GCP_PROJECT}" \
        --gcs-log-dir="gs://your-project-flutter-artifacts/build-logs" \
        "${context}" <<CBEOF
steps:
  - name: gcr.io/cloud-builders/docker
    args: ['build', '--platform=linux/amd64', '-t', '${image_tag}', '-f', '${rel_dockerfile}', '.']
images: ['${image_tag}']
options:
  machineType: E2_HIGHCPU_8
CBEOF
    echo "=== ${img} done ==="
done
