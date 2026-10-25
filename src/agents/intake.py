"""Intake agent (P3). The only agent that talks to the taxpayer."""
from __future__ import annotations

# 要问的问题,按顺序排列。每个问题只问一件事。
# field: 答案存进 intake 的哪个位置
# text:  用通俗的话问用户

# 用户说的话 -> Rules 能读懂的值
FILING_STATUS_CHOICES = {
    "single": "single",
    "married": "mfj",
    "married filing jointly": "mfj",
    "married filing separately": "mfs",
    "head of household": "hoh",
}


def parse_filing_status(answer: str) -> str | None:
    """Turn what the user said into one of single/mfj/mfs/hoh/qss, or None."""
    return FILING_STATUS_CHOICES.get(answer.strip().lower())

def parse_birth_date(answer: str) -> str | None:
    """Turn a date like 03/05/1958 or 1958-03-05 into YYYY-MM-DD, or None."""
    text = answer.strip()
    for pattern in ("%Y-%m-%d", "%m/%d/%Y", "%B %d, %Y"):
        try:
            return datetime.strptime(text, pattern).date().isoformat()
        except ValueError:
            continue
    return None


QUESTIONS = [
    {
        "field": "filing_status",
        "text": "First, how would you describe your situation for this tax return? "
                "For example: single, married, or widowed.",
    },
]


def _is_filled(intake: dict, field: str) -> bool:
    return intake.get(field) not in (None, "")


def next_question(intake: dict) -> dict | None:
    """Return the first question that has no answer yet, or None if done."""
    for question in QUESTIONS:
        if not _is_filled(intake, question["field"]):
            return question
    return None

def record_answer(intake: dict, field: str, answer: str) -> dict:
    """Return a new intake dict with the answer saved. Old answers are kept."""
    updated = dict(intake)
    updated[field] = answer
    return updated

from datetime import datetime, timezone


def make_flag(flag_type: str, turn_id: int, excerpt: str = "") -> dict:
    """Build a flag record that matches the IntakeFlag contract in state.py."""
    now = datetime.now(timezone.utc)
    return {
        "id": f"flag_{turn_id}_{flag_type}",
        "type": flag_type,
        "turn_id": turn_id,
        "excerpt": excerpt,
        "raised_at": now.isoformat(),
    }

def handle_filing_status_answer(state: dict, answer: str, turn_id: int) -> dict:
    """Process one answer to the filing-status question."""
    intake = state.get("intake") or {}
    flags = list(state.get("flags") or [])

    value = parse_filing_status(answer)
    if value is None:
        flags.append(make_flag("uncertain_answer", turn_id, answer))
    else:
        intake = record_answer(intake, "filing_status", value)

    return {"intake": intake, "flags": flags}

def run(state: dict) -> dict:
    """Read the state and return only the fields Intake may write."""
    intake = state.get("intake") or {}
    flags = list(state.get("flags") or [])

    answer = state.get("latest_answer")
    if answer is not None:
        turn_id = len(flags) + 1
        result = handle_filing_status_answer(state, answer, turn_id)
        intake = result["intake"]
        flags = result["flags"]

    question = next_question(intake)
    return {
        "intake": intake,
        "user_inputs": state.get("user_inputs") or {},
        "flags": flags,
        "session_summary": state.get("session_summary") or "",
        "open_questions": [question["field"]] if question else [],
    }