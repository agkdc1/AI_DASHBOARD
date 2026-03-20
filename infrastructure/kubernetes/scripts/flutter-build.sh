#!/bin/bash
# =============================================================================
# Flutter Build Wrapper
# Creates a K8s Job to build Flutter web/Android artifacts.
# Usage: sudo ./flutter-build.sh <git-repo-url> [branch] [targets]
#   branch   defaults to "main"
#   targets  defaults to "web,apk" (comma-separated: web, apk, aab)
# =============================================================================
set -euo pipefail

KUBECONFIG="${KUBECONFIG:-/etc/rancher/k3s/k3s.yaml}"
NAMESPACE="shinbee"
IMAGE="asia-northeast1-docker.pkg.dev/your-gcp-project-id/shinbee/flutter-builder:latest"

usage() {
  echo "Usage: sudo $0 <git-repo-url> [branch] [targets]"
  echo "  branch   defaults to 'main'"
  echo "  targets  defaults to 'web,apk' (comma-separated: web, apk, aab)"
  exit 1
}

[[ $# -lt 1 ]] && usage

GIT_REPO="$1"
GIT_BRANCH="${2:-main}"
BUILD_TARGETS="${3:-web,apk}"
JOB_NAME="flutter-build-$(date +%Y%m%d-%H%M%S)"

echo "Creating Job: ${JOB_NAME}"
echo "  Repo:    ${GIT_REPO}"
echo "  Branch:  ${GIT_BRANCH}"
echo "  Targets: ${BUILD_TARGETS}"
echo

kubectl --kubeconfig="${KUBECONFIG}" -n "${NAMESPACE}" apply -f - <<EOF
apiVersion: batch/v1
kind: Job
metadata:
  name: ${JOB_NAME}
  namespace: ${NAMESPACE}
  labels:
    app.kubernetes.io/name: flutter-builder
spec:
  backoffLimit: 0
  ttlSecondsAfterFinished: 86400
  template:
    metadata:
      labels:
        app.kubernetes.io/name: flutter-builder
    spec:
      nodeSelector:
        kubernetes.io/arch: amd64
      affinity:
        nodeAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
            - weight: 100
              preference:
                matchExpressions:
                  - key: kubernetes.io/hostname
                    operator: In
                    values:
                      - node-a5dd21
      containers:
        - name: flutter-builder
          image: ${IMAGE}
          env:
            - name: GIT_REPO
              value: "${GIT_REPO}"
            - name: GIT_BRANCH
              value: "${GIT_BRANCH}"
            - name: BUILD_TARGETS
              value: "${BUILD_TARGETS}"
            - name: GCS_BUCKET
              value: "your-project-flutter-artifacts"
            - name: GCS_PREFIX
              value: "flutter-builds"
          resources:
            requests:
              memory: "2Gi"
              cpu: "1"
            limits:
              memory: "3Gi"
              cpu: "3"
          volumeMounts:
            - name: gcs-key
              mountPath: /etc/gcs
              readOnly: true
            - name: build-cache
              mountPath: /cache
      volumes:
        - name: gcs-key
          secret:
            secretName: backup-gcs-secret
        - name: build-cache
          persistentVolumeClaim:
            claimName: flutter-build-cache
      restartPolicy: Never
EOF

echo
echo "Job created. Follow logs with:"
echo "  sudo KUBECONFIG=${KUBECONFIG} kubectl -n ${NAMESPACE} logs -f job/${JOB_NAME}"
