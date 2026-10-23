"""Validated staff resolution; dashboard must authenticate staff before calling (P7)."""
from copy import deepcopy
from datetime import datetime, timezone

from src.orchestration import CLOSING_OPTIONS
from src.state import Provenance, ResumePayload, validate_intake


def apply_resolution(state, raw):
    payload = ResumePayload.model_validate(raw)
    pending = state.get("pending_escalation")
    if payload.escalation_id != pending:
        raise ValueError("Resolution does not match the pending escalation")
    record = next(e for e in state["escalations"] if e["id"] == pending)
    if record["status"] != "open" or payload.option not in record["options"]:
        raise ValueError("Escalation is closed or option is not allowed")
    now = datetime.now(timezone.utc).isoformat()
    resolution = payload.model_dump() | {"resolved_at": now}
    record = deepcopy(record) | {"status": "resolved", "resolution": resolution}
    result = {"escalations": [record], "last_agent": "human", "pending_escalation": ""}
    intake = deepcopy(state.get("intake", {}))
    inputs = deepcopy(state.get("user_inputs", {}))
    for path, value in payload.overrides.items():
        if path.startswith("intake."):
            parts = path.split(".")[1:]
            cursor = intake
            for part in parts[:-1]:
                cursor = cursor.setdefault(part, {}) if isinstance(cursor, dict) else cursor[int(part)]
            if isinstance(cursor, list):
                cursor[int(parts[-1])] = value
            else:
                cursor[parts[-1]] = value
        elif path.startswith("user_inputs."):
            line = path.split(".", 1)[1]
            inputs[line] = Provenance(line=line, value=value, kind="human_resolution",
                                      entered_by=payload.resolved_by, timestamp=now).model_dump(mode="json")
        else:
            raise ValueError("Overrides are limited to intake fields and user-input lines")
    validate_intake(intake)
    result.update(intake=intake, user_inputs=inputs, lines={}, review_findings=[], review_verdict="")
    if payload.option in CLOSING_OPTIONS:
        result["status"] = "closed"
    elif record["code"] in {"E9", "E10"}:
        result.update(iterations=0, handoff_history=[], total_handoffs=0)
    return result
