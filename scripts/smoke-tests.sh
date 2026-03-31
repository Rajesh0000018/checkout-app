#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-}"
if [[ -z "$BASE_URL" ]]; then
  echo "Usage: $0 http://YOUR_PUBLIC_URL"
  exit 1
fi

say() { printf '\n=== %s ===\n' "$1"; }

say "Gateway health"
curl -sS "${BASE_URL}/health"; echo

say "Ping"
curl -sS "${BASE_URL}/api/ping"; echo

say "Architecture"
curl -sS "${BASE_URL}/api/arch"; echo

say "Quote"
curl -sS "${BASE_URL}/api/quote?sku=SKU-001&quantity=2"; echo

say "Happy path checkout"
curl -sS -X POST "${BASE_URL}/api/checkout" \
  -H 'Content-Type: application/json' \
  -H 'X-Request-Id: req-happy-001' \
  -d '{"customerId":"cust-101","sku":"SKU-001","quantity":2}'; echo

say "Out-of-stock checkout"
curl -sS -X POST "${BASE_URL}/api/checkout" \
  -H 'Content-Type: application/json' \
  -H 'X-Request-Id: req-oos-001' \
  -d '{"customerId":"cust-101","sku":"SKU-999","quantity":2}'; echo
