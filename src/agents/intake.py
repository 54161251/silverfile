"""Intake agent (P3). The only agent that talks to the taxpayer."""
from __future__ import annotations


def run(state: dict) -> dict:
    """Read the state and return only the fields Intake may write."""
    return {
        "intake": state.get("intake") or {},
        "user_inputs": state.get("user_inputs") or {},
        "flags": state.get("flags") or [],
        "session_summary": state.get("session_summary") or "",
        "open_questions": state.get("open_questions") or [],
    }