#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# PROOF: in Mode 2, agent egress reaches the sidecar because of iptables — NOT
# because of HTTP_PROXY. The agent runs with NO proxy env at all; interception is
# the iptables REDIRECT alone. A flush/restore control proves iptables is the
# mechanism: with rules flushed, a denied host becomes reachable again.
#
# Requires: Linux host with NET_ADMIN (a real VM — not Docker Desktop), root
# (for nsenter), docker compose, nsenter + iptables on the host, and a .env with
# ANTHROPIC_API_KEY + SOE creds (SOE_API_TOKEN or SOE_API_KEY) + SOE_TENANT_ID.
#
#   sudo -E bash tests/iptables-interception-test.sh
#
# iptables ops are driven from the HOST via `nsenter` into the agent's network
# namespace — the host is not behind the REDIRECT, so it can flush/restore freely.
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
CF="docker compose -f docker-compose.transparent.yml"
ALLOW_URL="https://api.anthropic.com/v1/messages"   # on the egress allow-list
DENY_URL="https://example.com"                        # reachable everywhere; on the deny-list
fail=0
pass(){ echo "  PASS: $*"; }
bad(){ echo "  FAIL: $*"; fail=1; }

[ "$(id -u)" = 0 ] || { echo "must run as root (sudo) — nsenter needs it"; exit 2; }
command -v nsenter  >/dev/null || { echo "nsenter required (util-linux)"; exit 2; }
command -v iptables >/dev/null || apt-get install -y -q iptables >/dev/null 2>&1 || true

agent_pid(){ docker inspect -f '{{.State.Pid}}' lending-agent 2>/dev/null; }
# Run a command inside the agent's NET namespace using the HOST's tools.
in_netns(){ nsenter -t "$(agent_pid)" -n sh -c "$1" 2>/dev/null; }
# Probe a URL from INSIDE the agent container (which has no proxy env).
probe(){ $CF exec -T lending-agent python -c '
import httpx,sys
try:
    r=httpx.get(sys.argv[1],timeout=8); print("REACHED",r.status_code)
except Exception as e:
    print("BLOCKED",type(e).__name__)' "$1" 2>/dev/null; }

echo "== bring up transparent stack (iptables interception, NO proxy env) =="
$CF up --build -d >/dev/null 2>&1
sleep 14

echo "== [1] agent must have NO HTTP(S)_PROXY env =="
penv=$($CF exec -T lending-agent printenv 2>/dev/null | grep -iE '^https?_proxy=' || true)
[ -z "$penv" ] && pass "no HTTP(S)_PROXY in agent env" || bad "proxy env present: $penv"

echo "== [2] iptables REDIRECT rules active in agent netns =="
in_netns "iptables -t nat -L SOE_OUT -n --line-numbers"

echo "== [3] probe with iptables ACTIVE (interception via iptables only) =="
a=$(probe "$ALLOW_URL"); echo "    allow  $ALLOW_URL -> $a"
d=$(probe "$DENY_URL");  echo "    deny   $DENY_URL  -> $d"
echo "$a" | grep -q REACHED && pass "allow-listed host reached (sidecar forwarded)" || bad "allow-listed host not reached"
echo "$d" | grep -q BLOCKED && pass "deny-listed host blocked (sidecar denied)"     || bad "deny-listed host NOT blocked"

echo "== [4] CONTROL: flush iptables (host nsenter), re-probe the denied host =="
in_netns "iptables -t nat -F SOE_OUT"
d2=$(probe "$DENY_URL"); echo "    deny host after FLUSH -> $d2"
echo "$d2" | grep -q REACHED && pass "flush -> reachable (PROVES iptables was the interceptor)" \
  || bad "still blocked after flush (interception not attributable to iptables)"

echo "== [5] restore rules, confirm blocked again =="
in_netns "env SIDECAR_PORT=15001 SIDECAR_UID=1337 sh '$PWD/iptables-init/init.sh'" >/dev/null 2>&1
d3=$(probe "$DENY_URL"); echo "    deny host after RESTORE -> $d3"
echo "$d3" | grep -q BLOCKED && pass "restore -> blocked again" || bad "not blocked after restore"

echo ""
if [ $fail -eq 0 ]; then
  echo "RESULT: ALL PASS — Mode-2 interception is enforced by iptables, independent of HTTP_PROXY."
else
  echo "RESULT: FAILURES above."
fi
echo "(teardown: $CF down -v)"
exit $fail
