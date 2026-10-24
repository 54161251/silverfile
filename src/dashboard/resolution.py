"""Build staff ResumePayloads (contract #3) for the escalation options in the catalog.

Options and the sentence the taxpayer heard come from P5's rules.ESCALATION_CATALOG, as P5
asked, and from the escalation record itself (E9/E10 options are set by the orchestrator).
Some options only make sense with a corrected value; those require an override, which the
runtime records as a human_resolution provenance record (src/human.py).
"""
from __future__ import annotations

import json
import re
from typing import Any

from src.agents.rules import ESCALATION_CATALOG
from src.state import ResumePayload

FILING_STATUSES = ["single", "mfj", "mfs", "hoh", "qss"]
FILING_STATUS_LABELS = {"single": "Single", "mfj": "Married filing jointly", "mfs": "Married filing separately",
                        "hoh": "Head of household", "qss": "Qualifying surviving spouse"}

OPTION_LABELS = {
    "convert_to_client_call": "Convert to client call (close session)",
    "not_applicable_continue": "Not applicable, continue",
    "choose_value": "Choose the value that wins",
    "preparer_enters_amount": "Preparer enters the taxable amount",
    "close_session": "Close session",
    "acknowledge": "Acknowledge; question queued for preparer",
    "set_filing_status": "Set filing status",
    "flag_for_review": "Flag for trained staff review",
    "verified_continue": "Verified, continue",
    "correct_data_continue": "Correct data, continue",
    "enter_value": "Enter value",
    "contact_client": "Contact client",
    "rerun": "Rerun from the last good point",
}
ORCHESTRATOR_MESSAGES = {"E9": "A colleague will finish checking your return.",
                         "E10": "A colleague will finish checking your return."}

# Options that must carry a corrected value: (kind of value, suggested state path or None).
NEEDS_OVERRIDE = {
    ("E2", "choose_value"): "value",
    ("E3", "preparer_enters_amount"): "amount",
    ("E5", "set_filing_status"): "filing_status",
    ("E7", "correct_data_continue"): "value",
    ("E8", "enter_value"): "value",
}
ALLOWED_PREFIXES = ("intake.", "user_inputs.")  # what src/human.apply_resolution accepts
LINE_KEY = re.compile(r"^user_inputs\.[0-9a-z_.]+$")


def option_label(option: str) -> str:
    return OPTION_LABELS.get(option, option.replace("_", " ").capitalize())


def taxpayer_message(code: str) -> str:
    entry = ESCALATION_CATALOG.get(code)
    return entry["user_message"] if entry else ORCHESTRATOR_MESSAGES.get(code, "")


def override_kind(code: str, option: str) -> str | None:
    return NEEDS_OVERRIDE.get((code, option))


def suggested_path(escalation: dict) -> str:
    """First evidence entry that names a state path, without P5's '@hash' suffix."""
    if escalation.get("code") == "E5":
        return "intake.filing_status"
    for item in escalation.get("evidence", []):
        path = str(item).split("@", 1)[0]
        if path.startswith(ALLOWED_PREFIXES):
            return path
    return ""


def parse_value(path: str, text: str) -> Any:
    """Turn the staff-typed value into the type the runtime expects. No arithmetic (R9)."""
    text = (text or "").strip()
    if not text:
        raise ValueError("Enter a value")
    if path.startswith("user_inputs."):
        cleaned = text.replace(",", "").replace("$", "")
        if not re.fullmatch(r"-?\d+", cleaned):
            raise ValueError("Amounts are whole dollars, for example 1250")
        return int(cleaned)
    if text.lower() in {"true", "yes"}:
        return True
    if text.lower() in {"false", "no"}:
        return False
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    try:
        return json.loads(text) if text[:1] in "[{" else text
    except json.JSONDecodeError:
        return text


def build_payload(escalation: dict, option: str, note: str, staff_id: str,
                  override_path: str = "", override_value: Any = None) -> dict:
    """Validated ResumePayload dict. Raises ValueError with a message staff can act on."""
    if escalation.get("status") != "open":
        raise ValueError("This escalation is already resolved")
    if option not in escalation.get("options", []):
        raise ValueError("Choose one of the options offered for this escalation")
    overrides: dict[str, Any] = {}
    kind = override_kind(escalation["code"], option)
    if kind:
        path = (override_path or "").strip()
        if not path.startswith(ALLOWED_PREFIXES):
            raise ValueError("The field must start with intake. or user_inputs.")
        if path.startswith("user_inputs.") and not LINE_KEY.fullmatch(path):
            raise ValueError("Use a form line such as user_inputs.26")
        if kind == "filing_status" and override_value not in FILING_STATUSES:
            raise ValueError("Pick a filing status")
        if override_value is None or override_value == "":
            raise ValueError("Enter the corrected value")
        overrides[path] = override_value
    payload = {"escalation_id": escalation["id"], "option": option, "note": (note or "").strip(),
               "resolved_by": staff_id, "overrides": overrides}
    try:
        return ResumePayload.model_validate(payload).model_dump()
    except Exception as exc:  # pydantic ValidationError -> plain message for the UI
        raise ValueError("A note explaining the decision is required") from exc
