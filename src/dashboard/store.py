"""Session queries for the staff dashboard, built only on P1's public session API.

Reads come from LangGraph snapshots in the SQLite checkpointer (src/memory.py). The single
write path is `resolve`, which sends a ResumePayload through Sessions.resume, i.e.
Command(resume=...). The dashboard never edits line values or agent fields directly (B7).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from src.dashboard.auth import Staff
from src.demo_agents import adapters as demo_adapters
from src.memory import open_sessions
from src.state import ResumePayload

TZ = ZoneInfo("America/New_York")

# Dashboard groups, in display order. "completed" is what the brief calls submitted: a
# draft handed to Kushim staff. SilverFile never files anything (A25).
GROUPS = {
    "needs_staff": "Needs staff",
    "waiting_taxpayer": "Waiting on taxpayer",
    "in_progress": "In progress",
    "completed": "Draft ready",
    "closed": "Closed",
}
COMPLETED_STATUSES = {"draft_ready", "scaffold_complete"}


@dataclass
class SessionSummary:
    thread_id: str
    mode: str
    status: str
    group: str
    filing_status: str | None
    documents: int
    lines: int
    updated_at: datetime | None
    pending: dict | None = None            # open escalation awaiting staff, if any
    open_codes: list[str] = field(default_factory=list)
    intake_fields: list[str] = field(default_factory=list)  # questions the taxpayer must answer

    @property
    def group_label(self) -> str:
        return GROUPS[self.group]


def agents_for(mode: str) -> dict:
    """Agent adapters for resuming a session in the mode it was started with (run.py rule)."""
    if mode == "demo":
        return demo_adapters()
    from run import production_adapters  # raises a clear error until every agent is merged
    return production_adapters()


def _interrupts(snapshot) -> list[dict]:
    values = []
    for task in snapshot.tasks or ():
        for item in getattr(task, "interrupts", ()) or ():
            if isinstance(item.value, dict):
                values.append(item.value)
    return values


def _timestamp(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw).astimezone(TZ)
    except ValueError:
        return None


def summarize(thread_id: str, snapshot) -> SessionSummary:
    state = snapshot.values or {}
    waits = _interrupts(snapshot)
    staff_waits = [w for w in waits if w.get("type") == "staff_resolution"]
    intake_waits = [w for w in waits if w.get("type") == "intake"]
    status = state.get("status", "unknown")
    if staff_waits:
        group = "needs_staff"
    elif intake_waits:
        group = "waiting_taxpayer"
    elif status in COMPLETED_STATUSES:
        group = "completed"
    elif status == "closed":
        group = "closed"
    else:
        group = "in_progress"
    escalations = state.get("escalations", [])
    return SessionSummary(
        thread_id=thread_id,
        mode=state.get("mode", "unknown"),
        status=status,
        group=group,
        filing_status=state.get("filing_status_validated") or (state.get("intake") or {}).get("filing_status"),
        documents=len(state.get("documents", [])),
        lines=len(state.get("lines", {})),
        updated_at=_timestamp(snapshot.created_at),
        pending=staff_waits[0]["escalation"] if staff_waits else None,
        open_codes=[e["code"] for e in escalations if e.get("status") == "open"],
        intake_fields=[f for w in intake_waits for f in w.get("fields", [])],
    )


class Store:
    """Opens the shared SQLite file per call, so the dashboard never holds a stale snapshot."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)

    def _open(self, agents: dict | None = None):
        # Demo adapters are only used to build the graph for reading; nothing runs them here.
        return open_sessions(self.db_path, agents or demo_adapters())

    def thread_ids(self) -> list[str]:
        if not self.db_path.exists():
            return []
        seen: dict[str, None] = {}
        with self._open() as sessions:
            for item in sessions.graph.checkpointer.list(None):
                seen.setdefault(item.config["configurable"]["thread_id"], None)
        return list(seen)

    def summaries(self) -> list[SessionSummary]:
        if not self.db_path.exists():
            return []
        with self._open() as sessions:
            rows = [summarize(t, sessions.snapshot(t)) for t in self.thread_ids()]
        order = list(GROUPS)
        epoch = datetime.min.replace(tzinfo=TZ)
        rows.sort(key=lambda r: (r.updated_at or epoch), reverse=True)
        rows.sort(key=lambda r: order.index(r.group))  # stable: newest first inside each group
        return rows

    def state(self, thread_id: str) -> tuple[SessionSummary, dict]:
        with self._open() as sessions:
            snapshot = sessions.snapshot(thread_id)
            if not snapshot.values:
                raise KeyError(thread_id)
            return summarize(thread_id, snapshot), snapshot.values

    def resolve(self, thread_id: str, payload: dict[str, Any], staff: Staff) -> SessionSummary:
        """Resume the graph with a staff decision. The signed-in staff ID is always the actor."""
        if not isinstance(staff, Staff):
            raise PermissionError("Sign in as Kushim staff before resolving escalations")
        if payload.get("resolved_by") != staff.staff_id:
            raise PermissionError("resolved_by must be the signed-in staff member")
        clean = ResumePayload.model_validate(payload).model_dump()
        summary, _ = self.state(thread_id)
        if not summary.pending or summary.pending["id"] != clean["escalation_id"]:
            raise ValueError("This escalation is no longer waiting; refresh the dashboard")
        with self._open(agents_for(summary.mode)) as sessions:
            sessions.resume(thread_id, clean)
            return summarize(thread_id, sessions.snapshot(thread_id))
