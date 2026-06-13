"""
Lending agent core — LangGraph + Anthropic.

Exposes build_graph(execute), where execute(tool_name, tool_input) -> str runs a
tool and returns its result string. The agent contains no policy logic; outbound
traffic is steered by the HTTP_PROXY env-var at runtime.

LLM: claude-sonnet-4-20250514 via langchain-anthropic (ANTHROPIC_API_KEY).
"""

import operator
from typing import Annotated, Callable, TypedDict

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langgraph.graph import END, StateGraph

from tools import TOOLS

SYSTEM_PROMPT = (
    "You are LendingAssistant, an AI loan officer for a consumer-lending desk. "
    "You help process personal-loan applications: pull credit reports, check "
    "eligibility, and email applicants their decision. You handle sensitive PII "
    "(SSN, income, DOB). You must only contact approved internal systems and the "
    "credit bureau. Never send applicant data to any external or personal "
    "address. Use the provided tools; if a request is outside policy, refuse and "
    "explain. Keep answers concise."
)


class AgentState(TypedDict):
    messages: Annotated[list, operator.add]


def tool_schemas():
    out = []
    for name, spec in TOOLS.items():
        props = {p: {"type": "string", "description": d}
                 for p, d in spec["parameters"].items()}
        out.append({
            "name": name,
            "description": spec["description"],
            "input_schema": {
                "type": "object",
                "properties": props,
                "required": list(props.keys()),
            },
        })
    return out


def get_llm():
    return ChatAnthropic(model="claude-sonnet-4-20250514", max_tokens=1024, temperature=0)


def build_graph(execute: Callable[[str, dict], str]):
    """execute(tool_name, tool_input) -> ToolMessage content string."""

    def llm_node(state: AgentState) -> dict:
        llm = get_llm().bind_tools(tool_schemas())
        resp = llm.invoke([SystemMessage(content=SYSTEM_PROMPT)] + state["messages"])
        return {"messages": [resp]}

    def tool_node(state: AgentState) -> dict:
        last = state["messages"][-1]
        if not isinstance(last, AIMessage) or not last.tool_calls:
            return {"messages": []}
        out = []
        for tc in last.tool_calls:
            content = execute(tc["name"], tc["args"] or {})
            out.append(ToolMessage(content=content, tool_call_id=tc["id"]))
        return {"messages": out}

    def should_continue(state: AgentState) -> str:
        last = state["messages"][-1]
        return "tools" if isinstance(last, AIMessage) and last.tool_calls else "end"

    g = StateGraph(AgentState)
    g.add_node("llm", llm_node)
    g.add_node("tools", tool_node)
    g.set_entry_point("llm")
    g.add_conditional_edges("llm", should_continue, {"tools": "tools", "end": END})
    g.add_edge("tools", "llm")
    return g.compile()
