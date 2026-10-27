"""P4 test helper: run the real Extraction, Rules, Computation and Review agents in the same order the
graph does, WITHOUT LangGraph, so the evaluation cases can be checked anywhere (including machines
where langgraph is not installed). This does not replace tests/test_graph.py; it checks the data, not the routing.

It applies each agent's update with P1's own reducers (merge_documents / merge_escalations), forbids an
agent from writing outside its fields (validate_update), and uses P1's own `apply_resolution` for the
human step, so a resolution that works here uses the same payload the dashboard and CLI send.
"""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from src.agents import computation, extraction, review, rules
from src.human import apply_resolution
from src.state import merge_documents, merge_escalations, validate_intake, validate_update

REPO = Path(__file__).resolve().parents[1]


def load_input(relative: str) -> dict:
    return json.loads((REPO / relative).read_text(encoding="utf-8"))


def _apply(state: dict, update: dict) -> None:
    for key, value in update.items():
        if key == "documents":
            state["documents"] = merge_documents(state.get("documents"), value)
        elif key == "escalations":
            state["escalations"] = merge_escalations(state.get("escalations"), value)
        else:
            state[key] = value


def start(inputs: dict, session_id: str = "p4-sim") -> dict:
    validate_intake(inputs)
    state = deepcopy(inputs) | {"session_id": session_id, "mode": "production", "documents": [], "escalations": []}
    for upload in state.get("uploads", []):
        snapshot = deepcopy(state) | {"uploads": [upload]}       # one worker per document, like the graph
        _apply(state, validate_update("extraction", extraction.run(snapshot)))
    return state


def run_until_stop(state: dict) -> dict:
    """Rules -> Computation -> Review. Stops at an open escalation or when Computation/Review must send work back."""
    _apply(state, validate_update("rules", rules.run(deepcopy(state))))
    open_escalations = [e for e in state["escalations"] if e["status"] == "open"]
    if open_escalations:
        state["status"], state["pending_escalation"] = "awaiting_human", open_escalations[0]["id"]
        return state
    if state.get("eligibility", {}).get("missing"):
        state["status"] = "needs_intake"
        return state
    _apply(state, validate_update("computation", computation.run(deepcopy(state))))
    if state.get("open_questions"):
        state["status"] = "needs_intake"
        return state
    _apply(state, validate_update("review", review.run(deepcopy(state))))
    state["status"] = "draft_ready" if state.get("review_verdict") == "pass" else "review_sent_back"
    return state


def resolve(state: dict, payload: dict) -> dict:
    """Apply a staff resolution exactly as the graph's human node does, then continue."""
    _apply(state, apply_resolution(state, payload))
    state["pending_escalation"] = ""
    return run_until_stop(state)
