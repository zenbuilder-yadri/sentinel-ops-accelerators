"""
LendingAssistant chat backend — a vanilla LangGraph + Anthropic agent.

This service contains no governance code and no policy SDK. The only governance
wiring is the HTTP_PROXY env-var (set by docker-compose), which routes every
outbound call — the LLM, the bureau, the loan system, the mail relay, and
anything an attacker tricks the agent into fetching — through the egress proxy.
Containment happens on the wire, before any packet leaves the pod.
"""

import json

import httpx
from fastapi import FastAPI
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import BaseModel

from agent_core import build_graph
from tools import TOOLS

app = FastAPI(title="LendingAssistant (Mode 2 / sidecar)")


def execute(tool_name: str, tool_input: dict) -> str:
    """Plain tool executor. If the sidecar blocks the egress, httpx raises and
    we surface it — that blocked-on-the-wire result IS the Mode-2 demo signal."""
    spec = TOOLS.get(tool_name)
    if not spec:
        return f"ERROR: unknown tool {tool_name}"
    try:
        return json.dumps(spec["fn"](**tool_input))[:1500]
    except httpx.HTTPStatusError as e:
        return (f"EGRESS BLOCKED by egress proxy (HTTP {e.response.status_code}): "
                f"{tool_name} {tool_input}")
    except (httpx.ProxyError, httpx.ConnectError, httpx.TransportError) as e:
        return (f"EGRESS BLOCKED by egress proxy: {tool_name} {tool_input} "
                f"({type(e).__name__})")
    except Exception as e:  # noqa: BLE001
        return f"TOOL ERROR: {type(e).__name__}: {e}"


graph = build_graph(execute)


class ChatIn(BaseModel):
    message: str


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.post("/chat")
def chat(body: ChatIn):
    result = graph.invoke({"messages": [HumanMessage(content=body.message)]})
    trace, final = [], ""
    for m in result["messages"]:
        if isinstance(m, AIMessage):
            for tc in (m.tool_calls or []):
                trace.append({"type": "tool_call", "name": tc["name"], "args": tc["args"]})
            if m.content and not m.tool_calls:
                final = m.content if isinstance(m.content, str) else json.dumps(m.content)
        elif isinstance(m, ToolMessage):
            trace.append({
                "type": "tool_result",
                "blocked": str(m.content).startswith("EGRESS BLOCKED"),
                "content": str(m.content)[:400],
            })
    return {"final": final, "trace": trace}
