"""Intake agent (P3). The only agent that talks to the taxpayer."""
from __future__ import annotations
from langgraph.types import interrupt
from src.agents.rules import ESCALATION_CATALOG


FILING_STATUS_CHOICES = {
    "single": "single",
    "married filing jointly": "mfj",
    "married filing separately": "mfs",
    "head of household": "hoh",
}


JOINT_WORDS = {"jointly", "joint", "together"}
SEPARATE_WORDS = {"separately", "separate"}
BLOCKING_WORDS = {"widow", "widowed", "widower", "not", "never",
                  "unmarried", "divorced", "separated"}


def parse_filing_status(answer: str) -> str | None:
    """Turn what the user said into one of single/mfj/mfs/hoh, or None."""
    text = answer.strip().lower()
    exact = FILING_STATUS_CHOICES.get(text)
    if exact:
        return exact
    words = set(re.findall(r"[a-z]+", text))
    # Unclear, negated, or human-path cases: do not guess.
    if words & BLOCKING_WORDS:
        return None
    joint = bool(words & JOINT_WORDS)
    separate = bool(words & SEPARATE_WORDS)
    found = set()
    if "single" in words:
        found.add("single")
    if "head" in words and "household" in words:
        found.add("hoh")
    if "married" in words:
        if separate and not joint:
            found.add("mfs")
        elif joint and not separate:
            found.add("mfj")
        else:
            found.add("married?")  # married, but joint or separate is not clear
    result = found.pop() if len(found) == 1 else None
    return None if result == "married?" else result


def is_married_unspecified(answer: str) -> bool:
    """'I am married' with no word about filing together or separately: ask a follow-up."""
    words = set(re.findall(r"[a-z]+", answer.lower()))
    return ("married" in words and "single" not in words
            and not words & BLOCKING_WORDS
            and parse_filing_status(answer) is None)


def parse_joint_or_separate(answer: str) -> str | None:
    """Answer to 'together or separately?': mfj, mfs, or None if unclear."""
    words = set(re.findall(r"[a-z]+", answer.lower()))
    joint = bool(words & JOINT_WORDS)
    separate = bool(words & SEPARATE_WORDS)
    if joint and not separate:
        return "mfj"
    if separate and not joint:
        return "mfs"
    return None

MARITAL_STAFF_WORDS = {"widow", "widowed", "widower", "divorced", "separated"}
DEATH_WORDS = {"died", "passed", "deceased", "death"}
SPOUSE_WORDS = {"spouse", "husband", "wife"}
MARRIED_FOLLOWUP = "Will you file together with your spouse, or separately?"

def needs_filing_status_help(answer: str) -> bool:
    """Widowed, divorced or separated: a colleague settles the filing status (E5), not us.

    Death words count only when the answer also mentions a spouse, husband or wife.
    """
    words = set(re.findall(r"[a-z]+", answer.lower()))
    if words & MARITAL_STAFF_WORDS:
        return True
    return bool(words & DEATH_WORDS and words & SPOUSE_WORDS)

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

ZERO_WORDS = {"none", "no", "nothing", "zero", "nil"}


def parse_amount(answer: str):
    """Turn '$1,200.50', '(500)', '-500' or 'none' into a number, or None if unclear."""
    text = answer.strip().lower().rstrip(".")
    if text in ZERO_WORDS:
        return 0
    match = re.fullmatch(r"(\()?(-)?\$?\s*(\d{1,3}(?:,\d{3})+|\d+)(\.\d{1,2})?(\))?", text)
    if not match or bool(match.group(1)) != bool(match.group(5)):
        return None
    amount = float(match.group(3).replace(",", "") + (match.group(4) or ""))
    if match.group(1) or match.group(2):
        amount = -amount
    return int(amount) if amount == int(amount) else amount


def has_other_amounts(intake: dict) -> bool:
    return intake.get("has_other_amounts") is True


OTHER_AMOUNTS_GATE = {
    "group": None,
    "field": "has_other_amounts",
    "text": ("Do you have any other amounts for 2025 that are not on the forms you gave us? "
             "For example: other income, adjustments to income, extra taxes, tax credits, "
             "or estimated tax payments you already made. Please answer yes or no."),
    "parser": parse_yes_no,
}

# line -> (short label for the summary, question text)
AMOUNT_LINES = {
    "8": ("your other income",
          "How much other income did you have in 2025 that is not on the forms you gave us "
          "(for example, unemployment pay or gambling winnings)? Enter 0 if none. "
          "If it was a loss, put a minus sign in front of the amount."),
    "10": ("your adjustments to income",
           "How much are your adjustments to income for 2025 (for example, a deductible IRA "
           "contribution or student loan interest)? Enter 0 if none."),
    "17": ("your extra tax from Schedule 2, line 3",
           "Do you have an amount for Schedule 2, line 3 (for example, alternative minimum "
           "tax or repaying health-insurance subsidies)? Enter the amount, or 0 if none."),
    "19": ("your child tax credit",
           "How much child tax credit or credit for other dependents do you have for 2025? "
           "Enter 0 if none."),
    "20": ("your other credits",
           "How much do you have from Schedule 3, line 8 (other credits, for example the "
           "foreign tax credit or education credits)? Enter 0 if none."),
    "23": ("your other taxes",
           "How much do you have for other taxes, such as self-employment tax "
           "(Schedule 2, line 21)? Enter 0 if none."),
    "26": ("your estimated tax payments",
           "How much estimated tax did you pay for 2025, including any overpayment from your "
           "2024 return that you applied to 2025? Enter 0 if none."),
}

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
                "United States, or whose immigration status changed, during "
                "the year. Please answer yes or no.",
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

QUESTIONS.extend(
    {"group": "other_amounts", "field": line, "text": text,
     "parser": parse_amount, "only_if": has_other_amounts}
    for line, (_label, text) in AMOUNT_LINES.items()
)


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
        if (path.startswith("intake.other_amounts.")
                and path.rsplit(".", 1)[-1] in AMOUNT_LINES
                and intake.get("has_other_amounts") is None):
            question = OTHER_AMOUNTS_GATE
        else:
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

LABELS.update({f"intake.other_amounts.{line}": label
               for line, (label, _text) in AMOUNT_LINES.items()})

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

    if question["field"] == "filing_status" and needs_filing_status_help(answer):
        intake = record_answer(intake, "marital_status_unclear", True)
        return {"intake": intake, "flags": flags}

    if question["field"] == "filing_status":
        if intake.get("married_pending"):
            value = parse_joint_or_separate(answer)
            if value is None:
                flags.append(make_flag("uncertain_answer", turn_id, answer))
            else:
                intake = {k: v for k, v in intake.items() if k != "married_pending"}
                intake = record_answer(intake, "filing_status", value)
            return {"intake": intake, "flags": flags}
        if is_married_unspecified(answer):
            intake = {k: v for k, v in intake.items() if k != "filing_status"}
            intake = record_answer(intake, "married_pending", True)
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

    if question["field"] == "has_other_amounts" and value is False:
        amounts = dict(intake.get("other_amounts") or {})
        for line in AMOUNT_LINES:
            amounts.setdefault(line, 0)
        intake = record_answer(intake, "other_amounts", amounts)
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

def missing_paths(state: dict) -> list:
    """Paths Rules or Computation say are missing, as intake.* field paths."""
    missing = list((state.get("eligibility") or {}).get("missing") or [])
    for text in state.get("open_questions") or []:
        path = str(text).split(":")[0].strip()
        if path.startswith("user_inputs.") and path.split(".", 1)[1] in AMOUNT_LINES:
            missing.append("intake.other_amounts." + path.split(".", 1)[1])
    return missing


def with_user_inputs(state: dict, intake: dict) -> dict:
    """Copy the answered amounts into user_inputs, where Computation reads them."""
    inputs = dict(state.get("user_inputs") or {})
    inputs.update(intake.get("other_amounts") or {})
    return inputs

# Flags that must reach Rules (and a colleague) before Intake asks anything else.
HANDOVER_FLAGS = (
    ("advice_request", "E4"),
    ("third_party_answering", "E6"),
    ("out_of_scope_mention", "E1"),
)


def _run_interactive(state: dict) -> dict:
    intake = state.get("intake") or {}
    flags = list(state.get("flags") or [])
    missing = missing_paths(state)
    notice = build_summary(intake)
    target = None  # a question the user asked to revisit

    while True:
        question = target or next_question(intake, missing)
        if question is None:
            return {"intake": intake, "flags": flags, "open_questions": [],
                    "session_summary": build_summary(intake)}

        text = question["text"]
        if question["field"] == "filing_status" and intake.get("married_pending"):
            text = MARRIED_FOLLOWUP
        reply = interrupt({
            "type": "intake",
            "question": (notice + " " if notice else "") + text,
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

        for flag_type, code in HANDOVER_FLAGS:
            if flag_type in new:
                # Return now so Rules and a colleague see this flag before any more
                # questions. The unanswered question stays open and is asked again after.
                return {"intake": intake, "flags": flags,
                        "open_questions": [field_path(question)],
                        "session_summary": ESCALATION_CATALOG[code]["user_message"]}
        if "ssn_volunteered" in new:
            notice = ("You don't need to share your Social Security number "
                      "right now, so I have not saved it.")
            continue
        if "contradiction" in new:
            notice = ("No problem. Your earlier answers are safe. "
                      "Let's finish this question first, and a colleague "
                      "can fix anything that needs changing.")
            continue
        if intake.get("marital_status_unclear") and not intake.get("filing_status"):
            # Hand over now (no open questions) so Rules raises E5 for a colleague.
            return {"intake": intake, "flags": flags, "open_questions": [],
                    "session_summary": ESCALATION_CATALOG["E5"]["user_message"]}

        next_q = next_question(intake, missing)
        return {"intake": intake, "flags": flags,
                "session_summary": build_summary(intake),
                "open_questions": [field_path(next_q)] if next_q else []}

def run_interactive(state: dict) -> dict:
    result = _run_interactive(state)
    result["user_inputs"] = with_user_inputs(state, result["intake"])
    return result