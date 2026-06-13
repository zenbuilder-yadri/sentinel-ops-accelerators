"""
LendingAdvisor — Mode 1 (SDK-integrated).

Same LangGraph + Anthropic lending agent as the Mode-2 hero, but governed
in-process: the SDK gate is called before every tool call (~12 added lines vs an
ungoverned agent). The contrast with Mode 2 is the whole point —

  • Mode 1 (here):    decides ALLOW/DENY at the SDK, and inspects CONTENT — it
    blocks the SSN-leaking email (L-S6) that Mode 2's network layer lets through.
  • Mode 2 (sidecar): contains EGRESS on the wire — it blocks exfiltration even
    when the agent is fully prompt-injected, with zero code in the agent.

Usage:  python agent.py --scenario L-S1 | all
        python agent.py --interactive
"""

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agent_core import build_graph
from scenarios import SCENARIOS
from soe_client import SoeClient
from tools import TOOLS

load_dotenv(Path(__file__).resolve().parent / ".env")

SOE_API_URL = os.getenv("SOE_API_URL", "https://api.yadriworks.ai")
SOE_JWT = os.getenv("SOE_JWT", "")
SOE_TENANT_ID = os.getenv("SOE_TENANT_ID", "yadriworks-demo")
AGENT_ID = os.getenv("AGENT_ID", "lending-advisor-mode1")
SESSION_ID = os.getenv("SOE_SESSION_ID", f"sess-{uuid.uuid4().hex[:12]}")

if not SOE_JWT:
    print("[warn] SOE_JWT empty — every /v1/evaluate call will 401 (fail-closed).",
          file=sys.stderr)
if not os.getenv("ANTHROPIC_API_KEY"):
    print("[warn] ANTHROPIC_API_KEY empty — LLM calls will fail.", file=sys.stderr)

soe = SoeClient(api_url=SOE_API_URL, jwt=SOE_JWT,
                tenant_id=SOE_TENANT_ID, agent_id=AGENT_ID)


def execute(tool_name: str, tool_input: dict) -> str:
    """The ~12-line governance wrapper: evaluate -> guard -> run -> audit."""
    dec = soe.evaluate(tool_name, tool_input)
    if dec.get("decision") != "allow":
        return (f"BLOCKED by SOE: {dec.get('reason', 'denied')} "
                f"(layer={dec.get('layer', '?')})")

    if tool_name == "send_decision_email":
        g = soe.guard(tool_input.get("body", ""))
        if (g.get("action") or g.get("decision") or "").upper() in {"BLOCK", "DENY"}:
            return f"GUARD BLOCKED email body: {g.get('reason', 'PII/injection detected')}"

    try:
        result = TOOLS[tool_name]["fn"](**tool_input)
    except Exception as e:  # noqa: BLE001
        return f"TOOL ERROR: {e}"

    soe.audit({"tool_name": tool_name, "tool_input": tool_input,
               "decision": "allow", "outcome": "ok", "sessionId": SESSION_ID})
    return json.dumps(result)


agent = build_graph(execute)


def _line(msg: ToolMessage):
    b = msg.content if isinstance(msg.content, str) else str(msg.content)
    if b.startswith("BLOCKED by SOE") or b.startswith("GUARD BLOCKED"):
        print(f"  [DENY ] {b}")
    else:
        print(f"  [ALLOW] {b[:120]}{'…' if len(b) > 120 else ''}")


def run_scenario(sid: str):
    sc = SCENARIOS.get(sid)
    if not sc:
        print(f"unknown scenario {sid}"); return
    print(f"\n=== {sid} — {sc['desc']}  (expect {sc['expect']}) ===")
    print(f"USER: {sc['prompt']}")
    try:
        result = agent.invoke({"messages": [HumanMessage(content=sc["prompt"])]})
    except Exception as e:  # noqa: BLE001
        print(f"  [error] {e}"); return
    for m in result["messages"]:
        if isinstance(m, ToolMessage):
            _line(m)
        elif isinstance(m, AIMessage) and m.content and not m.tool_calls:
            t = m.content if isinstance(m.content, str) else json.dumps(m.content)
            print(f"  AGENT: {t[:180]}{'…' if len(t) > 180 else ''}")


def run_interactive():
    print("LendingAdvisor (Mode 1, SDK). Ctrl-D to exit.")
    hist = []
    while True:
        try:
            u = input("\nyou> ").strip()
        except EOFError:
            print(); return
        if not u:
            continue
        hist.append(HumanMessage(content=u))
        result = agent.invoke({"messages": hist})
        hist = result["messages"]
        for m in result["messages"][-5:]:
            if isinstance(m, ToolMessage):
                _line(m)
            elif isinstance(m, AIMessage) and m.content and not m.tool_calls:
                t = m.content if isinstance(m.content, str) else json.dumps(m.content)
                print(f"agent> {t}")


def main():
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--scenario", help="L-S1..L-S6 or 'all'")
    g.add_argument("--interactive", action="store_true")
    a = p.parse_args()
    if a.interactive:
        run_interactive()
    elif a.scenario == "all":
        for sid in SCENARIOS:
            run_scenario(sid)
    else:
        run_scenario(a.scenario)


if __name__ == "__main__":
    main()
