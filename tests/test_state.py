from itertools import permutations

import pytest
from pydantic import ValidationError
from src.state import Provenance, ResumePayload, validate_intake, validate_update
from src.state import merge_documents


def test_R10_agent_cannot_write_another_agents_field():
    with pytest.raises(ValueError, match="outside"):
        validate_update("review", {"lines": {}})


def test_A19_real_ssn_rejected_before_checkpoint():
    with pytest.raises(ValueError, match="synthetic"):
        validate_intake({"dependents": [{"ssn": "123-45-6789"}]})


def test_R8_computed_money_requires_evidence():
    with pytest.raises(ValidationError):
        Provenance(line="9", value=100, kind="computed", timestamp="2026-10-23T12:00:00Z")


def test_R8_staff_identity_cannot_be_whitespace():
    with pytest.raises(ValidationError):
        ResumePayload(escalation_id="esc_0001", option="acknowledge", note="ok", resolved_by=" ")


def test_merge_order_is_independent_and_idempotent():
    records = [{"doc_id": name, "form": "W-2", "boxes": {"1": 100}} for name in ["b", "a", "c"]]
    expected = merge_documents([], records)
    for order in permutations(records):
        state = []
        for record in order:
            state = merge_documents(state, [record])
        assert state == expected
        assert merge_documents(state, state) == expected


def test_merge_order_conflict_does_not_silently_overwrite():
    doc = {"doc_id": "a", "form": "W-2", "boxes": {"1": 100}}
    with pytest.raises(ValueError, match="Conflicting"):
        merge_documents([doc], [doc | {"boxes": {"1": 200}}])
