import pytest
from src.orchestration import orchestrate
from src.human import apply_resolution


def test_D5_review_bound_triggers_E9():
    result = orchestrate({"last_agent": "review", "review_verdict": "revise", "iterations": 3,
                          "review_findings": [{"target_agent": "computation"}]})
    assert result["escalations"][0]["code"] == "E9"


def test_D5_pathological_handoff_triggers_E10():
    result = orchestrate({"last_agent": "intake", "handoff_history": [["intake", "rules"]] * 2})
    assert result["escalations"][0]["code"] == "E10"


def test_R10_missing_input_routes_back_to_intake():
    result = orchestrate({"last_agent": "rules", "eligibility": {"missing": ["intake.taxpayer.ssn"]}})
    assert result["next_agent"] == "intake"


def test_E4_gate_interrupts_as_well_as_stop():
    result = orchestrate({"escalations": [{"id": "esc_0001", "kind": "GATE", "status": "open"}]})
    assert result["next_agent"] == "human"


def pending():
    return {"intake": {"taxpayer": {"birth_date": "1955-01-01"}}, "pending_escalation": "esc_0001",
            "escalations": [{"id": "esc_0001", "code": "E2", "status": "open", "options": ["choose_value"]}]}


def response(**changes):
    return dict(escalation_id="esc_0001", option="choose_value", note="Confirmed synthetic input",
                resolved_by="test_staff", overrides={"intake.taxpayer.ssn": "901-11-1111"}) | changes


def test_resolution_keeps_answers_and_records_actor_and_time():
    state = pending()
    result = apply_resolution(state, response())
    assert result["intake"]["taxpayer"] == {"birth_date": "1955-01-01", "ssn": "901-11-1111"}
    assert "ssn" not in state["intake"]["taxpayer"]
    assert result["escalations"][0]["resolution"]["resolved_at"]
    assert result["escalations"][0]["resolution"]["resolved_by"] == "test_staff"


@pytest.mark.parametrize("changes", [{"escalation_id": "esc_0002"}, {"option": "invalid"},
                                   {"overrides": {"intake.taxpayer.ssn": "123-45-6789"}},
                                   {"overrides": {"status": "draft_ready"}}])
def test_resolution_rejects_wrong_id_option_or_unsafe_override(changes):
    with pytest.raises(ValueError):
        apply_resolution(pending(), response(**changes))
