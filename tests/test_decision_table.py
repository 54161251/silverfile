"""Decision-table tests for the Eligibility & Rules agent (P5).

One test per E-rule (R13) plus eligibility, 12d, senior-deduction and scope rules.
Run from the repo root: python -m pytest tests/test_decision_table.py
"""
import copy
import re
from pathlib import Path

import pytest

from src.agents import rules

POLICY_PATH = Path(__file__).resolve().parents[1] / "data" / "policy.md"
B4_FIELDS = {"eligibility", "filing_status_validated", "box_count_12d", "schedules",
             "scope", "escalations", "citations"}

CLEAN = {
    "intake": {
        "filing_status": "mfj",
        "taxpayer": {"birth_date": "1955-06-01", "blind": False, "ssn": "901-11-1111"},
        "spouse": {"birth_date": "1963-09-15", "blind": True, "ssn": "902-22-2222"},
        "document_inventory": ["W-2", "1099-R", "SSA-1099"],
        "refund": {"method": "direct_deposit", "account_owner": "joint"},
    },
    "documents": [
        {"doc_id": "w2_1", "form": "W-2", "boxes": {"1": 48250, "2": 5120}},
        {"doc_id": "1099r_1", "form": "1099-R", "boxes": {"1": 12000, "2a": 12000, "7": "7"}},
        {"doc_id": "ssa1099_1", "form": "SSA-1099", "boxes": {"5": 21000}},
    ],
    "flags": [],
    "user_inputs": {},
    "escalations": [],
}


def make(**changes):
    """Clean state with `intake` keys (or whole top-level keys) overridden."""
    state = copy.deepcopy(CLEAN)
    for key, value in changes.items():
        if key in state:
            state[key] = value
        else:
            state["intake"][key] = value
    return state


def codes(out):
    return [e["code"] for e in out["escalations"]]


def flag(fid, ftype):
    return {"id": fid, "type": ftype, "turn_id": 1, "excerpt": "***",
            "raised_at": "2026-10-27T14:04:40-04:00"}


# --- Boundaries and the clean path -------------------------------------------------

def test_B4_writes_only_own_fields():
    assert set(rules.run(make())) == B4_FIELDS


def test_clean_mfj_return_has_no_escalations():
    out = rules.run(make())
    assert out["escalations"] == []
    assert out["scope"]["in_scope"] is True
    assert out["filing_status_validated"] == "mfj"
    assert out["eligibility"]["form_1040sr_eligible"] is True


def test_every_citation_points_at_an_existing_policy_anchor():
    headings = re.findall(r"^## (.+)$", POLICY_PATH.read_text(), flags=re.M)
    anchors = {re.sub(r"[^a-z0-9 -]", "", h.lower()).replace(" ", "-") for h in headings}
    state = make(flags=[flag("flag_1", t) for t in list(rules.FLAG_RULES) + ["ssn_volunteered"]])
    out = rules.run(state)
    cited = {c["citation"].removeprefix("policy.md#") for c in out["citations"]}
    assert cited and cited <= anchors


def test_escalation_records_match_contract():
    out = rules.run(make(flags=[flag("flag_0012", "unknown_refund_account")]))
    (esc,) = out["escalations"]
    assert set(esc) == {"id", "code", "kind", "raised_by", "reason", "evidence", "options",
                        "status", "created_at", "resolution"}
    assert esc["id"] == "esc_0001" and esc["status"] == "open" and esc["resolution"] is None
    assert esc["evidence"] == ["flag_0012"]
    assert esc["options"] == ["flag_for_review", "verified_continue", "close_session"]


# --- A3 / A4: 1040-SR eligibility and the age-65 test -------------------------------

@pytest.mark.parametrize("birth_date, senior", [("1961-01-01", True), ("1961-01-02", False)])
def test_A3_birth_date_cutoff(birth_date, senior):
    out = rules.run(make(filing_status="single", spouse=None,
                         taxpayer={"birth_date": birth_date, "ssn": "901-11-1111"}))
    assert out["eligibility"]["taxpayer_65_or_older"] is senior
    assert ("E7" in codes(out)) is (not senior)


def test_A3_one_spouse_is_enough_on_mfj():
    state = make(taxpayer={"birth_date": "1970-01-01", "ssn": "901-11-1111"},
                 spouse={"birth_date": "1958-01-01", "ssn": "902-22-2222"})
    out = rules.run(state)
    assert out["eligibility"]["form_1040sr_eligible"] is True
    assert "E7" not in codes(out)


def test_A3_missing_birth_date_is_reported_not_guessed():
    out = rules.run(make(taxpayer={"ssn": "901-11-1111"}, spouse=None, filing_status="single"))
    assert out["eligibility"]["form_1040sr_eligible"] is None
    assert "intake.taxpayer.birth_date" in out["eligibility"]["missing"]
    assert out["escalations"] == []


# --- C10: line 12d -------------------------------------------------------------------

def test_C10_box_count_mfj_counts_both_spouses():
    # taxpayer 65+, spouse blind but under 65
    assert rules.run(make())["box_count_12d"] == 2


def test_C10_spouse_boxes_ignored_unless_mfj():
    state = make(filing_status="mfs", taxpayer={"birth_date": "1955-06-01", "blind": True,
                                                "ssn": "901-11-1111"})
    assert rules.run(state)["box_count_12d"] == 2


def test_C10_mfs_claiming_spouse_boxes_escalates_E7():
    out = rules.run(make(filing_status="mfs", mfs_claim_spouse_boxes=True))
    assert "E7" in codes(out)


# --- A12 / C12: senior deduction qualifiers --------------------------------------------

def test_A12_senior_deduction_two_qualifiers_on_mfj():
    state = make(spouse={"birth_date": "1959-01-01", "ssn": "902-22-2222"})
    assert rules.run(state)["eligibility"]["senior_deduction_qualifiers"] == ["taxpayer", "spouse"]


def test_A12_senior_deduction_is_zero_for_mfs():
    out = rules.run(make(filing_status="mfs"))
    assert out["eligibility"]["senior_deduction_qualifiers"] == []
    assert out["schedules"]["schedule_1a"] is False


def test_A12_missing_ssn_is_reported_to_intake_not_silently_dropped():
    out = rules.run(make(taxpayer={"birth_date": "1955-06-01", "ssn": None}))
    assert "taxpayer" not in out["eligibility"]["senior_deduction_qualifiers"]
    assert "intake.taxpayer.ssn" in out["eligibility"]["missing"]


@pytest.mark.parametrize("ssn", [None, "", "123-45-6789"])
def test_A19_spouse_ssn_missing_or_invalid_on_mfj(ssn):
    out = rules.run(make(spouse={"birth_date": "1959-01-01", "ssn": ssn}))
    assert "intake.spouse.ssn" in out["eligibility"]["missing"]
    assert out["eligibility"]["senior_deduction_qualifiers"] == ["taxpayer"]


def test_A20_incomplete_dependent_is_reported():
    out = rules.run(make(dependents=[{"name": "Alex Doe", "relationship": "grandchild"}]))
    assert out["eligibility"]["missing"] == ["intake.dependents.0.ssn"]


def test_clean_return_reports_nothing_missing():
    assert rules.run(make())["eligibility"]["missing"] == []


# --- E1: out of scope --------------------------------------------------------------------

def test_E1_out_of_scope_mention_flag():
    out = rules.run(make(flags=[flag("flag_1", "out_of_scope_mention")]))
    assert codes(out) == ["E1"]
    assert out["scope"]["in_scope"] is False


@pytest.mark.parametrize("item", sorted(rules.OUT_OF_SCOPE_ITEMS))
def test_E1_out_of_scope_intake_item(item):
    assert codes(rules.run(make(out_of_scope_items=[item]))) == ["E1"]


def test_E1_unsupported_document_form():
    docs = CLEAN["documents"] + [{"doc_id": "1099nec_1", "form": "1099-NEC", "boxes": {"1": 900}}]
    assert "E1" in codes(rules.run(make(documents=docs)))


def test_E1_1099R_code_other_than_7():
    docs = copy.deepcopy(CLEAN["documents"])
    docs[1]["boxes"]["7"] = "1"
    assert codes(rules.run(make(documents=docs))) == ["E1"]


def test_E1_1099DIV_capital_gain_distribution():
    docs = CLEAN["documents"] + [{"doc_id": "1099div_1", "form": "1099-DIV",
                                  "boxes": {"1a": 300, "1b": 200, "2a": 50}}]
    out = rules.run(make(documents=docs, document_inventory=None))
    assert codes(out) == ["E1"]


def test_E1_social_security_mfs_lived_with_spouse():
    assert "E1" in codes(rules.run(make(filing_status="mfs", mfs_lived_with_spouse=True)))


def test_E1_social_security_lump_sum():
    assert "E1" in codes(rules.run(make(ss_lump_sum_prior_year=True)))


# --- E2: conflicts -------------------------------------------------------------------------

def test_E2_document_not_in_stated_inventory():
    out = rules.run(make(document_inventory=["W-2", "SSA-1099"]))  # "no pension"
    assert codes(out) == ["E2"]
    assert "doc:1099r_1" in out["escalations"][0]["evidence"]


def test_E2_stated_age_conflicts_with_birth_date():
    state = make(taxpayer={"birth_date": "1955-06-01", "ssn": "901-11-1111", "stated_age": 62})
    assert codes(rules.run(state)) == ["E2"]


def test_E2_stated_age_one_year_later_is_accepted():
    state = make(taxpayer={"birth_date": "1955-06-01", "ssn": "901-11-1111", "stated_age": 71})
    assert codes(rules.run(state)) == []


def test_E2_contradiction_flag():
    assert codes(rules.run(make(flags=[flag("flag_2", "contradiction")]))) == ["E2"]


# --- E3: 1099-R box 2b --------------------------------------------------------------------

def test_E3_1099R_taxable_amount_not_determined():
    docs = copy.deepcopy(CLEAN["documents"])
    docs[1]["boxes"]["2b_not_determined"] = True
    out = rules.run(make(documents=docs))
    assert codes(out) == ["E3"]
    assert out["scope"]["in_scope"] is False


def test_E3_from_extraction_flag():
    docs = copy.deepcopy(CLEAN["documents"])
    docs[1]["flags"] = ["taxable_amount_not_determined"]
    assert codes(rules.run(make(documents=docs))) == ["E3"]


# --- E4: advice is a GATE -----------------------------------------------------------------

def test_E4_advice_request_is_gate_and_keeps_scope():
    out = rules.run(make(flags=[flag("flag_3", "advice_request")]))
    assert codes(out) == ["E4"]
    assert out["escalations"][0]["kind"] == "GATE"
    assert out["scope"]["in_scope"] is True


# --- E5: filing-status ambiguity -------------------------------------------------------------

@pytest.mark.parametrize("changes", [
    {"spouse": {"birth_date": "1950-01-01", "ssn": "902-22-2222", "date_of_death": "2025-08-02"}},
    {"filing_status": "qss"},
    {"filing_status": "hoh", "spouse": None},
    {"marital_status_unclear": True},
    {"filing_status": "single"},
], ids=["spouse_died", "qss", "hoh_no_qualifying_person", "unclear", "single_with_spouse"])
def test_E5_filing_status_ambiguity(changes):
    out = rules.run(make(**changes))
    assert "E5" in codes(out)
    assert out["filing_status_validated"] is None


def test_married_without_spouse_details_asks_intake_instead_of_escalating():
    # Rules can run mid-Intake (e.g. after "I'm not sure"), before the spouse questions are reached.
    out = rules.run(make(spouse=None))
    assert "E5" not in codes(out)
    assert {"intake.spouse.birth_date", "intake.spouse.ssn"} <= set(out["eligibility"]["missing"])


def test_E5_hoh_with_qualifying_person_is_fine():
    out = rules.run(make(filing_status="hoh", spouse=None, hoh_qualifying_person=True))
    assert codes(out) == []
    assert out["filing_status_validated"] == "hoh"


# --- E6: exploitation / third-party pressure ---------------------------------------------------

@pytest.mark.parametrize("ftype", ["third_party_answering", "unknown_refund_account",
                                   "pressure_signal"])
def test_E6_exploitation_flags_stop(ftype):
    out = rules.run(make(flags=[flag("flag_4", ftype)]))
    assert codes(out) == ["E6"]
    assert out["escalations"][0]["kind"] == "STOP"


@pytest.mark.parametrize("owner", ["other", "unknown", None])
def test_E6_refund_to_account_not_in_taxpayer_name(owner):
    assert codes(rules.run(make(refund={"method": "direct_deposit", "account_owner": owner}))) == ["E6"]


def test_E6_reason_never_contains_excerpt():
    f = flag("flag_5", "pressure_signal") | {"excerpt": "my nephew told me to say that"}
    out = rules.run(make(flags=[f]))
    assert "nephew" not in str(out)


# --- E7: wrong form / chart does not apply ------------------------------------------------------

@pytest.mark.parametrize("changes", [
    {"can_be_claimed_as_dependent": True},
    {"dual_status_alien": True},
    {"filing_status": "mfs", "mfs_spouse_itemizes": True},
], ids=["dependent", "dual_status", "mfs_spouse_itemizes"])
def test_E7_standard_deduction_chart_does_not_apply(changes):
    assert "E7" in codes(rules.run(make(**changes)))


# --- Document checks: Extraction flags and low-confidence boxes ---------------------------------

def with_w2(**fields):
    docs = copy.deepcopy(CLEAN["documents"])
    docs[0] |= fields
    return docs


def test_E7_w2_with_non_test_ssn():
    out = rules.run(make(documents=with_w2(boxes={"1": None, "2": None},
                                           flags=["ssn_not_test_range"])))
    assert codes(out) == ["E7"]
    assert out["escalations"][0]["kind"] == "STOP"


def test_E8_unreadable_document():
    docs = with_w2(boxes={}, flags=["unreadable_document:file_not_found_or_unsupported_type"])
    assert codes(rules.run(make(documents=docs))) == ["E8"]


def test_E8_unconfirmed_low_confidence_box_the_return_uses():
    out = rules.run(make(documents=with_w2(unverified=["2"])))
    assert codes(out) == ["E8"]
    assert out["escalations"][0]["evidence"] == ["doc:w2_1.box.2"]


def test_D4_confirmed_low_confidence_box_does_not_escalate():
    state = make(documents=with_w2(unverified=["2"]),
                 user_inputs={"w2_1.2": {"value": 5120, "kind": "human_resolution"}})
    assert codes(rules.run(state)) == []


def test_D4_low_confidence_box_the_return_does_not_use_is_ignored():
    assert codes(rules.run(make(documents=with_w2(unverified=["3"], flags=["ssn_unreadable"])))) == []


# --- E8: honest uncertainty -----------------------------------------------------------------------

def test_E8_uncertain_answer_is_gate():
    out = rules.run(make(flags=[flag("flag_6", "uncertain_answer")]))
    assert codes(out) == ["E8"]
    assert out["escalations"][0]["kind"] == "GATE"


def test_E8_unknown_flag_type_defaults_to_uncertainty():
    assert codes(rules.run(make(flags=[flag("flag_7", "something_new")]))) == ["E8"]


def test_R17_volunteered_ssn_does_not_escalate():
    assert codes(rules.run(make(flags=[flag("flag_8", "ssn_volunteered")]))) == []


# --- Re-runs after send-back or resolution ----------------------------------------------------------

def test_rerun_does_not_duplicate_open_escalation():
    state = make(flags=[flag("flag_9", "pressure_signal")])
    first = rules.run(state)
    state["escalations"] = first["escalations"]
    assert rules.run(state)["escalations"] == []


def resolve(esc, option, resolved_by="staff_jlee"):
    return esc | {"status": "resolved",
                  "resolution": {"option": option, "resolved_by": resolved_by, "note": "ok"}}


def test_resolved_continue_clears_scope_item():
    state = make(out_of_scope_items=["state_return"])
    esc = rules.run(state)["escalations"][0]
    state["escalations"] = [resolve(esc, "not_applicable_continue")]
    out = rules.run(state)
    assert out["escalations"] == []
    assert out["scope"]["in_scope"] is True


@pytest.mark.parametrize("resolution", [
    None,
    {},
    {"option": "not_applicable_continue"},                            # no staff name
    {"option": "verified_continue", "resolved_by": "staff_jlee"},     # not an E1 option
], ids=["none", "empty", "no_resolved_by", "wrong_option"])
def test_incomplete_resolution_does_not_clear(resolution):
    state = make(out_of_scope_items=["state_return"])
    esc = rules.run(state)["escalations"][0]
    state["escalations"] = [esc | {"status": "resolved", "resolution": resolution}]
    out = rules.run(state)
    assert codes(out) == ["E1"]
    assert out["escalations"][0]["id"] == "esc_0002"
    assert out["scope"]["in_scope"] is False


def test_E6_changed_refund_owner_after_approval_escalates_again():
    state = make(refund={"method": "direct_deposit", "account_owner": "other"})
    esc = rules.run(state)["escalations"][0]
    state["escalations"] = [resolve(esc, "verified_continue")]
    assert rules.run(state)["escalations"] == []

    state["intake"]["refund"]["account_owner"] = "unknown"
    assert codes(rules.run(state)) == ["E6"]


def test_E1_changed_1099R_code_after_approval_escalates_again():
    docs = copy.deepcopy(CLEAN["documents"])
    docs[1]["boxes"]["7"] = "1"
    state = make(documents=docs)
    esc = rules.run(state)["escalations"][0]
    state["escalations"] = [resolve(esc, "not_applicable_continue")]
    assert rules.run(state)["escalations"] == []

    state["documents"][1]["boxes"]["7"] = "2"
    assert codes(rules.run(state)) == ["E1"]


def test_E5_staff_setting_filing_status_does_not_loop():
    spouse = {"birth_date": "1950-01-01", "ssn": "902-22-2222", "date_of_death": "2025-08-02"}
    state = make(spouse=spouse)
    esc = rules.run(state)["escalations"][0]
    state["escalations"] = [resolve(esc, "set_filing_status")]
    state["intake"]["filing_status"] = "single"   # the staff override, applied by P1
    out = rules.run(state)
    assert out["escalations"] == []
    assert out["filing_status_validated"] == "single"


def test_new_escalation_ids_continue_after_existing():
    state = make(flags=[flag("flag_10", "advice_request")],
                 escalations=[{"id": "esc_0007", "code": "E9", "reason": "x", "evidence": []}])
    assert rules.run(state)["escalations"][0]["id"] == "esc_0008"


def test_E5_marital_status_unclear_without_any_filing_status():
    # Intake records this instead of a status for "widowed", "divorced", "separated".
    state = make(marital_status_unclear=True)
    state["intake"].pop("filing_status")
    out = rules.run(state)
    assert codes(out) == ["E5"]
    assert out["filing_status_validated"] is None
