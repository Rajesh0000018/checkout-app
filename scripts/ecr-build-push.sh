#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${1:-}"
ACCOUNT_ID="${2:-}"
AWS_REGION="${3:-eu-west-2}"
TAG="${4:-v1}"

if [[ -z "$APP_ROOT" || -z "$ACCOUNT_ID" ]]; then
  echo "Usage: $0 /path/to/checkout-app AWS_ACCOUNT_ID [region] [tag]"
  exit 1
fi

SERVICES=(gateway checkout pricing inventory quote)
REGISTRY="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

for svc in "${SERVICES[@]}"; do
  aws ecr describe-repositories --repository-names "$svc" --region "$AWS_REGION" >/dev/null 2>&1 || \
    aws ecr create-repository --repository-name "$svc" --region "$AWS_REGION" >/dev/null
 done

aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$REGISTRY"

for svc in "${SERVICES[@]}"; do
  echo "=== Building ${svc}:${TAG} ==="
  docker build -t "${svc}:${TAG}" "${APP_ROOT}/${svc}"
  docker tag "${svc}:${TAG}" "${REGISTRY}/${svc}:${TAG}"
  echo "=== Pushing ${REGISTRY}/${svc}:${TAG} ==="
  docker push "${REGISTRY}/${svc}:${TAG}"
done

echo "Done. Export these before deploy:"
echo "export IMAGE_REGISTRY=${REGISTRY}"
echo "export IMAGE_TAG=${TAG}"
