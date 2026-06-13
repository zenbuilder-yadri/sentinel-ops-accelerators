#!/usr/bin/env bash
# Comprehensive test harness for both lending demos. Captures results to
# docs/TEST-RESULTS.md.
#
# Auth: SOE_JWT (Mode 1) and SOE_API_KEY (sok_, Mode 2). ANTHROPIC_API_KEY for both.
# Env:  SOE_API_URL, SOE_TENANT_ID.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
M1="$ROOT/mode1-sdk/lending-advisor"
M2="$ROOT/mode2-sidecar/lending-assistant"
OUT="$ROOT/docs/TEST-RESULTS.md"
# Auto-load a .env so creds/keys flow into both modes without manual export.
for E in "$ROOT/.env" "./.env"; do [ -f "$E" ] && { set -a; . "$E"; set +a; break; }; done
: "${SOE_API_URL:=https://api.yadriworks.ai}"
: "${SOE_TENANT_ID:=yadriworks-demo}"
STAMP="${RESULTS_STAMP:-$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo unknown)}"

mkdir -p "$ROOT/docs"
{
  echo "# Lending Demos — Test Results"
  echo ""
  echo "- Date: $STAMP"
  echo "- Control plane: $SOE_API_URL (tenant \`$SOE_TENANT_ID\`)"
  echo ""
} > "$OUT"

echo "==> [0/3] control-plane health"
curl -sS -m 12 "$SOE_API_URL/v1/health" | tee -a "$OUT"; echo "" >> "$OUT"

echo "==> [1/3] deploy SOEs"
SOE_JWT="${SOE_JWT:-}" SOE_API_KEY="${SOE_API_KEY:-}" \
  "$ROOT/bin/deploy-soe.sh" 2>&1 | tee -a "$OUT"

echo "==> [2/3] Mode 1 (SDK) — all scenarios"
{
  echo ""; echo "## Mode 1 (SDK) — lending-advisor"; echo '```'
} >> "$OUT"
( cd "$M1" && python3 agent.py --scenario all ) 2>&1 | tee -a "$OUT"
echo '```' >> "$OUT"

echo "==> [3/3] Mode 2 (sidecar) — bring up + attack"
{
  echo ""; echo "## Mode 2 (sidecar) — lending-assistant"; echo '```'
} >> "$OUT"
( cd "$M2" && docker compose up --build -d ) 2>&1 | tee -a "$OUT"
echo "    (waiting 25s for sidecar + agent to be healthy)"; sleep 25
python3 "$M2/scenarios/attack.py" --container lending-agent \
  --json "$ROOT/docs/mode2-results.json" 2>&1 | tee -a "$OUT"
echo '```' >> "$OUT"
( cd "$M2" && docker compose down -v ) >/dev/null 2>&1 || true

echo ""; echo "Results written to $OUT"
