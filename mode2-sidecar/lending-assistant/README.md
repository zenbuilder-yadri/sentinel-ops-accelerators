# LendingAssistant — Mode 2 (transparent sidecar)

A consumer-lending loan-officer agent (LangGraph + Anthropic) governed with
**zero code changes**. The agent reaches the credit bureau, the loan-origination
system, the mail relay, and the LLM — and **nothing else**. Even a fully
prompt-injected agent cannot exfiltrate applicant PII, because containment
happens at the network egress, not in the agent.

## Run

```bash
cp .env.example .env        # SOE_API_KEY (sok_...), ANTHROPIC_API_KEY
docker compose up --build -d
python scenarios/attack.py  # drives the chat backend, asserts ALLOW/DENY
docker compose down -v
```

## What the harness proves

| Scenario | Egress target | Expect |
|---|---|---|
| L-S1 pull credit report | credit bureau | **ALLOW** |
| L-S2 eligibility check | loan-origination system | **ALLOW** |
| L-S3 injection → exfil | `attacker.example` | **DENY** |
| L-S4 SSRF | `169.254.169.254` (metadata) | **DENY** |
| L-S5 data staging | `pastebin.com` | **DENY** |

The agent reaching the LLM at all proves `api.anthropic.com` is allow-listed.

## Two steering mechanisms — iptables is primary, HTTP_PROXY is the fallback

| | Transparent (primary) | HTTP_PROXY (fallback) |
|---|---|---|
| Compose file | `docker-compose.transparent.yml` | `docker-compose.yml` |
| Agent config | **none** — zero proxy env | `HTTP_PROXY=…:15001` |
| Mechanism | iptables `REDIRECT :80/:443 → :15001` (shared netns, like a K8s pod) | app honors proxy env |
| Bypass-resistance | **enforced** — works even for Go/JVM/static binaries that ignore proxy env | cooperative — an app can ignore it |
| Needs | `NET_ADMIN` | nothing |

The transparent path is the real zero-trust control; `HTTP_PROXY` is only a
fallback for environments where `NET_ADMIN`/iptables aren't available.

The SOE (`soe-definitions/lending-assistant-mode2.soe.json`, named for the
agentId — the sidecar loads policy by that filename) declares the egress
allow/deny lists; the sidecar enforces them on every connection.

## Proof: interception is iptables, not the proxy

`tests/iptables-interception-test.sh` runs the agent with **no proxy env**, shows
the iptables rules, confirms allow/deny still holds, then **flushes** iptables and
shows the denied host becomes reachable (proving iptables was the interceptor),
then restores. Requires a real Linux host with `NET_ADMIN` (not Docker Desktop):

```bash
docker compose -f docker-compose.transparent.yml up --build -d
sudo -E bash tests/iptables-interception-test.sh    # ALL PASS
```

See [`docs/TEST-RESULTS.md`](../../docs/TEST-RESULTS.md) for a captured run.

## Files

```
app/                vanilla agent image (BYO Dockerfile) — zero SOE references
mock-services/      mock bureau / LOS / mail (synthetic, one image)
soe-definitions/    lending-assistant-mode2.soe.json (transport.network allow/deny)
docker-compose.yml  agent + soe-sidecar + 3 mocks
scenarios/attack.py stdlib attack harness
```

## In production (Kubernetes)

Use `deploy/helm/sentinel-ops-sidecar` to inject the same sidecar in-pod next to
your existing image — see the repo root README.
