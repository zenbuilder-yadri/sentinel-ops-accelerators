#!/bin/sh
# ─────────────────────────────────────────────────────────────────────────
# Mode 2 — iptables NAT REDIRECT initContainer (reference implementation)
#
# For the docker-compose demo we use HTTP_PROXY env-var routing because it
# is the simplest, most portable steering primitive (works on Mac, Linux,
# and Docker Desktop without privileged kernels). This script exists to
# show the "real" Kubernetes deployment style for fleets that cannot rely
# on HTTP_PROXY — Go binaries, JVM apps, anything that ignores HTTPS_PROXY.
#
# In a real Pod this would run as an `initContainer` with NET_ADMIN before
# the agent container starts, so all egress from the shared netns
# transparently hits port 15001 without the agent knowing.
#
# Usage (compose):
#   docker compose --profile iptables up iptables-init
# Usage (Kubernetes — see deploy/k8s/pilotpilot-pod.yaml for the real spec).
# ─────────────────────────────────────────────────────────────────────────
set -eu

SIDECAR_PORT="${SIDECAR_PORT:-15001}"
SIDECAR_UID="${SIDECAR_UID:-1337}"   # in real pod, sidecar runs as this UID

# Skip in dev if the toolchain is missing — keeps `docker compose up` honest.
if ! command -v iptables >/dev/null 2>&1; then
  apk add --no-cache iptables >/dev/null 2>&1 || true
fi

echo "[iptables-init] redirecting tcp egress -> ${SIDECAR_PORT}"

# Bypass loopback + the sidecar's own egress.
iptables -t nat -N SOE_OUT 2>/dev/null || true
iptables -t nat -F SOE_OUT
iptables -t nat -A SOE_OUT -m owner --uid-owner "${SIDECAR_UID}" -j RETURN
iptables -t nat -A SOE_OUT -d 127.0.0.1/32 -j RETURN
iptables -t nat -A SOE_OUT -p tcp --dport 80  -j REDIRECT --to-port "${SIDECAR_PORT}"
iptables -t nat -A SOE_OUT -p tcp --dport 443 -j REDIRECT --to-port "${SIDECAR_PORT}"

# Hook OUTPUT once.
if ! iptables -t nat -C OUTPUT -p tcp -j SOE_OUT 2>/dev/null; then
  iptables -t nat -A OUTPUT -p tcp -j SOE_OUT
fi

echo "[iptables-init] done. rules:"
iptables -t nat -L SOE_OUT --line-numbers -n
