#!/usr/bin/env bash
set -euo pipefail

MANIFEST_DIR="${1:-../manifests}"
: "${IMAGE_REGISTRY:?Set IMAGE_REGISTRY first}"
: "${IMAGE_TAG:?Set IMAGE_TAG first}"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

render_file() {
  local src="$1"
  local dst="$2"
  sed \
    -e "s#__IMAGE_REGISTRY__#${IMAGE_REGISTRY}#g" \
    -e "s#__IMAGE_TAG__#${IMAGE_TAG}#g" \
    "$src" > "$dst"
}

for f in "$MANIFEST_DIR"/*.yaml; do
  render_file "$f" "$TMP_DIR/$(basename "$f")"
done

echo "=== Applying namespace/config/data layer ==="
kubectl apply -f "$TMP_DIR/00-namespace.yaml"
kubectl apply -f "$TMP_DIR/01-configmap.yaml"
kubectl apply -f "$TMP_DIR/02-secret.yaml"
kubectl apply -f "$TMP_DIR/03-postgres-pvc.yaml"
kubectl apply -f "$TMP_DIR/04-postgres-deployment.yaml"
kubectl apply -f "$TMP_DIR/05-postgres-service.yaml"

echo "=== Waiting for Postgres rollout ==="
kubectl rollout status deployment/postgres -n shop --timeout=180s

echo "=== Applying application services ==="
for f in \
  10-pricing-deployment.yaml 11-pricing-service.yaml \
  12-inventory-deployment.yaml 13-inventory-service.yaml \
  14-checkout-deployment.yaml 15-checkout-service.yaml \
  16-gateway-deployment.yaml 17-gateway-service.yaml \
  18-quote-deployment.yaml 19-quote-service.yaml \
  20-ingress.yaml 21-toolbox.yaml; do
  kubectl apply -f "$TMP_DIR/$f"
done

echo "=== Waiting for app rollouts ==="
for deploy in pricing inventory checkout gateway quote; do
  kubectl rollout status deployment/$deploy -n shop --timeout=180s
done

echo "=== Current state ==="
kubectl get pods,svc,ingress,pvc -n shop
