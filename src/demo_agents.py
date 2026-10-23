"""Offline walking skeleton only. No OCR, LLM, tax math, or valid return is claimed."""
from copy import deepcopy
from langgraph.types import interrupt
from src.agents.rules import run as rules_run


def intake(state):
    missing = state.get("eligibility", {}).get("missing", []) + state.get("open_questions", [])
    data = deepcopy(state.get("intake", {}))
    if missing:
        reply = interrupt({"type": "intake", "fields": missing, "demo": True})
        for path in missing:
            if not path.startswith("intake.") or path not in reply:
                raise ValueError("Demo intake needs an answer for each requested intake path")
            cursor = data
            parts = path.split(".")[1:]
            for part in parts[:-1]:
                cursor = cursor.setdefault(part, {})
            cursor[parts[-1]] = reply[path]
    return {"intake": data, "open_questions": []}


def extraction(state):
    # This copies already structured fixture boxes. P4 replaces it with actual OCR.
    return {"documents": [deepcopy(state["uploads"][0])]}


def computation(state):
    # Deliberately empty: a successful routing demo is not a computed tax return.
    return {"lines": {}, "open_questions": []}


def review(state):
    return {"review_verdict": "pass", "review_findings": []}


def adapters():
    return {"intake": intake, "extraction": extraction, "rules": rules_run,
            "computation": computation, "review": review}


def sample(hitl=False):
    return {"intake": {"filing_status": "single",
                        "taxpayer": {"birth_date": "1955-06-01", "ssn": "901-11-1111", "blind": False},
                        "document_inventory": ["W-2"],
                        "refund": {"method": "direct_deposit", "account_owner": "unknown" if hitl else "taxpayer"}},
            "uploads": [{"doc_id": name, "form": "W-2", "boxes": {"1": amount, "2": 100},
                         "source_file": "synthetic-structured-fixture"}
                        for name, amount in [("w2_1", 1000), ("w2_2", 2000)]]}
