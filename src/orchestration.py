"""Rule-based control only: no extraction, tax math, or taxpayer conversation (B1)."""
from collections import Counter
from datetime import datetime, timezone
from src.progress import flag_keys, guard_state

REVIEW_LIMIT = 3
HANDOFF_REPEAT_LIMIT = 3
HANDOFF_WINDOW = 10
TOTAL_LIMIT = 80
CLOSING_OPTIONS = {"close_session", "convert_to_client_call", "flag_for_review"}


def guard_escalation(state, code):
    number = 1 + max((int(e["id"].split("_")[1]) for e in state.get("escalations", [])), default=0)
    return {"id": f"esc_{number:04d}", "code": code, "kind": "STOP",
            "raised_by": "orchestrator", "reason": "Review limit reached" if code == "E9" else "Repeated handoff cycle",
            "evidence": ["iterations" if code == "E9" else "handoff_history"],
            "options": ["close_session", "rerun"], "status": "open",
            "created_at": datetime.now(timezone.utc).isoformat(), "resolution": None}


def orchestrate(state):
    if state.get("status") == "closed":
        return {"next_agent": "end"}
    pending = [e for e in state.get("escalations", []) if e["status"] == "open"]
    if pending:
        return {"next_agent": "human", "pending_escalation": pending[0]["id"], "status": "awaiting_human"}
    last = state.get("last_agent", "start")
    iterations = state.get("iterations", 0)
    if last == "start":
        target = "intake"
    elif last == "intake":
        done = {doc["doc_id"] for doc in state.get("documents", [])}
        if set(flag_keys(state)) - set(state.get("checked_intake_flags", [])):
            target = "rules"  # New advice/uncertainty/exploitation flags must not wait for the questionnaire.
        elif state.get("open_questions"):
            target = "intake"
        else:
            target = "dispatch" if any(u["doc_id"] not in done for u in state.get("uploads", [])) else "rules"
    elif last == "extraction":
        target = "rules"
    elif last in {"rules", "human"}:
        if last == "human":
            target = "rules"
        elif state.get("eligibility", {}).get("missing") or state.get("open_questions"):
            target = "intake"
        elif not state.get("scope", {}).get("in_scope") or not state.get("filing_status_validated"):
            raise ValueError("Rules must report missing inputs or an escalation when blocked")
        else:
            target = "computation"
    elif last == "computation":
        target = "intake" if state.get("open_questions") else "review"
    elif last == "review":
        verdict = state.get("review_verdict")
        if verdict == "pass":
            status = "scaffold_complete" if state.get("mode") == "demo" else "draft_ready"
            if status == "draft_ready" and not state.get("lines"):
                raise ValueError("Cannot complete a real draft without populated lines")
            return {"next_agent": "end", "status": status}
        if verdict != "revise" or not state.get("review_findings"):
            raise ValueError("Review must return pass or revise with findings")
        if iterations >= REVIEW_LIMIT:
            return {"escalations": [guard_escalation(state, "E9")], "next_agent": "orchestrator"}
        target = state["review_findings"][0]["target_agent"]
        if target not in {"intake", "extraction", "rules", "computation"}:
            raise ValueError("Invalid review send-back target")
        # Re-extraction is a fresh document version; conflicts are never overwritten.
        target = "dispatch" if target == "extraction" else target
        iterations += 1
    else:
        raise ValueError("Unknown agent completion")
    pair = [last, target]
    history = (state.get("handoff_history", []) + [pair])[-HANDOFF_WINDOW:]
    progress = guard_state(state, pair, HANDOFF_WINDOW)
    repeated = max(Counter(map(tuple, progress["stalled_handoff_history"])).values()) >= HANDOFF_REPEAT_LIMIT
    total = state.get("total_handoffs", 0) + 1
    if repeated or progress["handoffs_without_progress"] > TOTAL_LIMIT:
        return {"escalations": [guard_escalation(state, "E10")], "next_agent": "orchestrator"}
    return progress | {"next_agent": target, "handoff_history": history, "iterations": iterations,
            "total_handoffs": total, "status": "extracting" if target == "dispatch" else target}
