#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${1:-}"
DOCKERHUB_USER="${2:-}"
TAG="${3:-v1}"

if [[ -z "$APP_ROOT" || -z "$DOCKERHUB_USER" ]]; then
  echo "Usage: $0 /path/to/checkout-app DOCKERHUB_USERNAME [tag]"
  exit 1
fi

SERVICES=(gateway checkout pricing inventory quote)

for svc in "${SERVICES[@]}"; do
  echo "=== Building ${DOCKERHUB_USER}/${svc}:${TAG} ==="
  docker build -t "${DOCKERHUB_USER}/${svc}:${TAG}" "${APP_ROOT}/${svc}"
  echo "=== Pushing ${DOCKERHUB_USER}/${svc}:${TAG} ==="
  docker push "${DOCKERHUB_USER}/${svc}:${TAG}"
done

echo "Done. Export these before deploy:"
echo "export IMAGE_REGISTRY=docker.io/${DOCKERHUB_USER}"
echo "export IMAGE_TAG=${TAG}"
