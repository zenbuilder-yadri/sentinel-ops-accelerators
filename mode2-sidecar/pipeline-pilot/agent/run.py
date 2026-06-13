"""
FastAPI driver for PipelinePilot.

Exposes three routes — the Streamlit UI hits /scenarios and /scenarios/{id}/run
for the demo, /health is for docker-compose readiness.

Note: this file contains no governance logic. The upstream proxy enforces
policy transparently at the HTTP_PROXY hop.
"""

from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from pilot import chat_once, execute_scripted
from scenarios import SCENARIOS, get_by_id

app = FastAPI(title="PipelinePilot", version="1.0.0")


class ChatRequest(BaseModel):
    prompt: str


@app.get("/health")
def health() -> dict:
    """Cheap liveness probe — used by docker-compose."""
    return {
        "status": "ok",
        "agent": "pipelinepilot",
        "proxy": os.environ.get("HTTP_PROXY", ""),
        "llm": "llama-3.3-70b-versatile (Groq)",
    }


@app.get("/scenarios")
def list_scenarios() -> dict:
    """Return scenario metadata so the UI can render the picker."""
    return {
        "scenarios": [
            {
                "id": s["id"],
                "title": s["title"],
                "layer": s["layer_under_test"],
                "expected": s["expected_decision"],
                "narrative": s["narrative"],
                "step_count": len(s["steps"]),
            }
            for s in SCENARIOS
        ]
    }


@app.post("/scenarios/{scenario_id}/run")
def run_scenario(scenario_id: str) -> dict:
    """Execute every scripted step and return raw HTTP results.

    Decisions reported here come straight from the upstream proxy (which
    got them from the live control plane). No client-side classification
    happens here.
    """
    s = get_by_id(scenario_id)
    if s is None:
        raise HTTPException(status_code=404, detail=f"scenario {scenario_id} not found")
    results = execute_scripted(s)
    return {
        "scenario_id": s["id"],
        "title": s["title"],
        "layer": s["layer_under_test"],
        "expected": s["expected_decision"],
        "results": results,
    }


@app.post("/chat")
def chat(req: ChatRequest) -> dict:
    """Free-form turn through the LangGraph agent (LLM picks the tools)."""
    return {"response": chat_once(req.prompt)}
