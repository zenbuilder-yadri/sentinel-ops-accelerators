# LendingAssistant — Mode 2 (transparent sidecar)

A consumer-lending loan-officer agent (LangGraph + Anthropic) governed with
**zero code changes**. The agent reaches the credit bureau, the loan-origination
system, the mail relay, and the LLM — and **nothing else**. Even a fully
prompt-injected agent cannot exfiltrate applicant PII, because containment
happens at the network egress, not in the agent.

## Run

```bash
cp .env.example .env        # ANTHROPIC_API_KEY (+ optional control-plane creds — see Authentication)
docker compose up --build -d
python scenarios/attack.py  # deterministic egress matrix (allow LLM, deny exfil/SSRF/C2)
docker compose down -v
```

## What the harness proves

`scenarios/attack.py` is a **deterministic** egress matrix — it probes a fixed set
of hosts from inside the agent container and checks the sidecar's verdict. It does
**not** depend on the LLM choosing to call a malicious tool. The sidecar runs in
**whitelist mode**: only allow-listed hosts are reachable; everything else is
denied by default.

| Host | Class | Expect |
|---|---|---|
| `api.anthropic.com` | LLM provider (allow-listed) | **ALLOW** |
| `attacker.example` | exfiltration callback | **DENY** |
| `169.254.169.254` / `metadata.google.internal` | cloud metadata (SSRF) | **DENY** |
| `pastebin.com` / `transfer.sh` / `webhook.site` | paste / file-transfer / webhook exfil | **DENY** |
| `api.telegram.org` / `discord.com` | messaging C2 / exfil | **DENY** |
| `raw.githubusercontent.com` / `example.com` / `1.1.1.1` | any non-allow-listed host / raw IP | **DENY** |

12 targets, 1 allow / 11 deny — all denials are by **default-deny whitelist**, not
a hand-maintained blocklist. `scenarios/demo_chat.py` is a separate *illustrative*
chat narrative (not a pass/fail test — a safety-trained model may decline on its own).

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

## Authentication

Two separate concerns — don't conflate them:

1. **Egress allow/deny (the containment proof) needs NO credentials.** The sidecar
   decides every connection **locally** from the mounted SOE's `transport.network`
   rules. So `scenarios/attack.py` and `tests/iptables-interception-test.sh` run
   with zero control-plane auth (no tokens needed to reproduce the proof). A
   captured live run is in [`docs/TEST-RESULTS.md`](../../docs/TEST-RESULTS.md).
2. **Control-plane reporting (audit trail, tool-eval, central policy) needs a tenant credential.** Provide one of:
   - `SOE_API_TOKEN=<jwt>` — a Bearer JWT (fine for demos; ~24h lifetime).
   - `SOE_API_KEY=sok_…` — a long-lived API key. **Minting a `sok_` key requires the
     `admin` role on the tenant** (an `editor` cannot). On your own tenant you have
     admin: mint via the dashboard or `POST /v1/auth/tenants/<id>/api-keys`.

To deploy the SOE to a tenant: `bin/deploy-soe.sh` accepts either `SOE_JWT` or
`SOE_API_KEY` (with `SOE_TENANT_ID`).

## Files

```
app/                          vanilla agent image (BYO Dockerfile) — zero SOE references
mock-services/                mock bureau / LOS / mail (synthetic, one image)
soe-definitions/              lending-assistant-mode2.soe.json (transport.network allow/deny)
docker-compose.yml            HTTP_PROXY steering (cooperative fallback)
docker-compose.transparent.yml iptables interception (primary) — sidecar shares agent netns
iptables-init/init.sh         NAT REDIRECT :80/:443 -> sidecar
scenarios/attack.py           deterministic egress matrix (the real proof)
scenarios/demo_chat.py        illustrative end-to-end chat (not a test)
tests/iptables-interception-test.sh  iptables-vs-proxy proof + flush/restore control
```

## In production (Kubernetes)

Use `deploy/helm/sentinel-ops-sidecar` to inject the same sidecar in-pod next to
your existing image — see the repo root README.
