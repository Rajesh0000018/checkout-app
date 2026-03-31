#!/usr/bin/env bash
set -euo pipefail

say() { printf '\n=== %s ===\n' "$1"; }

say "Query checkout_audit before restart"
kubectl exec -it deploy/postgres -n shop -- psql -U checkoutuser -d checkoutdb -c "SELECT * FROM checkout_audit;"

say "Restart Postgres"
kubectl rollout restart deployment/postgres -n shop
kubectl rollout status deployment/postgres -n shop --timeout=180s

say "Query checkout_audit after restart"
kubectl exec -it deploy/postgres -n shop -- psql -U checkoutuser -d checkoutdb -c "SELECT * FROM checkout_audit;"
