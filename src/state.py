"""P1 shared contracts (R5/R8/R10). JSON-compatible state preserves P5 keys."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import re
from typing import Annotated, Any, Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Provenance(Contract):
    line: str
    value: StrictInt
    kind: Literal["extracted", "user_input", "computed", "default_zero", "human_resolution"]
    formula: str | None = None
    inputs: list[dict] = Field(default_factory=list)
    sources: list[dict] = Field(default_factory=list)
    tool: dict | None = None
    citation: str | None = None
    entered_by: str | None = None
    timestamp: datetime

    @model_validator(mode="after")
    def audit_fields(self):
        if self.timestamp.tzinfo is None:
            raise ValueError("Timestamp must include a timezone")
        if self.kind in {"user_input", "human_resolution"} and not self.entered_by:
            raise ValueError("An input actor is required")
        if self.kind == "computed" and not (self.tool and self.inputs and self.formula):
            raise ValueError("Computed values require tool, inputs and formula")
        return self


class ResumePayload(Contract):
    escalation_id: str
    option: str
    note: str = Field(min_length=1)
    resolved_by: str = Field(min_length=1)
    overrides: dict[str, Any] = Field(default_factory=dict)

    @field_validator("note", "resolved_by")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("A nonblank note and staff identity are required")
        return value


class Escalation(Contract):
    id: str = Field(pattern=r"^esc_\d+$")
    code: Literal["E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9", "E10"]
    kind: Literal["STOP", "GATE"]
    raised_by: str
    reason: str
    evidence: list[str] = Field(default_factory=list)
    options: list[str]
    status: Literal["open", "resolved"] = "open"
    created_at: datetime
    resolution: dict | None = None


class IntakeFlag(Contract):
    id: str
    type: Literal["advice_request", "out_of_scope_mention", "third_party_answering",
                  "unknown_refund_account", "pressure_signal", "uncertain_answer",
                  "contradiction", "ssn_volunteered"]
    turn_id: int
    excerpt: str = ""
    raised_at: datetime


class ExtractedDocument(Contract):
    doc_id: str = Field(min_length=1)
    form: str
    boxes: dict[str, Any]
    confidence: dict[str, float] = Field(default_factory=dict)
    unverified: list[str] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)
    source_file: str | None = None

    @field_validator("confidence")
    @classmethod
    def probabilities(cls, values):
        if any(not 0 <= value <= 1 for value in values.values()):
            raise ValueError("Confidence must be between zero and one")
        return values


def validate_intake(value: Any):
    """Reject non-test SSNs before they can reach a persistent checkpoint."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key.lower().rsplit(".", 1)[-1] == "ssn" and item is not None:
                if not isinstance(item, str) or not re.fullmatch(r"9\d{2}-?\d{2}-?\d{4}", item):
                    raise ValueError("Only synthetic 900-series SSNs are accepted")
            validate_intake(item)
    elif isinstance(value, list):
        for item in value:
            validate_intake(item)
    return value


def merge_documents(left: list | None, right: list | None) -> list:
    """Order-independent parallel reduction. Conflicting same-ID writes fail closed."""
    indexed = {}
    for record in (left or []) + (right or []):
        record = ExtractedDocument.model_validate(record).model_dump(mode="json")
        key = record["doc_id"]
        if key in indexed and indexed[key] != record:
            raise ValueError(f"Conflicting extraction records for {key}")
        indexed[key] = record
    return [indexed[key] for key in sorted(indexed)]


def merge_escalations(left: list | None, right: list | None) -> list:
    """Sequential upsert by ID: retain old entries and replace resolved versions."""
    indexed = {record["id"]: deepcopy(record) for record in left or []}
    for record in right or []:
        validated = Escalation.model_validate(record).model_dump(mode="json")
        indexed[validated["id"]] = validated
    return [indexed[key] for key in sorted(indexed)]


class GraphState(TypedDict, total=False):
    session_id: str
    mode: Literal["demo", "production"]
    status: str
    intake: dict
    user_inputs: dict
    flags: list[dict]
    session_summary: str
    open_questions: list[str]
    uploads: list[dict]
    documents: Annotated[list[dict], merge_documents]
    escalations: Annotated[list[dict], merge_escalations]
    eligibility: dict
    filing_status_validated: str | None
    box_count_12d: int
    schedules: dict
    scope: dict
    citations: list[dict]
    lines: dict
    review_findings: list[dict]
    review_verdict: str
    last_agent: str
    next_agent: str
    handoff_history: list[list[str]]
    iterations: int
    total_handoffs: int
    pending_escalation: str


AGENT_FIELDS = {
    "intake": {"intake", "user_inputs", "flags", "session_summary", "open_questions"},
    "extraction": {"documents"},
    "rules": {"eligibility", "filing_status_validated", "box_count_12d", "schedules",
              "scope", "escalations", "citations"},
    "computation": {"lines", "open_questions"},
    "review": {"review_findings", "review_verdict"},
}


def validate_update(agent: str, update: dict) -> dict:
    if not isinstance(update, dict) or set(update) - AGENT_FIELDS[agent]:
        raise ValueError(f"{agent} wrote outside its contract")
    validate_intake(update)
    if "documents" in update:
        update["documents"] = merge_documents([], update["documents"])
    if "escalations" in update:
        update["escalations"] = merge_escalations([], update["escalations"])
    if "flags" in update:
        update["flags"] = [IntakeFlag.model_validate(f).model_dump(mode="json") for f in update["flags"]]
    if "lines" in update:
        update["lines"] = {k: Provenance.model_validate(v).model_dump(mode="json")
                           for k, v in update["lines"].items()}
    return update
