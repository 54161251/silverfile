"""Real P3 Intake + Rules, with offline extraction/computation/review placeholders."""
from copy import deepcopy
from src.agents.rules import run as rules_run
from src.agents.intake import run_interactive


def extraction(state):
    # This copies already structured fixture boxes. P4 replaces it with actual OCR.
    return {"documents": [deepcopy(state["uploads"][0])]}


def computation(state):
    # Deliberately empty: a successful routing demo is not a computed tax return.
    return {"lines": {}, "open_questions": []}


def review(state):
    return {"review_verdict": "pass", "review_findings": []}


def adapters():
    return {"intake": run_interactive, "extraction": extraction, "rules": rules_run,
            "computation": computation, "review": review}


def sample(hitl=False):
    return {"intake": {"filing_status": "single",
                        "taxpayer": {"birth_date": "1955-06-01", "ssn": "901-11-1111", "blind": False},
                        "dual_status_alien": False, "can_be_claimed_as_dependent": False,
                        "dependents": [], "other_amounts": {"26": 0}, "has_other_amounts": False,
                        "document_inventory": ["W-2"],
                        "refund": {"method": "direct_deposit", "account_owner": "unknown" if hitl else "taxpayer"}},
            "uploads": [{"doc_id": name, "form": "W-2", "boxes": {"1": amount, "2": 100},
                         "source_file": "synthetic-structured-fixture"}
                        for name, amount in [("w2_1", 1000), ("w2_2", 2000)]]}
