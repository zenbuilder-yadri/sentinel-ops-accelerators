#!/usr/bin/env bash
# Deploy the lending SOE definitions to a Sentinel-Ops tenant.
#
# Auth: either SOE_JWT (Bearer) OR SOE_API_KEY (sok_, with SOE_TENANT_ID).
# Env:  SOE_API_URL (default https://api.yadriworks.ai), SOE_TENANT_ID.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
: "${SOE_API_URL:=https://api.yadriworks.ai}"
: "${SOE_TENANT_ID:?set SOE_TENANT_ID}"

if [ -n "${SOE_JWT:-}" ]; then
  AUTH=(-H "Authorization: Bearer $SOE_JWT" -H "X-SOE-Tenant-Id: $SOE_TENANT_ID")
elif [ -n "${SOE_API_KEY:-}" ]; then
  AUTH=(-H "X-SOE-Api-Key: $SOE_API_KEY" -H "X-SOE-Tenant-Id: $SOE_TENANT_ID")
else
  echo "set SOE_JWT or SOE_API_KEY"; exit 1
fi

DEFS=(
  "$ROOT/mode1-sdk/lending-advisor/soe-definitions/lending-advisor.soe.json"
  "$ROOT/mode2-sidecar/lending-assistant/soe-definitions/lending-assistant.soe.json"
)
for f in "${DEFS[@]}"; do
  [ -f "$f" ] || { echo "skip (missing): $f"; continue; }
  python3 -c "import json;print(json.dumps({'soe':json.load(open('$f'))}))" > /tmp/soe-wrap.json
  code=$(curl -sS -o /tmp/soe-deploy.json -w '%{http_code}' \
    -X POST "$SOE_API_URL/v1/deploy" "${AUTH[@]}" \
    -H 'Content-Type: application/json' --data-binary @/tmp/soe-wrap.json)
  if [ "$code" = "200" ] || [ "$code" = "201" ]; then
    echo "✓ deployed $(basename "$f") (HTTP $code)"
  else
    echo "✗ $(basename "$f") failed (HTTP $code):"; cat /tmp/soe-deploy.json; exit 1
  fi
done
echo "done."
