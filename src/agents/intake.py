"""Intake agent (P3). The only agent that talks to the taxpayer."""
from __future__ import annotations
from langgraph.types import interrupt
from src.agents.rules import ESCALATION_CATALOG


FILING_STATUS_CHOICES = {
    "single": "single",
    "married": "mfj",
    "married filing jointly": "mfj",
    "married filing separately": "mfs",
    "head of household": "hoh",
}


def parse_filing_status(answer: str) -> str | None:
    """Turn what the user said into one of single/mfj/mfs/hoh, or None."""
    text = answer.strip().lower()
    exact = FILING_STATUS_CHOICES.get(text)
    if exact:
        return exact
    words = set(re.findall(r"[a-z]+", text))
    # Unclear, negated, or human-path cases: do not guess.
    if words & {"widow", "widowed", "widower", "not", "never",
                "unmarried", "divorced", "separated"}:
        return None
    found = set()
    if "single" in words:
        found.add("single")
    if "head" in words and "household" in words:
        found.add("hoh")
    if "married" in words:
        found.add("mfs" if words & {"separately", "separate"} else "mfj")
    return found.pop() if len(found) == 1 else None

def parse_birth_date(answer: str) -> str | None:
    """Turn a date like 03/05/1958, 1958-03-05 or March 5, 1958 into YYYY-MM-DD, or None."""
    text = re.sub(r"(?<=\d)(st|nd|rd|th)\b", "", answer.strip().rstrip("."),
                  flags=re.IGNORECASE)
    text = " ".join(text.split())
    for pattern in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y", "%B %d, %Y",
                    "%B %d %Y", "%b %d, %Y", "%b %d %Y"):
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

def parse_refund_method(answer: str) -> str | None:
    text = answer.strip().lower()
    if "deposit" in text or "bank" in text:
        return "direct_deposit"
    if "check" in text or "mail" in text:
        return "check"
    return None


def parse_account_owner(answer: str) -> str | None:
    text = answer.strip().lower()
    if any(p in text for p in ("not sure", "don't know", "do not know", "unknown")):
        return "unknown"
    if "joint" in text or "both" in text:
        return "joint"
    if "spouse" in text or "wife" in text or "husband" in text:
        return "spouse"
    if text in ("mine", "my own", "me", "my name", "taxpayer") or "my own" in text:
        return "taxpayer"
    words = set(re.findall(r"[a-z]+", text.replace("'s", "")))
    if words & {"son", "daughter", "friend", "someone", "other", "caregiver", "nephew", "niece", "grandson", "granddaughter"}:
        return "other"
    return None

import re

SSN_PATTERN = re.compile(r"9\d{2}-?\d{2}-?\d{4}")


def parse_ssn(answer: str) -> str | None:
    """Accept only a 900-series test SSN. Anything else returns None."""
    text = answer.strip()
    if SSN_PATTERN.fullmatch(text):
        digits = text.replace("-", "")
        return f"{digits[:3]}-{digits[3:5]}-{digits[5:]}"
    return None

SSN_ANYWHERE = re.compile(r"\b\d{3}-?\d{2}-?\d{4}\b")


def contains_ssn(answer: str) -> bool:
    """True if the text contains something shaped like a Social Security number."""
    return bool(SSN_ANYWHERE.search(answer))



ADVICE_PHRASES = (
    "should i", "can i deduct", "would i pay less", "is it better",
    "roth", "how can i save", "lower my tax", "worth it to",
)


def looks_like_advice_request(answer: str) -> bool:
    """True if the user seems to be asking for tax advice instead of answering."""
    text = answer.lower()
    return any(phrase in text for phrase in ADVICE_PHRASES)

THIRD_PARTY_PHRASES = (
    "i'm answering for", "i am answering for", "answering for my",
    "on behalf of", "i'm his", "i'm her", "i am his", "i am her",
    "he told me to", "she told me to", "my son is helping",
    "my daughter is helping", "my caregiver", "power of attorney",
)


def looks_like_third_party(answer: str) -> bool:
    """True if someone other than the taxpayer may be answering."""
    text = answer.lower()
    return any(phrase in text for phrase in THIRD_PARTY_PHRASES)
 

CORRECTION_PHRASES = (
    "i made a mistake", "i was wrong", "sorry, i meant", "i meant to say",
    "change my answer", "that was wrong",
)

def looks_like_correction(answer: str) -> bool:
    text = answer.lower()
    return any(phrase in text for phrase in CORRECTION_PHRASES)

BACK_PHRASES = ("go back", "previous question", "back up", "last question",
                "the one before")


def wants_to_go_back(answer: str) -> bool:
    text = answer.lower()
    return any(phrase in text for phrase in BACK_PHRASES)


def previous_question(intake: dict, current: dict | None = None) -> dict | None:
    """The last answered question that comes before `current` in QUESTIONS."""
    last = None
    for question in QUESTIONS:
        if question is current:
            break
        condition = question.get("only_if")
        if condition and not condition(intake):
            continue
        if _is_filled(intake, question):
            last = question
    return last

OUT_OF_SCOPE_KEYWORDS = {
    "itemize": ("itemize", "itemized", "schedule a"),
    "self_employment": ("self-employed", "self employed", "my business", "freelance", "1099-nec"),
    "rental": ("rental", "rent out", "landlord", "tenant"),
    "capital_gains": ("capital gain", "sold stock", "sold shares", "sold my house", "sold a house"),
    "digital_assets": ("bitcoin", "crypto", "ethereum", "nft"),
    "foreign": ("foreign account", "overseas", "abroad", "foreign income"),
    "amended_or_prior_year": ("amended", "prior year", "last year's return", "previous year"),
    "state_return": ("state return", "state tax"),
}


def out_of_scope_items(answer: str) -> list:
    """Category codes (matching Rules' OUT_OF_SCOPE_ITEMS) mentioned in the answer."""
    text = answer.lower()
    return [code for code, words in OUT_OF_SCOPE_KEYWORDS.items()
            if any(w in text for w in words)]

def is_married_joint(intake: dict) -> bool:
    return intake.get("filing_status") == "mfj"

def refund_in_progress(intake: dict) -> bool:
    return "refund" in intake


def refund_is_deposit(intake: dict) -> bool:
    return (intake.get("refund") or {}).get("method") == "direct_deposit"


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
        "field": "ssn",
        "text": "What is your Social Security number? For this practice system, "
                "please use only a test number that starts with 9.",
        "parser": parse_ssn,
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
                "This mainly applies to people who moved to or from the "
                "United States during the year. Please answer yes or no.",
        "parser": parse_yes_no,
    },
    {
        "group": None,
        "field": "can_be_claimed_as_dependent",
        "text": "Can someone else list you as a dependent on their tax return? "
                "For example, a relative who pays most of your living costs. "
                "Please answer yes or no.",
        "parser": parse_yes_no,
    },
    {
        "group": "spouse",
        "field": "birth_date",
        "text": "What is your spouse's date of birth? For example: March 5, 1958.",
        "parser": parse_birth_date,
        "only_if": is_married_joint,
    },
        {
        "group": "spouse",
        "field": "ssn",
        "text": "What is your spouse's Social Security number? For this practice "
                "system, please use only a test number that starts with 9.",
        "parser": parse_ssn,
        "only_if": is_married_joint,
    },
    {
        "group": "spouse",
        "field": "blind",
        "text": "Is your spouse blind? Please answer yes or no.",
        "parser": parse_yes_no,
        "only_if": is_married_joint,
    },
        {
        "group": "refund",
        "field": "method",
        "text": "If you get a refund, would you like it by direct deposit "
                "or by a mailed check?",
        "parser": parse_refund_method,
        "only_if": refund_in_progress,
    },
    {
        "group": "refund",
        "field": "account_owner",
        "text": "Whose name is on the bank account? For example: mine, "
                "joint with my spouse, or someone else.",
        "parser": parse_account_owner,
        "only_if": refund_is_deposit,
    },
]

def field_path(question: dict) -> str:
    """Full path used by Rules and the staff UI, e.g. intake.taxpayer.birth_date."""
    parts = ["intake", question["group"], question["field"]]
    return ".".join(p for p in parts if p)

def _is_filled(intake: dict, question: dict) -> bool:
    index = question.get("dependent_index")
    if index is not None:
        people = intake.get("dependents") or []
        return index < len(people) and people[index].get(question["field"]) not in (None, "")
    group, field = question["group"], question["field"]
    source = intake.get(group) or {} if group else intake
    return source.get(field) not in (None, "")

import re as _re

DEPENDENT_QUESTIONS = {
    "name": ("What is this person's first name?", None),
    "relationship": ("How is this person related to you? For example: "
                     "son, daughter, grandchild, parent.", None),
    "ssn": ("What is this person's Social Security number? For this practice "
            "system, please use only a test number that starts with 9.", parse_ssn),
}


def dependent_question(path: str) -> dict | None:
    """Build a question for paths like intake.dependents.0.ssn."""
    match = _re.fullmatch(r"intake\.dependents\.(\d+)\.(name|relationship|ssn)", path)
    if not match:
        return None
    index, field = int(match.group(1)), match.group(2)
    text, parser = DEPENDENT_QUESTIONS[field]
    return {"group": f"dependents.{index}", "field": field, "text": text,
            "parser": parser or (lambda answer: answer.strip() or None),
            "dependent_index": index}
import re as _re

DEPENDENT_QUESTIONS = {
    "name": ("What is this person's first name?", None),
    "relationship": ("How is this person related to you? For example: "
                     "son, daughter, grandchild, parent.", None),
    "ssn": ("What is this person's Social Security number? For this practice "
            "system, please use only a test number that starts with 9.", parse_ssn),
}


def dependent_question(path: str) -> dict | None:
    """Build a question for paths like intake.dependents.0.ssn."""
    match = _re.fullmatch(r"intake\.dependents\.(\d+)\.(name|relationship|ssn)", path)
    if not match:
        return None
    index, field = int(match.group(1)), match.group(2)
    text, parser = DEPENDENT_QUESTIONS[field]
    return {"group": f"dependents.{index}", "field": field, "text": text,
            "parser": parser or (lambda answer: answer.strip() or None),
            "dependent_index": index}
           
def question_for_path(path: str) -> dict | None:
    """Find the question whose full field path equals `path`."""
    for question in QUESTIONS:
        if field_path(question) == path:
            return question
    return None

def next_question(intake: dict, missing: list | None = None) -> dict | None:
    """Return the next question to ask, or None.

    Paths named by Rules (`missing`) come first; otherwise follow QUESTIONS order.
    """
    for path in missing or []:
        question = question_for_path(path) or dependent_question(path)
        if question is not None and not _is_filled(intake, question):
            return question
    for question in QUESTIONS:
        condition = question.get("only_if")
        if condition and not condition(intake):
            continue
        if not _is_filled(intake, question):
            return question
    return None

LABELS = {
    "intake.filing_status": "your filing status",
    "intake.taxpayer.birth_date": "your date of birth",
    "intake.taxpayer.ssn": "your Social Security number",
    "intake.taxpayer.blind": "whether you are blind",
    "intake.dual_status_alien": "whether you were a nonresident for part of 2025",
    "intake.can_be_claimed_as_dependent": "whether someone else can claim you as a dependent",
    "intake.spouse.birth_date": "your spouse's date of birth",
    "intake.spouse.ssn": "your spouse's Social Security number",
    "intake.spouse.blind": "whether your spouse is blind",
        "intake.refund.method": "how you want your refund",
    "intake.refund.account_owner": "whose name is on the bank account",
}


def build_summary(intake: dict) -> str:
    """Plain-language recap of what is already answered and what is left."""
    done, left = [], []
    for question in QUESTIONS:
        condition = question.get("only_if")
        if condition and not condition(intake):
            continue
        label = LABELS[field_path(question)]
        (done if _is_filled(intake, question) else left).append(label)
    if not done:
        return ""
    text = "So far we have covered: " + ", ".join(done) + "."
    if left:
        text += " Still to go: " + ", ".join(left) + "."
    return text

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

def record_dependent_answer(intake: dict, index: int, field: str, value) -> dict:
    """Save one field of the index-th dependent. Keeps everyone else's answers."""
    updated = dict(intake)
    people = [dict(person) for person in (updated.get("dependents") or [])]
    while len(people) <= index:
        people.append({})
    people[index][field] = value
    updated["dependents"] = people
    return updated

from datetime import datetime, timezone


def make_flag(flag_type: str, turn_id: int, excerpt: str = "") -> dict:
    """Build a flag record that matches the IntakeFlag contract in state.py."""
    now = datetime.now(timezone.utc)
    return {
        "id": f"flag_{turn_id}_{flag_type}",
        "type": flag_type,
        "turn_id": turn_id,
        "excerpt": SSN_ANYWHERE.sub("[SSN removed]", excerpt),
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

def handle_answer(state: dict, answer: str, turn_id: int, question: dict | None = None) -> dict:
    """Process one answer for whichever question is currently open."""
    intake = state.get("intake") or {}
    flags = list(state.get("flags") or [])

    question = question or next_question(intake)
    if question is None:
        return {"intake": intake, "flags": flags}

    if looks_like_advice_request(answer):
        flags.append(make_flag("advice_request", turn_id, answer))
        return {"intake": intake, "flags": flags}

    if looks_like_third_party(answer):
        flags.append(make_flag("third_party_answering", turn_id, answer))
        return {"intake": intake, "flags": flags}

    if looks_like_correction(answer):
        flags.append(make_flag("contradiction", turn_id, answer))
        return {"intake": intake, "flags": flags}

    if out_of_scope_items(answer):
        flags.append(make_flag("out_of_scope_mention", turn_id, answer))
        return {"intake": intake, "flags": flags}

    if contains_ssn(answer) and question["field"] != "ssn":
        flags.append(make_flag("ssn_volunteered", turn_id, ""))
        return {"intake": intake, "flags": flags}

    value = question["parser"](answer)
    if value is None:
        flags.append(make_flag("uncertain_answer", turn_id, answer))
    elif question.get("dependent_index") is not None:
        intake = record_dependent_answer(
            intake, question["dependent_index"], question["field"], value)
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


def run_interactive(state: dict) -> dict:
    intake = state.get("intake") or {}
    flags = list(state.get("flags") or [])
    missing = (state.get("eligibility") or {}).get("missing")
    notice = build_summary(intake)
    target = None  # a question the user asked to revisit

    while True:
        question = target or next_question(intake, missing)
        if question is None:
            return {"intake": intake, "flags": flags, "open_questions": [],
                    "session_summary": build_summary(intake)}

        reply = interrupt({
            "type": "intake",
            "question": (notice + " " if notice else "") + question["text"],
            "fields": [field_path(question)],
        })

        if wants_to_go_back(reply["answer"]):
            earlier = previous_question(intake, question)
            if earlier is None:
                notice = "We are at the first question, so there is nothing earlier to go back to."
            else:
                target = earlier
                notice = "Of course, let's go back to that one. Your other answers are safe."
            continue

        before = len(flags)
        result = handle_answer(
            {"intake": intake, "flags": flags}, reply["answer"], len(flags) + 1, question
        )
        intake, flags = result["intake"], result["flags"]
        new = {f["type"] for f in flags[before:]}

        if "advice_request" in new:
            notice = ESCALATION_CATALOG["E4"]["user_message"]
            continue
        if "ssn_volunteered" in new:
            notice = ("You don't need to share your Social Security number "
                      "right now, so I have not saved it.")
            continue
        if "third_party_answering" in new:
            notice = ESCALATION_CATALOG["E6"]["user_message"]
            continue
        if "contradiction" in new:
            notice = ("No problem. Your earlier answers are safe. "
                      "Let's finish this question first, and a colleague "
                      "can fix anything that needs changing.")
            continue
        if "out_of_scope_mention" in new:
            notice = ESCALATION_CATALOG["E1"]["user_message"]
            continue

        next_q = next_question(intake, missing)
        return {"intake": intake, "flags": flags,
                "session_summary": build_summary(intake),
                "open_questions": [field_path(next_q)] if next_q else []}
    