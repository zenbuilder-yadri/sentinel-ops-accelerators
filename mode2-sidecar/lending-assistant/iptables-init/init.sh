#!/bin/sh
# ─────────────────────────────────────────────────────────────────────────
# Mode 2 — transparent egress interception via iptables NAT REDIRECT.
#
# This is the PRIMARY, non-cooperative steering mechanism: it redirects all
# outbound TCP on ports 80/443 to the sidecar regardless of whether the agent
# honors HTTP_PROXY. (HTTP_PROXY is only a cooperative fallback for environments
# where NET_ADMIN / iptables are unavailable.)
#
# Runs as an initContainer (K8s) or a network_mode:service container (compose)
# that shares the agent's network namespace, with NET_ADMIN, before traffic flows.
# The sidecar (running as SIDECAR_UID) is excluded so its own forwarded egress
# is not re-redirected into an infinite loop.
# ─────────────────────────────────────────────────────────────────────────
set -eu

SIDECAR_PORT="${SIDECAR_PORT:-15001}"
SIDECAR_UID="${SIDECAR_UID:-1337}"

command -v iptables >/dev/null 2>&1 || apk add --no-cache iptables >/dev/null 2>&1 || true

echo "[iptables-init] redirecting tcp egress :80,:443 -> :${SIDECAR_PORT} (excluding uid ${SIDECAR_UID})"

iptables -t nat -N SOE_OUT 2>/dev/null || true
iptables -t nat -F SOE_OUT
# Never redirect the sidecar's own egress (prevents loop), or loopback.
iptables -t nat -A SOE_OUT -m owner --uid-owner "${SIDECAR_UID}" -j RETURN
iptables -t nat -A SOE_OUT -d 127.0.0.1/32 -j RETURN
# Redirect everything else on 80/443 to the sidecar.
iptables -t nat -A SOE_OUT -p tcp --dport 80  -j REDIRECT --to-port "${SIDECAR_PORT}"
iptables -t nat -A SOE_OUT -p tcp --dport 443 -j REDIRECT --to-port "${SIDECAR_PORT}"

# Hook OUTPUT once (idempotent).
if ! iptables -t nat -C OUTPUT -p tcp -j SOE_OUT 2>/dev/null; then
  iptables -t nat -A OUTPUT -p tcp -j SOE_OUT
fi

echo "[iptables-init] active rules:"
iptables -t nat -L SOE_OUT --line-numbers -n
