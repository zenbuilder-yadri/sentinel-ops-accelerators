# LendingAdvisor — Mode 1 (SDK)

The same consumer-lending loan-officer agent as the Mode-2 hero, but governed
**in-process**: the SDK gate is called before every tool call (~12 added lines),
and content guardrails inspect outbound email bodies for PII.

## Run

```bash
cp .env.example .env        # SOE_JWT (Bearer), ANTHROPIC_API_KEY
pip install -r requirements.txt
python agent.py --scenario all      # or --scenario L-S1 | --interactive
```

## What it proves

| Scenario | Mechanism | Expect |
|---|---|---|
| L-S1 pull credit report | tool allow-list | **ALLOW** |
| L-S2 eligibility check | tool allow-list | **ALLOW** |
| L-S3 injection → `fetch_url` | tool deny-list | **DENY** |
| L-S4 SSRF → `fetch_url` | tool deny-list | **DENY** |
| L-S5 paste → `fetch_url` | tool deny-list | **DENY** |
| L-S6 SSN in decision email | **content guardrail** | **DENY** |

**L-S6 is the A/B against Mode 2.** Mode 1 catches the SSN inside an *allowed*
email via the content layer; Mode 2's network containment lets it through the
allowed mail relay. Containment vs. content — you usually want both.

## The integration (the ~12 lines)

```python
dec = soe.evaluate(tool_name, tool_input)          # 1. policy gate
if dec["decision"] != "allow": return f"BLOCKED: {dec['reason']}"
if tool_name == "send_decision_email":
    g = soe.guard(tool_input["body"])              # 2. content guardrail
    if g["action"] == "BLOCK": return "GUARD BLOCKED"
result = TOOLS[tool_name]["fn"](**tool_input)      # 3. run the tool
soe.audit({...})                                   # 4. tamper-evident audit
```

See `agent.py` (`execute()`). The SOE is `soe-definitions/lending-advisor.soe.json`.
