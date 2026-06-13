# Mode 1 — AdvisorCopilot (SDK-integrated)

A LangGraph financial-advisor agent that adds **~11 lines** to gain full
Sentinel-Ops enforcement: every tool call is gated by a real
`POST /v1/evaluate` on `api.yadriworks.ai`, every allowed call is logged
to Chronicle via `POST /v1/audit`, and every LLM-emitted email body is
content-scanned via `POST /v1/guardrails/evaluate`.

- **Domain**: Fintech (mid-market RIA, $4B AUM)
- **Persona**: Head of Compliance — owns agent governance
- **LLM**: Anthropic Claude Sonnet 4 via `langchain_anthropic.ChatAnthropic`
- **Integration**: In-process HTTP — `SoeClient.evaluate()` / `.audit()` / `.guard()`
- **Tenant / Agent**: `yadriworks-demo` / `fin-advisor-mode1`
- **Auth**: `Authorization: Bearer <jwt>` (from `/ui/login` or reused from
  `sentinel-ops-demo/.env`)

---

## The ~11-line SOE diff (verbatim)

```python
# 1. sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ui"))
# 2. from soe_client import SoeClient
# 3. soe = SoeClient(api_url=SOE_API_URL, jwt=SOE_JWT,
#                    tenant_id=SOE_TENANT_ID, agent_id=AGENT_ID)
# 4. dec = soe.evaluate(tool_name, tool_input)
# 5. if dec["decision"] != "allow":
# 6.     return ToolMessage(f"BLOCKED by SOE: {dec['reason']} (layer={dec['layer']})", ...)
# 7. if tool_name == "draft_client_email":
# 8.     g = soe.guard(tool_input.get("body", ""))
# 9.     if g["action"] == "BLOCK":
# 10.        return ToolMessage(f"Guard blocked email body: {g['reason']}", ...)
# 11. soe.audit({"tool_name": tool_name, "tool_input": tool_input,
#               "decision": "allow", "outcome": "ok", "sessionId": SESSION_ID})
```

Everything else is the customer's existing agent. The diff lives at the top of
`agent.py` as a comment block so a staff engineer can review it in one sitting.

---

## Tools

| Tool | Disposition | Enforcing layer |
|---|---|---|
| `read_market_data(symbol)` | allow | — |
| `get_portfolio_summary(client_id)` | allow | — |
| `generate_report(topic)` | allow | — |
| `draft_client_email(client_id, subject, body)` | allow (body guarded) | `contentGuardrails.pii` |
| `execute_trade(symbol, qty, action)` | deny | `toolActions.denied` |
| `access_client_ssn(client_id)` | deny | `toolActions.denied` + `**/ssn*` readDeny |
| `delete_client_records(client_id)` | deny | `toolActions.denied` + `client/**` writeDeny |
| `read_credentials(path)` | deny | `toolActions.denied` + `**/credentials*` readDeny |

The agent exposes **all eight** tool schemas to the LLM — deterministic SOE
enforcement at the gate is the source of truth. No client-side filtering.

---

## Scenarios

| ID | What it proves | Expected | Layer |
|---|---|---|---|
| M1-S1 | Baseline — SDK wrapper invisible, <50 ms overhead | allow | deterministic |
| M1-S2 | Hard-policy line beats LLM compliance — sub-ms block | deny | deterministic |
| M1-S3 | Defense in depth: tool denylist + `**/ssn*` glob both fire | deny | deterministic |
| M1-S4 | Glob policy CANNOT catch LLM-hallucinated PII; guardrail can | deny | content-guardrails |
| M1-S5 | Cumulative risk is server-side — page refresh doesn't reset | deny | risk-budget |
| M1-S6 | Fail-CLOSED proven — no silent fail-open path on partition | deny | network-error |

---

## How to run

### 1. Bootstrap env

```bash
cp .env.example .env
# fill SOE_JWT (paste from /ui/login on the dashboard) and ANTHROPIC_API_KEY
```

### 2. Install deps (Python 3.11+)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Seed the tenant policy (once, from the demo root)

```bash
../bin/demo-seed-tenant.sh
# uploads soe-definitions/advisor-copilot.soe.json to api.yadriworks.ai
```

### 4. Run a single scenario

```bash
python agent.py --scenario M1-S1
python agent.py --scenario M1-S4   # the headline content-guardrails moment
```

### 5. Fire all six in sequence

```bash
python agent.py --scenario all
```

### 6. Interactive REPL

```bash
python agent.py --interactive
```

---

## Sibling files

- `soe-definitions/advisor-copilot.soe.json` — the live policy uploaded to the
  control plane. The engine, not this repo, evaluates it.
- `tools.py` — synthetic-data tool implementations. They exist so the engine
  has real tool-call events to gate.
- `../ui/soe_client.py` — shared HTTP client (`evaluate` / `audit` / `guard`)
  used by this agent and by the Streamlit UI. JWT-Bearer auth.
- `../bin/demo-bootstrap.sh` — top-level bring-up for both modes.

---

## What's real vs synthetic

| Layer | Real? |
|---|---|
| LangGraph agent + Anthropic LLM call | real |
| `POST /v1/evaluate` on `api.yadriworks.ai` | real (prod) |
| `POST /v1/audit` (Chronicle) | real (prod) |
| `POST /v1/guardrails/evaluate` | real (prod) |
| SOE policy enforcement | real (engine-side) |
| Tool return values (market prices, portfolios) | synthetic |

No mocked decisions. No canned data. No hardcoded denials.
