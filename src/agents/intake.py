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
    "widowed": "qss",
}


def parse_filing_status(answer: str) -> str | None:
    """Turn what the user said into one of single/mfj/mfs/hoh/qss, or None."""
    return FILING_STATUS_CHOICES.get(answer.strip().lower())


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

def run(state: dict) -> dict:
    """Read the state and return only the fields Intake may write."""
    intake = state.get("intake") or {}
    question = next_question(intake)
    return {
        "intake": intake,
        "user_inputs": state.get("user_inputs") or {},
        "flags": state.get("flags") or [],
        "session_summary": state.get("session_summary") or "",
        "open_questions": [question["field"]] if question else [],
    }