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

def parse_yes_no(answer: str) -> bool | None:
    """Turn yes/no style answers into True/False, or None if unclear."""
    text = answer.strip().lower()
    if text in ("yes", "y", "yeah", "yep", "i am", "i do"):
        return True
    if text in ("no", "n", "nope", "i am not", "i do not"):
        return False
    return None

QUESTIONS = [
    {
        "group": None,
        "field": "filing_status",
        "text": "First, how would you describe your situation for this tax return? "
                "For example: single, married, or widowed.",
        "parser": parse_filing_status,
    },
    {
        "group": "taxpayer",
        "field": "birth_date",
        "text": "What is your date of birth? For example: March 5, 1958.",
        "parser": parse_birth_date,
    },
    {
        "group": "taxpayer",
        "field": "blind",
        "text": "Are you blind? Please answer yes or no.",
        "parser": parse_yes_no,

    },
        {
        "group": None,
        "field": "dual_status_alien",
        "text": "Were you a nonresident of the United States for part of 2025? "
                "Please answer yes or no.",
        "parser": parse_yes_no,
    },
        {
        "group": None,
        "field": "can_be_claimed_as_dependent",
        "text": "Can someone else list you as a dependent on their tax return? "
                "Please answer yes or no.",
        "parser": parse_yes_no,
    },
]

def field_path(question: dict) -> str:
    """Full path used by Rules and the staff UI, e.g. intake.taxpayer.birth_date."""
    parts = ["intake", question["group"], question["field"]]
    return ".".join(p for p in parts if p)

def _is_filled(intake: dict, question: dict) -> bool:
    group, field = question["group"], question["field"]
    source = intake.get(group) or {} if group else intake
    return source.get(field) not in (None, "")


def next_question(intake: dict) -> dict | None:
    """Return the first question that has no answer yet, or None if done."""
    for question in QUESTIONS:
        if not _is_filled(intake, question):
            return question
    return None

def record_answer(intake: dict, field: str, answer: str) -> dict:
    """Return a new intake dict with the answer saved. Old answers are kept."""
    updated = dict(intake)
    updated[field] = answer
    return updated

def record_nested_answer(intake: dict, group: str, field: str, answer) -> dict:
    """Save an answer inside a group, e.g. taxpayer -> birth_date. Keeps old answers."""
    updated = dict(intake)
    inner = dict(updated.get(group) or {})
    inner[field] = answer
    updated[group] = inner
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
def handle_answer(state: dict, answer: str, turn_id: int) -> dict:
    """Process one answer for whichever question is currently open."""
    intake = state.get("intake") or {}
    flags = list(state.get("flags") or [])

    question = next_question(intake)
    if question is None:
        return {"intake": intake, "flags": flags}

    value = question["parser"](answer)
    if value is None:
        flags.append(make_flag("uncertain_answer", turn_id, answer))
    elif question["group"]:
        intake = record_nested_answer(intake, question["group"], question["field"], value)
    else:
        intake = record_answer(intake, question["field"], value)

    return {"intake": intake, "flags": flags}

def run(state: dict) -> dict:
    """Read the state and return only the fields Intake may write."""
    intake = state.get("intake") or {}
    flags = list(state.get("flags") or [])

    answer = state.get("latest_answer")
    if answer is not None:
        turn_id = len(flags) + 1
        result = handle_answer(state, answer, turn_id)
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