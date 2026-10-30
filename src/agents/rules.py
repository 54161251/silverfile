"""Eligibility & Rules agent (B4, owner P5).

Fully deterministic: no LLM call. Every decision is paired with a citation into
data/policy.md, and every escalation (E1-E8) is an escalation record matching data
contract #2.

Reads:  intake, documents, flags, user_inputs, escalations (to avoid re-raising)
Writes: eligibility, filing_status_validated, box_count_12d, schedules, scope,
        escalations, citations   (only these, per B4 / R10)

`escalations` returns only NEW records. The state reducer for that field must append
(or merge by `id`), not replace.

Field names read from `intake` and `documents` are provisional until P1's state.py
lands; they are listed in docs/p5_rules_interface.md. Rename them here, in one place.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

POLICY = "policy.md#"
TZ = ZoneInfo("America/New_York")

# A3/A4: born before 2 Jan 1961 (born 1 Jan 1961 qualifies).
SENIOR_BIRTH_CUTOFF = date(1961, 1, 2)
TAX_YEAR_END = date(2025, 12, 31)

FILING_STATUSES = {"single", "mfj", "mfs", "hoh", "qss"}
IN_SCOPE_FORMS = {"W-2", "1099-INT", "1099-DIV", "1099-R", "SSA-1099"}
TEST_SSN = re.compile(r"^9\d{2}-?\d{2}-?\d{4}$")  # A19: 900-999 only

# 1099-R / 1099-DIV box keys as written by Extraction / fixtures (agree with P4).
BOX_1099R_CODE = "7"
BOX_1099R_NOT_DETERMINED = "2b_not_determined"
BOX_1099DIV_CAP_GAIN = "2a"
DOC_FLAG_NOT_DETERMINED = "taxable_amount_not_determined"

# Extraction flags (P4, src/extraction/contract.py).
DOC_FLAG_REAL_SSN = "ssn_not_test_range"
DOC_FLAG_UNREADABLE = "unreadable_document:"

# Boxes the C-rules take from each form (C1-C6, C17). An unconfirmed low-confidence
# value in one of these blocks the return; other boxes are not used.
USED_BOXES = {
    "W-2": {"1", "2"},
    "1099-INT": {"1", "3", "4", "8"},
    "1099-DIV": {"1a", "1b", "4"},
    "1099-R": {"1", "2a", "4", "qcd_amount"},
    "SSA-1099": {"5", "6"},
}

# Escalation catalog: kind, staff options and the sentence the user hears.
# Options are the snake_case versions of the "Staff resolution options" column.
_SPECIALIST = "That part needs one of our specialists. I've passed it on, and someone will contact you."
ESCALATION_CATALOG = {
    "E1": {"kind": "STOP", "options": ["convert_to_client_call", "not_applicable_continue"],
           "user_message": _SPECIALIST},
    "E2": {"kind": "STOP", "options": ["choose_value"],
           "user_message": "I'm seeing two different answers here, so a colleague will check before we go on."},
    "E3": {"kind": "STOP", "options": ["preparer_enters_amount", "close_session"],
           "user_message": _SPECIALIST},
    "E4": {"kind": "GATE", "options": ["acknowledge"],
           "user_message": "I can't advise on that, but I've noted your question for a volunteer preparer."},
    "E5": {"kind": "STOP", "options": ["set_filing_status", "convert_to_client_call"],
           "user_message": "A colleague will confirm the right filing status with you."},
    "E6": {"kind": "STOP", "options": ["flag_for_review", "verified_continue", "close_session"],
           "user_message": "I need a colleague to look at this before we continue."},
    "E7": {"kind": "STOP", "options": ["close_session", "correct_data_continue"],
           "user_message": _SPECIALIST},
    "E8": {"kind": "GATE", "options": ["enter_value", "contact_client"],
           "user_message": "I'm not sure, so I'll flag this for a volunteer."},
}
# Resolutions after which the triggering condition no longer blocks the return.
CLOSING_OPTIONS = {"close_session", "convert_to_client_call", "flag_for_review"}

# Intake flag type -> (escalation code, neutral reason, policy anchor).
# Reasons never quote the excerpt (R17); the flag id goes in `evidence`.
FLAG_RULES = {
    "out_of_scope_mention": ("E1", "Taxpayer mentioned an out-of-scope item", "out-of-scope"),
    "contradiction": ("E2", "Taxpayer gave conflicting answers", "conflicting-information"),
    "advice_request": ("E4", "Taxpayer asked for tax advice", "no-tax-advice"),
    "third_party_answering": ("E6", "Another person may be answering for the taxpayer",
                              "exploitation-and-third-party-pressure"),
    "unknown_refund_account": ("E6", "Refund account owner not known to taxpayer",
                               "exploitation-and-third-party-pressure"),
    "pressure_signal": ("E6", "Possible outside pressure on the taxpayer's answers",
                        "exploitation-and-third-party-pressure"),
    "uncertain_answer": ("E8", "Taxpayer was unsure of an answer", "honest-uncertainty"),
}
NO_ESCALATION_FLAGS = {"ssn_volunteered"}  # R17: rejected at intake, flag kept only

# Intake out-of-scope category codes -> reason (all E1).
OUT_OF_SCOPE_ITEMS = {
    "itemize": "Taxpayer wants to itemize deductions",
    "self_employment": "Self-employment or business income",
    "rental": "Rental income",
    "capital_gains": "Capital gains requiring Schedule D",
    "digital_assets": "Digital assets",
    "foreign": "Foreign income or accounts",
    "amended_or_prior_year": "Amended or prior-year return",
    "state_return": "State return",
    "tips": "Tips deduction",
    "overtime": "Overtime deduction",
    "car_loan_interest": "Car-loan interest deduction",
}


def run(state: dict) -> dict:
    """Entry point (R10). Returns only the B4 fields."""
    intake = state.get("intake") or {}
    documents = state.get("documents") or []
    flags = state.get("flags") or []
    user_inputs = state.get("user_inputs") or {}
    existing = state.get("escalations") or []

    d = _Decisions()
    status = _check_filing_status(intake, d)
    eligibility = _check_eligibility(intake, status, d)
    box_count = _count_12d_boxes(intake, status, eligibility, d)
    _check_standard_deduction_exclusions(intake, status, d)
    _check_documents(intake, documents, d)
    _check_document_quality(documents, user_inputs, d)
    _check_intake_scope(intake, status, documents, d)
    _check_refund_account(intake, status, d)
    _check_flags(flags, d)
    schedules = _schedules(user_inputs, eligibility, d)

    new_escalations, cleared = _to_escalations(d.triggers, existing)
    blocking = [t for t in d.triggers if t not in cleared]
    status_blocked = any(t["code"] in ("E5", "E7") and t["about_status"] for t in blocking)

    return {
        "eligibility": eligibility,
        "filing_status_validated": None if status is None or status_blocked else status,
        "box_count_12d": box_count,
        "schedules": schedules,
        "scope": {
            "in_scope": not any(t["code"] in ("E1", "E3") for t in blocking),
            "out_of_scope_items": [_public(t) for t in d.triggers if t["code"] in ("E1", "E3")],
            "cleared_by_staff": [_public(t) for t in cleared],
        },
        "escalations": new_escalations,
        "citations": d.citations,
    }


class _Decisions:
    def __init__(self):
        self.triggers: list[dict] = []
        self.citations: list[dict] = []

    def cite(self, decision: str, anchor: str):
        self.citations.append({"decision": decision, "citation": POLICY + anchor})

    def escalate(self, code: str, reason: str, evidence: list[str], anchor: str,
                 about_status: bool = False):
        trigger = {"code": code, "reason": reason, "evidence": evidence,
                   "citation": POLICY + anchor, "about_status": about_status}
        if trigger not in self.triggers:
            self.triggers.append(trigger)
            self.cite(f"escalate_{code}: {reason}", anchor)


# --- Individual checks -------------------------------------------------------------

def _check_filing_status(intake: dict, d: _Decisions) -> str | None:
    status = (intake.get("filing_status") or "").lower() or None
    anchor = "filing-status"
    # Checked first: Intake sets this instead of a status when the taxpayer is widowed,
    # divorced or separated, so there may be no status to validate.
    if intake.get("marital_status_unclear"):
        d.escalate("E5", "Marital status unclear", ["intake.marital_status_unclear"],
                   anchor, about_status=True)
    if status not in FILING_STATUSES:
        return None
    spouse = intake.get("spouse")

    if spouse and spouse.get("date_of_death"):
        d.escalate("E5", "Spouse died in 2025 or earlier",
                   [_fp("intake.spouse.date_of_death", spouse["date_of_death"])],
                   anchor, about_status=True)
    if status == "qss":
        d.escalate("E5", "Qualifying surviving spouse claimed", ["intake.filing_status"],
                   anchor, about_status=True)
    if status == "hoh" and intake.get("hoh_qualifying_person") is not True:
        d.escalate("E5", "Head of household without a confirmed qualifying person",
                   ["intake.hoh_qualifying_person"], anchor, about_status=True)
    # MFJ/MFS with no spouse details yet is not ambiguous: the spouse questions are simply
    # unanswered, so they go to `missing` below and Intake asks them.
    if status in ("single", "hoh") and spouse and not spouse.get("date_of_death"):
        d.escalate("E5", "Unmarried filing status with spouse details", ["intake.spouse"],
                   anchor, about_status=True)

    d.cite(f"filing_status={status}", anchor)
    return status


def _is_senior(person: dict | None) -> bool | None:
    """A3/A4 birth-date test. None when the birth date is unknown."""
    if not person or not person.get("birth_date"):
        return None
    return date.fromisoformat(person["birth_date"]) < SENIOR_BIRTH_CUTOFF


def _check_eligibility(intake: dict, status: str | None, d: _Decisions) -> dict:
    taxpayer = intake.get("taxpayer") or {}
    spouse = intake.get("spouse")
    tp_senior = _is_senior(taxpayer)
    sp_senior = _is_senior(spouse) if status == "mfj" else None

    # Anything listed in `missing` sends the session back to Intake; nothing is guessed.
    missing = []
    if status is None:
        missing.append("intake.filing_status")
    if tp_senior is None:
        missing.append("intake.taxpayer.birth_date")
    if status == "mfj" and sp_senior is None:
        missing.append("intake.spouse.birth_date")
    if not TEST_SSN.match(taxpayer.get("ssn") or ""):
        missing.append("intake.taxpayer.ssn")
    if status in ("mfj", "mfs") and not TEST_SSN.match((spouse or {}).get("ssn") or ""):
        missing.append("intake.spouse.ssn")
    for i, dependent in enumerate(intake.get("dependents") or []):
        for field in ("name", "relationship"):
            if not dependent.get(field):
                missing.append(f"intake.dependents.{i}.{field}")
        if not TEST_SSN.match(dependent.get("ssn") or ""):
            missing.append(f"intake.dependents.{i}.ssn")

    # 1040-SR: one qualifying spouse is enough on MFJ (A3).
    if tp_senior or sp_senior:
        eligible = True
    elif tp_senior is None or (status == "mfj" and sp_senior is None):
        eligible = None
    else:
        eligible = False
        evidence = [_fp("intake.taxpayer.birth_date", taxpayer.get("birth_date"))]
        if status == "mfj":
            evidence.append(_fp("intake.spouse.birth_date", spouse.get("birth_date")))
        d.escalate("E7", "No one on the return was born before 2 January 1961",
                   evidence, "1040-sr-eligibility")
    d.cite(f"form_1040sr_eligible={eligible}", "1040-sr-eligibility")

    for role, person in (("taxpayer", taxpayer), ("spouse", spouse)):
        _check_stated_age(role, person, d)

    # Senior deduction (A12, D11): 65+, valid SSN, not MFS. Spouse only on MFJ.
    qualifiers = []
    if status not in (None, "mfs"):
        if tp_senior and TEST_SSN.match(taxpayer.get("ssn") or ""):
            qualifiers.append("taxpayer")
        if sp_senior and TEST_SSN.match((spouse or {}).get("ssn") or ""):
            qualifiers.append("spouse")
    d.cite(f"senior_deduction_qualifiers={qualifiers}", "senior-deduction")

    return {
        "form_1040sr_eligible": eligible,
        "taxpayer_65_or_older": tp_senior,
        "spouse_65_or_older": sp_senior,
        "senior_deduction_qualifiers": qualifiers,
        "missing": missing,
    }


def _check_stated_age(role: str, person: dict | None, d: _Decisions):
    """E2 if a stated age contradicts the birth date (allowing for the session year)."""
    if not person or person.get("stated_age") is None or not person.get("birth_date"):
        return
    born = date.fromisoformat(person["birth_date"])
    had_birthday = (TAX_YEAR_END.month, TAX_YEAR_END.day) >= (born.month, born.day)
    age_end_2025 = TAX_YEAR_END.year - born.year - (0 if had_birthday else 1)
    if person["stated_age"] not in (age_end_2025, age_end_2025 + 1):
        d.escalate("E2", f"Stated age of {role} does not match birth date",
                   [_fp(f"intake.{role}.stated_age", person["stated_age"]),
                    _fp(f"intake.{role}.birth_date", person["birth_date"])],
                   "conflicting-information")


def _count_12d_boxes(intake: dict, status: str | None, eligibility: dict, d: _Decisions) -> int:
    taxpayer = intake.get("taxpayer") or {}
    spouse = intake.get("spouse") or {}
    count = int(bool(eligibility["taxpayer_65_or_older"])) + int(bool(taxpayer.get("blind")))
    if status == "mfj":
        count += int(bool(eligibility["spouse_65_or_older"])) + int(bool(spouse.get("blind")))
    if status == "mfs" and intake.get("mfs_claim_spouse_boxes"):
        d.escalate("E7", "Spouse age or blindness boxes claimed on a separate return",
                   ["intake.mfs_claim_spouse_boxes"], "line-12d-box-count")
    d.cite(f"box_count_12d={count}", "line-12d-box-count")
    return count


def _check_standard_deduction_exclusions(intake: dict, status: str | None, d: _Decisions):
    anchor = "standard-deduction-exclusions"
    if intake.get("can_be_claimed_as_dependent"):
        d.escalate("E7", "Taxpayer can be claimed as a dependent",
                   ["intake.can_be_claimed_as_dependent"], anchor)
    if intake.get("dual_status_alien"):
        d.escalate("E7", "Dual-status alien", ["intake.dual_status_alien"], anchor)
    if status == "mfs" and intake.get("mfs_spouse_itemizes"):
        d.escalate("E7", "Spouse filing separately itemizes", ["intake.mfs_spouse_itemizes"],
                   anchor, about_status=True)
    d.cite("standard_deduction_only", "standard-deduction")


def _check_documents(intake: dict, documents: list[dict], d: _Decisions):
    inventory = intake.get("document_inventory")
    for doc in documents:
        doc_id, form, boxes = doc.get("doc_id"), doc.get("form"), doc.get("boxes") or {}
        ref = f"doc:{doc_id}"

        if form not in IN_SCOPE_FORMS:
            d.escalate("E1", f"Out-of-scope document {form}", [ref], "in-scope-documents")
            continue
        if inventory is not None and form not in inventory:
            d.escalate("E2", f"Taxpayer did not list a {form}, but one was provided",
                       ["intake.document_inventory", ref], "conflicting-information")

        if form == "1099-R":
            if boxes.get(BOX_1099R_NOT_DETERMINED) or DOC_FLAG_NOT_DETERMINED in (doc.get("flags") or []):
                d.escalate("E3", "1099-R taxable amount not determined", [ref],
                           "1099-r-distributions")
            code = str(boxes.get(BOX_1099R_CODE, "")).strip().upper()
            if code != "7":
                d.escalate("E1", f"1099-R distribution code {code or 'missing'} is not 7",
                           [_fp(ref, code)], "1099-r-distributions")
        cap_gain = boxes.get(BOX_1099DIV_CAP_GAIN) or 0
        if form == "1099-DIV" and cap_gain > 0:
            d.escalate("E1", "1099-DIV capital gain distributions", [_fp(ref, cap_gain)],
                       "dividends")
    d.cite("documents_checked", "in-scope-documents")


def _check_document_quality(documents: list[dict], user_inputs: dict, d: _Decisions):
    """Extraction flags and low-confidence boxes (A19, D4).

    Without these, a blocked document only shows up later as Computation open
    questions that Intake cannot answer, and the session ends in E10 with no reason.
    """
    anchor = "document-checks"
    for doc in documents:
        doc_id, form, flags = doc.get("doc_id"), doc.get("form"), doc.get("flags") or []
        ref = f"doc:{doc_id}"
        if DOC_FLAG_REAL_SSN in flags:
            d.escalate("E7", f"{form} shows an SSN outside the 900-999 test range", [ref], anchor)
        if any(str(f).startswith(DOC_FLAG_UNREADABLE) for f in flags):
            d.escalate("E8", f"{form} could not be read", [ref], anchor)
        for box in sorted(set(doc.get("unverified") or []) & USED_BOXES.get(form, set())):
            if user_inputs.get(f"{doc_id}.{box}") is None:
                d.escalate("E8", f"{form} box {box} was not read confidently",
                           [f"{ref}.box.{box}"], anchor)


def _check_intake_scope(intake: dict, status: str | None, documents: list[dict], d: _Decisions):
    for item in intake.get("out_of_scope_items") or []:
        reason = OUT_OF_SCOPE_ITEMS.get(item, f"Out-of-scope item: {item}")
        d.escalate("E1", reason, [f"intake.out_of_scope_items.{item}"], "out-of-scope")

    has_ssa = any(doc.get("form") == "SSA-1099" for doc in documents)
    if has_ssa and status == "mfs" and intake.get("mfs_lived_with_spouse"):
        d.escalate("E1", "Social Security on a separate return while living with spouse",
                   ["intake.mfs_lived_with_spouse"], "social-security-exclusions")
    if has_ssa and intake.get("ss_lump_sum_prior_year"):
        d.escalate("E1", "Lump-sum Social Security payment for prior years",
                   ["intake.ss_lump_sum_prior_year"], "social-security-exclusions")


def _check_refund_account(intake: dict, status: str | None, d: _Decisions):
    refund = intake.get("refund") or {}
    if refund.get("method") != "direct_deposit":
        return
    allowed = {"taxpayer", "joint"} | ({"spouse"} if status == "mfj" else set())
    owner = refund.get("account_owner")
    if owner not in allowed:
        d.escalate("E6", "Refund account is not in the taxpayer's name",
                   [_fp("intake.refund.account_owner", owner)], "refund-account")


def _check_flags(flags: list[dict], d: _Decisions):
    for flag in flags:
        ftype, fid = flag.get("type"), flag.get("id")
        if ftype in NO_ESCALATION_FLAGS:
            d.cite(f"flag {fid} ({ftype}) recorded, no escalation", "volunteered-ssn")
        elif ftype in FLAG_RULES:
            code, reason, anchor = FLAG_RULES[ftype]
            d.escalate(code, reason, [fid], anchor)
        else:
            # Conservative default for anything we don't recognise.
            d.escalate("E8", f"Unrecognised intake flag type {ftype}", [fid], "honest-uncertainty")


def _has_value(user_inputs: dict, line: str) -> bool:
    entry = user_inputs.get(line)
    value = entry.get("value") if isinstance(entry, dict) else entry
    return bool(value)


def _schedules(user_inputs: dict, eligibility: dict, d: _Decisions) -> dict:
    schedules = {
        "schedule_1": _has_value(user_inputs, "8") or _has_value(user_inputs, "10"),
        "schedule_1a": bool(eligibility["senior_deduction_qualifiers"]),
        "schedule_2": _has_value(user_inputs, "17") or _has_value(user_inputs, "23"),
        "schedule_3": _has_value(user_inputs, "20") or _has_value(user_inputs, "31"),
    }
    d.cite(f"schedules={sorted(k for k, v in schedules.items() if v)}", "schedules")
    return schedules


# --- Escalation records ------------------------------------------------------------

def _now() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def _fp(ref: str, value) -> str:
    """Evidence ref plus a short hash of the value that triggered it.

    A staff resolution then only matches the exact data it was given: if the value
    changes (e.g. a different refund-account owner), the key changes and Rules
    escalates again. Only values that can change while still triggering are
    fingerprinted; the hash keeps the value itself out of the record.
    """
    digest = hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()
    return f"{ref}@{digest[:8]}"


def _key(code: str, reason: str, evidence: list[str]) -> tuple:
    return code, reason, tuple(evidence)


def _public(trigger: dict) -> dict:
    return {k: trigger[k] for k in ("code", "reason", "evidence", "citation")}


def _valid_resolution(escalation: dict) -> bool:
    """Resolved by a named staff member with an option allowed for that E-code."""
    resolution = escalation.get("resolution") or {}
    allowed = ESCALATION_CATALOG.get(escalation.get("code"), {}).get("options", [])
    return (escalation.get("status") == "resolved"
            and resolution.get("option") in allowed
            and bool(resolution.get("resolved_by")))


def _to_escalations(triggers: list[dict], existing: list[dict]) -> tuple[list[dict], list[dict]]:
    """Turn triggers into new escalation records, skipping ones already raised.

    Compared against the latest record with the same key:
    - open: still blocking, not raised again;
    - validly resolved with a continuing option (e.g. "not_applicable_continue"):
      returned in `cleared` so it no longer blocks;
    - validly resolved with a closing option: not raised again;
    - anything else (e.g. "resolved" with no resolution): raised again.
    """
    by_key = {_key(e["code"], e["reason"], e.get("evidence", [])): e for e in existing}
    next_num = 1 + max((int(e["id"].split("_")[1]) for e in existing
                        if str(e.get("id", "")).startswith("esc_")), default=0)
    new, cleared = [], []
    for t in triggers:
        prior = by_key.get(_key(t["code"], t["reason"], t["evidence"]))
        if prior is not None:
            if prior.get("status") == "open":
                continue
            if _valid_resolution(prior):
                if prior["resolution"]["option"] not in CLOSING_OPTIONS:
                    cleared.append(t)
                continue
        catalog = ESCALATION_CATALOG[t["code"]]
        new.append({
            "id": f"esc_{next_num:04d}",
            "code": t["code"],
            "kind": catalog["kind"],
            "raised_by": "rules",
            "reason": t["reason"],
            "evidence": t["evidence"],
            "options": list(catalog["options"]),
            "status": "open",
            "created_at": _now(),
            "resolution": None,
        })
        next_num += 1
    return new, cleared
