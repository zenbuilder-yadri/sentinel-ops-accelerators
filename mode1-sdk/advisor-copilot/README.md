# Mode 1 — AdvisorCopilot (SDK-integrated)

A second Mode-1 example: a LangGraph **investment-advisor** agent (mid-market RIA)
governed in-process with ~11 lines of Sentinel-Ops SDK calls. It's a companion to
the canonical Mode-1 walkthrough in [`../lending-advisor`](../lending-advisor/) —
same integration pattern, different domain.

- **LLM:** Anthropic Claude Sonnet 4 (`langchain_anthropic`)
- **Integration:** in-process — `SoeClient.evaluate()` / `.guard()` / `.audit()` (vendored `soe_client.py`)
- **Agent / tenant:** `fin-advisor-mode1` / your tenant
- **Auth:** `Authorization: Bearer <jwt>`

## Tools & dispositions (enforced server-side by `soe-definitions/advisor-copilot.soe.json`)

| Tool | Disposition | Enforcing layer |
|---|---|---|
| `read_market_data`, `get_portfolio_summary`, `generate_report` | allow | — |
| `draft_client_email` | allow (body guarded) | `contentGuardrails.pii` |
| `execute_trade`, `access_client_ssn`, `delete_client_records`, `read_credentials` | deny | `toolActions.denied` (+ glob denies) |

## Scenarios

`M1-S1` baseline allow · `M1-S2`/`M1-S3` hard-policy deny · `M1-S4` content-guardrail
catches LLM-hallucinated PII · `M1-S5` cumulative risk budget · `M1-S6` fail-closed on partition.

## Run

```bash
cp .env.example .env            # set SOE_JWT (from your dashboard /ui/login) + ANTHROPIC_API_KEY + SOE_TENANT_ID
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# deploy this SOE to your tenant once (envelope = {"soe": <def>}):
curl -fsS -X POST "${SOE_API_URL:-https://api.yadriworks.ai}/v1/deploy" \
  -H "Authorization: Bearer $SOE_JWT" -H "X-SOE-Tenant-Id: $SOE_TENANT_ID" \
  -H 'Content-Type: application/json' \
  --data "$(python3 -c 'import json;print(json.dumps({"soe":json.load(open("soe-definitions/advisor-copilot.soe.json"))}))')"

python agent.py --scenario all      # or --scenario M1-S4 | --interactive
```

## Files

```
agent.py                            the agent + the ~11-line SDK wrapper
tools.py                            synthetic-data tools (engine gates real tool-call events)
soe_client.py                       vendored HTTP client (evaluate/guard/audit, JWT-Bearer)
soe-definitions/advisor-copilot.soe.json   the policy (engine-side enforcement)
```

Everything is real (the `/v1/evaluate`, `/v1/audit`, `/v1/guardrails/evaluate`
calls hit the live control plane); only tool return values are synthetic.
