#!/bin/bash
# =============================================================================
# Flutter Build Entrypoint
# Clones a Flutter project, builds specified targets, uploads to GCS.
# Runs as a K8s Job container.
# =============================================================================
set -euo pipefail

log()  { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
ok()   { echo "[$(date '+%Y-%m-%d %H:%M:%S')]   OK: $*"; }
err()  { echo "[$(date '+%Y-%m-%d %H:%M:%S')]   ERROR: $*" >&2; }
die()  { err "$*"; exit 1; }

# ---------------------------------------------------------------------------
# Required / optional environment variables
# ---------------------------------------------------------------------------
: "${GIT_REPO:?GIT_REPO is required}"
: "${GIT_BRANCH:=main}"
: "${BUILD_TARGETS:=web}"
: "${GCS_BUCKET:?GCS_BUCKET is required}"
: "${GCS_PREFIX:=flutter-builds}"
: "${FLUTTER_SUBDIR:=.}"

# Use persistent cache if mounted, otherwise /tmp
export PUB_CACHE="${PUB_CACHE:-/cache/pub}"
export GRADLE_USER_HOME="${GRADLE_USER_HOME:-/cache/gradle}"

WORK_DIR="/tmp/flutter-build"

log "=== Flutter Build ==="
log "Repo:    ${GIT_REPO} (branch: ${GIT_BRANCH})"
log "Targets: ${BUILD_TARGETS}"
log "Bucket:  gs://${GCS_BUCKET}/${GCS_PREFIX}"

# ---------------------------------------------------------------------------
# 1. Authenticate to GCS
# ---------------------------------------------------------------------------
if [[ -f /etc/gcs/key.json ]]; then
  log "Authenticating to GCS..."
  gcloud auth activate-service-account --key-file=/etc/gcs/key.json --quiet
  ok "GCS authenticated"
else
  die "GCS service account key not found at /etc/gcs/key.json"
fi

# ---------------------------------------------------------------------------
# 2. Clone repository
# ---------------------------------------------------------------------------
log "Cloning ${GIT_REPO}..."
rm -rf "${WORK_DIR}"
git clone --depth 1 --branch "${GIT_BRANCH}" "${GIT_REPO}" "${WORK_DIR}"

cd "${WORK_DIR}/${FLUTTER_SUBDIR}"
COMMIT=$(git rev-parse --short HEAD)
log "Commit: ${COMMIT}"

# ---------------------------------------------------------------------------
# 3. Flutter pub get + l10n
# ---------------------------------------------------------------------------
log "Running flutter pub get..."
flutter pub get
ok "Dependencies resolved"

log "Generating l10n..."
flutter gen-l10n || true
ok "l10n generated"

# ---------------------------------------------------------------------------
# 4. Build each target
# ---------------------------------------------------------------------------
UPLOAD_DIR="/tmp/flutter-artifacts"
rm -rf "${UPLOAD_DIR}"
mkdir -p "${UPLOAD_DIR}"

IFS=',' read -ra TARGETS <<< "${BUILD_TARGETS}"
for target in "${TARGETS[@]}"; do
  target=$(echo "$target" | xargs)  # trim whitespace
  case "$target" in
    web)
      log "Building web..."
      flutter build web --release
      tar -czf "${UPLOAD_DIR}/web.tar.gz" -C build/web .
      ok "Web build complete"
      ;;
    apk)
      log "Building APK..."
      flutter build apk --release
      cp build/app/outputs/flutter-apk/app-release.apk "${UPLOAD_DIR}/app-release.apk"
      ok "APK build complete"
      ;;
    aab)
      log "Building AAB..."
      flutter build appbundle --release
      cp build/app/outputs/bundle/release/app-release.aab "${UPLOAD_DIR}/app-release.aab"
      ok "AAB build complete"
      ;;
    *)
      err "Unknown target: ${target} (supported: web, apk, aab)"
      exit 1
      ;;
  esac
done

# ---------------------------------------------------------------------------
# 5. Upload artifacts to GCS
# ---------------------------------------------------------------------------
DEST="gs://${GCS_BUCKET}/${GCS_PREFIX}/${COMMIT}"
LATEST="gs://${GCS_BUCKET}/${GCS_PREFIX}/latest"
log "Uploading artifacts to ${DEST}/..."

for artifact in "${UPLOAD_DIR}"/*; do
  [[ -f "$artifact" ]] || continue
  name=$(basename "$artifact")
  log "  Uploading ${name}..."
  gcloud storage cp "$artifact" "${DEST}/${name}" --quiet
  # Also copy to latest/ for deployment init container
  gcloud storage cp "$artifact" "${LATEST}/${name}" --quiet
done

ok "All artifacts uploaded to ${DEST}/ and ${LATEST}/"

log "=== Flutter Build complete ==="
