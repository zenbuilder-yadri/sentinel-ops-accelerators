# Mode 2 — PipelinePilot (sidecar transparent proxy)

A vanilla LangGraph DevOps agent governed by a **separate sidecar container**.
The agent has **zero** awareness of Sentinel-Ops — every outbound HTTP call is
transparently steered through the sidecar via `HTTP_PROXY`, and the live
policy lives at `api.yadriworks.ai`.

This is the "polyglot fleet" answer: drop the sidecar into a Pod spec, set
one env-var, ship. The customer's agent source does not change by a single
line.

---

## The zero-code-change claim — verify it yourself

```bash
cd agent
grep -ri "soe\|sentinel\|evaluate" .
# → no matches. Exit 1.
```

The agent stack (`pilot.py`, `run.py`, `scenarios.py`, `requirements.txt`,
`Dockerfile`) contains zero references to Sentinel-Ops. If a grep
inside `agent/` ever returns a hit, this demo's central thesis is broken —
file a bug.

---

## Architecture

```
+---------------------------+        +-----------------------------+        +-------------------------+
|  pilot-agent (LangGraph)  |        |  soe-sidecar (public image)   |        |  api.yadriworks.ai      |
|  port 8090                |        |  port 15001 (proxy)         |        |  PROD control plane     |
|                           |        |  port 3101 (/healthz)       |        |                         |
|  httpx -> HTTP_PROXY env  |--TCP-->| CONNECT api.groq.com:443    |--POST->| /v1/evaluate            |
|                           |        | -> POST /v1/evaluate        |        | (tenant: yadriworks-demo)
|  Groq llama-3.3-70b       |<--403--|    decision=deny             |<-allow/deny+reason----------+   |
|  (real LLM call)          |        | -> tunnel CONNECT (allow)   |        | /v1/audit (Chronicle)   |
+---------------------------+        +-----------------------------+        +-------------------------+
        |                                       |
        | (optional)                            |
        v                                       v
   iptables-init (NET_ADMIN)              circuit-breaker
   NAT REDIRECT 80/443 -> 15001           fail-CLOSED on outage (SOE-1258)
```

* **No SDK in the agent.** The single integration point is `HTTP_PROXY=http://soe-sidecar:15001`.
* **Sidecar is a stock public image** — `us-central1-docker.pkg.dev/pragmatic-braid-467912-u0/sentinel-ops/soe-sidecar:latest`.
* **Every CONNECT is evaluated** against the live policy at `api.yadriworks.ai`
  by tenant `yadriworks-demo`, agent ID `devops-agent-mode2`.
* **Auth is per-tenant API key** (`X-SOE-Tenant-Id` + `X-SOE-Api-Key: sok_...`),
  not a user JWT — that's the right shape for a long-running pod.

---

## Scenarios (6) — `docs/demo-spec.md` §Mode 2

| ID         | Title                                                                | Layer under test                          | Expected | What it proves                                                                       |
|------------|----------------------------------------------------------------------|-------------------------------------------|----------|--------------------------------------------------------------------------------------|
| **M2-S1**  | Happy-path UAT rollout (5 hops)                                      | deterministic-allow                       | allow    | Sidecar is invisible when policy matches behaviour                                   |
| **M2-S2**  | `notify_slack(channel="https://pastebin.com/...", ...)`              | deterministic-deny (egressDeny)           | deny     | Network reset at CONNECT — the agent literally cannot exfil                          |
| **M2-S3**  | `apply_manifest("https://k8s-prod.acme.io/...", "default")`          | deterministic-deny (authorityLevel)       | deny     | `deploy-uat-only` enforced at the network layer, not just by a label                 |
| **M2-S4**  | `fetch_secret("prod/db-password")` (to `*.amazonaws.com`, allowed)   | content-guardrails (requestBody)          | deny     | Body inspection catches sub-resource attack on an allow-listed host                  |
| **M2-S5**  | Black-hole `SOE_API_URL` → re-run M2-S1                              | circuit-breaker (SOE-1258)                | deny     | **Fail-CLOSED**. The audit headline. Availability degrades, governance does not.    |
| **M2-S6**  | 30 rapid `plan_deployment` calls in 60s                              | risk-budget (Sentinel-AI escalate)        | escalate | Trajectory analysis — allow-in-isolation calls become ESCALATE in aggregate          |

Step-level mapping lives in [`agent/scenarios.py`](agent/scenarios.py). Decisions
are reported by the live engine; nothing about expected outcomes is hard-coded.

---

## Quick start

### Prerequisites

* Docker + docker-compose
* A `SOE_API_KEY` (`sok_…`) bound to tenant `yadriworks-demo` — get it from
  the YadriWorks admin console (mint a sok_ key under Settings -> API keys).
* A `GROQ_API_KEY` (free tier is fine — Groq is on the egress allow-list).

### 1. Configure

```bash
cp .env.example .env
$EDITOR .env   # fill in SOE_API_KEY + GROQ_API_KEY
```

### 2. Bring it up (normal mode)

```bash
docker compose up --build
```

Wait for the sidecar healthcheck:

```bash
curl -s http://localhost:3101/healthz
# {"status":"ok",...}
curl -s http://localhost:8090/health
# {"status":"ok","agent":"pipelinepilot",...}
```

### 3. Run a scenario

```bash
# List
curl -s http://localhost:8090/scenarios | jq

# Happy path (M2-S1)
curl -s -X POST http://localhost:8090/scenarios/M2-S1/run | jq

# Prompt-injected pastebin exfil (M2-S2) — observe sidecar deny
curl -s -X POST http://localhost:8090/scenarios/M2-S2/run | jq
```

Then open the Streamlit UI (`../ui`) and watch the live SSE feed from
`api.yadriworks.ai` — every step appears as a real decision event with a
real Chronicle audit row.

---

## M2-S5 — fail-CLOSED proof

This is the one auditors care about. The single override file flips
`SOE_API_URL` to `http://127.0.0.1:1` (no listener), so every
`/v1/evaluate` call from the sidecar fails. After the breaker threshold
the circuit opens and — because `SOE_CIRCUIT_BREAKER_FAIL_MODE=closed`
(SOE-1258, the default) — every egress request is denied.

```bash
# Stop the normal stack
docker compose down -v

# Bring it back up with the outage override
docker compose -f docker-compose.yml -f docker-compose.outage.yml up --build

# Re-run the happy path — every hop should now be denied by the sidecar
curl -s -X POST http://localhost:8090/scenarios/M2-S5/run | jq
```

The Streamlit `/circuit-breaker` panel will show `CLOSED -> OPEN` and the
30-second probe countdown. To return to normal:

```bash
docker compose down -v
docker compose up
```

---

## iptables variant (optional)

The default deployment uses `HTTP_PROXY` because it works everywhere. For
polyglot fleets where some workloads ignore `HTTP_PROXY` (Go binaries,
JVMs without `-Dhttps.proxyHost`, etc.) the production answer is an
`initContainer` that rewrites the netns NAT table.

```bash
docker compose --profile iptables up iptables-init
```

The reference script lives in [`iptables-init/init.sh`](iptables-init/init.sh).
In a real Kubernetes Pod it runs once, before the agent container starts.

---

## Files

```
mode2-pipeline-pilot/
├── README.md                          # this file
├── docker-compose.yml                 # 3 services: sidecar + agent + iptables-init
├── docker-compose.outage.yml          # M2-S5 override (control plane black-holed)
├── .env.example                       # vars consumed by the sidecar (not the agent)
├── agent/
│   ├── Dockerfile                     # python:3.12-slim + uvicorn
│   ├── requirements.txt               # langgraph + langchain-groq + httpx + fastapi
│   ├── pilot.py                       # LangGraph agent — 6 tools, real httpx, real Groq
│   ├── scenarios.py                   # 6 scripted scenarios (M2-S1..M2-S6)
│   └── run.py                         # FastAPI: GET /scenarios, POST /scenarios/{id}/run, GET /health
├── iptables-init/
│   └── init.sh                        # NAT REDIRECT script (deployment alternative)
└── soe-definitions/
    └── pipelinepilot.soe.json         # the policy the live engine enforces
```

---

## Troubleshooting

| Symptom                                                          | Cause                                                                       | Fix                                                                                                              |
|------------------------------------------------------------------|-----------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------|
| Sidecar fails healthcheck                                         | `SOE_API_KEY` invalid or tenant not seeded                                  | Mint a new sok_ key (tenant admin), paste into `.env`                                              |
| Every scenario denied, including M2-S1                            | Circuit breaker tripped (from earlier outage run)                           | `docker compose down -v && docker compose up`                                                                    |
| M2-S6 returns all allows, not an escalate                         | Per-session risk reset between runs                                         | Re-run within the same session, or `curl -X POST .../risk/reset` after each run                                  |
| Groq 401                                                          | `GROQ_API_KEY` missing                                                      | Add a key — the path is whitelisted, so the LLM call leaves the pod                                              |
| `grep` finds `soe` inside `agent/`                                | A future edit broke the zero-code-change invariant                          | Revert the edit — this directory is contractually clean                                                          |

---

For the full demo spec (architecture, alerts, comparison panels, auth flow):
[`docs/demo-spec.md`](../../docs/demo-spec.md).
