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

## The only governance wiring

`docker-compose.yml` sets `HTTP_PROXY=http://soe-sidecar:15001` on the agent.
That's it. The SOE (`soe-definitions/lending-assistant.soe.json`) declares the
egress allow/deny lists; the sidecar enforces them on every CONNECT.

## Files

```
app/                vanilla agent image (BYO Dockerfile) — zero SOE references
mock-services/      mock bureau / LOS / mail (synthetic, one image)
soe-definitions/    lending-assistant.soe.json (transport.network allow/deny)
docker-compose.yml  agent + soe-sidecar + 3 mocks
scenarios/attack.py stdlib attack harness
```

## In production (Kubernetes)

Use `deploy/helm/sentinel-ops-sidecar` to inject the same sidecar in-pod next to
your existing image — see the repo root README.
