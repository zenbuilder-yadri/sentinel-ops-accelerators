"""
PipelinePilot — vanilla LangGraph DevOps agent.

NO REFERENCES TO GOVERNANCE OR POLICY ENGINES IN THIS FILE.

Architecture:

    pilot.py (LangGraph + Groq llama-3.3-70b-versatile)
        |
        |  every tool calls httpx.{get,post}(...)
        |  httpx honors HTTP_PROXY / HTTPS_PROXY env-vars
        v
    a transparent egress proxy on http://upstream-proxy:15001
        |
        v
    upstream hosts (api.groq.com, api.github.com, ...) on the open internet

If any tool's destination violates the policy bound to this agent, the
proxy returns 403 (or RSTs the TCP connection). The agent simply
observes the failure — exactly what an ungoverned production agent
would see if a NetworkPolicy denied egress.
"""

from __future__ import annotations

import os
import time
from typing import Annotated, Sequence, TypedDict

import httpx
from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langchain_groq import ChatGroq
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

# ─── Real HTTP helper ────────────────────────────────────────────────────
# httpx automatically reads HTTP_PROXY/HTTPS_PROXY from os.environ.
# We intentionally short timeouts so the demo stays snappy when egress is
# blocked at the proxy layer.
_DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0)


def _http(method: str, url: str, *, json: dict | None = None, headers: dict | None = None) -> dict:
    """Single egress helper. Returns a structured result for the LLM."""
    start = time.monotonic()
    try:
        with httpx.Client(timeout=_DEFAULT_TIMEOUT, verify=False, follow_redirects=False) as c:
            r = c.request(method, url, json=json, headers=headers or {})
            return {
                "ok": r.is_success,
                "status": r.status_code,
                "url": url,
                "latency_ms": int((time.monotonic() - start) * 1000),
                "body_snippet": r.text[:200] if r.text else "",
            }
    except httpx.ProxyError as e:
        return {"ok": False, "status": 403, "url": url, "error": f"proxy-error: {e}",
                "latency_ms": int((time.monotonic() - start) * 1000)}
    except (httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError) as e:
        return {"ok": False, "status": 0, "url": url, "error": f"connect-error: {e}",
                "latency_ms": int((time.monotonic() - start) * 1000)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "status": 0, "url": url, "error": f"{type(e).__name__}: {e}",
                "latency_ms": int((time.monotonic() - start) * 1000)}


# ─── Tools (6) — all make REAL httpx calls ───────────────────────────────

@tool
def plan_deployment(service: str, env: str) -> dict:
    """Ask the LLM (Groq) for a deployment plan summary."""
    return _http(
        "POST",
        "https://api.groq.com/openai/v1/chat/completions",
        json={
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": "You produce concise k8s deploy plans."},
                {"role": "user", "content": f"Plan a rollout for service={service} env={env}. 3 bullets."},
            ],
            "max_tokens": 256,
        },
        headers={"Authorization": f"Bearer {os.environ.get('GROQ_API_KEY','')}"},
    )


@tool
def fetch_pr_diff(repo: str, pr: int) -> dict:
    """Fetch a pull-request from the GitHub REST API."""
    return _http(
        "GET",
        f"https://api.github.com/repos/{repo}/pulls/{pr}",
        headers={"Accept": "application/vnd.github+json"},
    )


@tool
def push_image(image: str, tag: str) -> dict:
    """Pretend to push an image — actually performs a real registry GET."""
    return _http("GET", f"https://registry.hub.docker.com/v2/library/{image}/manifests/{tag}")


@tool
def apply_manifest(url: str, ns: str) -> dict:
    """Apply a k8s manifest by POSTing to the cluster API server."""
    return _http(
        "POST",
        url,
        json={"namespace": ns, "kind": "Deployment", "metadata": {"name": "pipelinepilot-rollout"}},
        headers={"Content-Type": "application/json"},
    )


@tool
def notify_slack(channel: str, msg: str) -> dict:
    """POST a Slack incoming-webhook message.

    `channel` is treated as a webhook URL when it starts with http(s)://
    (used by the prompt-injection scenario to pivot to pastebin); otherwise
    a real hooks.slack.com webhook target is constructed.
    """
    url = channel if channel.startswith(("http://", "https://")) else \
        f"https://hooks.slack.com/services/T000/B000/{channel.lstrip('#')}"
    return _http("POST", url, json={"text": msg})


@tool
def fetch_secret(name: str) -> dict:
    """Fetch a secret from AWS Secrets Manager (allow-listed host).

    The body carries the literal secret name — that is exactly where the
    contentGuardrails.requestBody.denySubstrings rule does its work.
    """
    return _http(
        "POST",
        "https://secretsmanager.us-east-1.amazonaws.com/",
        headers={
            "Content-Type": "application/x-amz-json-1.1",
            "X-Amz-Target": "secretsmanager.GetSecretValue",
        },
        json={"SecretId": name},
    )


TOOLS = [plan_deployment, fetch_pr_diff, push_image, apply_manifest, notify_slack, fetch_secret]


# ─── LangGraph wiring ────────────────────────────────────────────────────

class PilotState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]


def _llm() -> ChatGroq:
    return ChatGroq(
        model="llama-3.3-70b-versatile",
        temperature=0.0,
        max_tokens=512,
        api_key=os.environ.get("GROQ_API_KEY", ""),
    ).bind_tools(TOOLS)


def llm_node(state: PilotState) -> dict:
    return {"messages": [_llm().invoke(state["messages"])]}


def should_continue(state: PilotState) -> str:
    last = state["messages"][-1]
    return "tools" if getattr(last, "tool_calls", None) else END


def build_graph():
    g = StateGraph(PilotState)
    g.add_node("llm", llm_node)
    g.add_node("tools", ToolNode(TOOLS))
    g.set_entry_point("llm")
    g.add_conditional_edges("llm", should_continue, {"tools": "tools", END: END})
    g.add_edge("tools", "llm")
    return g.compile()


# ─── Public entrypoint for run.py ────────────────────────────────────────

def execute_scripted(scenario: dict) -> list[dict]:
    """Bypass the LLM and execute a scripted sequence of tool calls.

    Used by /scenarios/{id}/run so a demo operator gets a deterministic
    repro of the policy outcome. The LLM-driven graph (`build_graph`) is
    still wired up and exercised by /chat for free-form interactions.
    """
    by_name = {t.name: t for t in TOOLS}
    out: list[dict] = []
    for step in scenario["steps"]:
        tool_obj = by_name.get(step["tool"])
        if tool_obj is None:
            out.append({"tool": step["tool"], "error": "unknown-tool"})
            continue
        try:
            result = tool_obj.invoke(step["args"])
        except Exception as e:  # noqa: BLE001
            result = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        out.append({"tool": step["tool"], "args": step["args"], "note": step.get("note", ""), "result": result})
    return out


def chat_once(prompt: str) -> str:
    """Run one LLM-driven turn with full tool autonomy."""
    graph = build_graph()
    final = graph.invoke({"messages": [HumanMessage(content=prompt)]}, config={"recursion_limit": 25})
    last = final["messages"][-1]
    # ToolMessage payloads dump the raw HTTP result; AIMessage carries text.
    return last.content if not isinstance(last, ToolMessage) else str(last.content)
