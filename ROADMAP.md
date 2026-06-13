# Roadmap

Parked ideas — captured so they don't derail the current goal (land design
partners on the core governance story).

## TokenOps — a 5th envelope dimension (deferred until design partner #1)

> **One gate, two budgets.** A *risk budget* governs what an agent may **do**; a
> *token budget* governs what it may **spend**.

The Sentinel-Ops gate already sits on every agent action — the Mode-2 sidecar
already proxies the LLM call (`api.anthropic.com` flows through it). That makes
token metering + spend caps a natural extension at the chokepoint we already own,
reusing machinery that exists:

- **Risk-budget state machine → token/cost budget** (same NORMAL→…→EXHAUSTED logic, different unit).
- **Audit trail → per-agent/tenant cost attribution.**
- **Sidecar → already in the LLM egress path** (Mode-1 SDK metering is trivial; Mode-2 token-exact metering needs TLS body inspection — a real project).

Pitch sequencing: TokenOps sells the meeting and the ROI (hard dollars);
governance is the sticky core and the moat. Lead with whichever the buyer is
bleeding from — same gate either way.

**Thin MVP (when picked up):** token/cost observability + per-agent spend cap +
cost attribution in the audit trail. **Defer** the competitive savings levers
(semantic caching, auto model-routing) — correctness risk + crowded market —
until a partner pulls for them.

**Status: not started. Revisit after the first design partner signs.**
