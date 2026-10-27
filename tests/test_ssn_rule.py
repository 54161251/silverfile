"""P4: the SSN testing-range rule (assignment 3.2). Accepted, rejected and "never ask" cases."""
import pytest

from src.security.ssn import (InvalidTestSsn, check_ssn, is_test_ssn, required_ssn_fields,
                              require_test_ssn, ssn_request_allowed)


@pytest.mark.parametrize("value", [
    "900-00-0001",   # lowest area number in the range
    "999-99-9999",   # highest
    "901-23-4567",
    "901234567",     # no separators
    "901 23 4567",   # spaces
    "  901-23-4567  ",  # surrounding spaces are stripped
    "950-12-3456",
])
def test_accepts_900_series(value):
    assert is_test_ssn(value)


@pytest.mark.parametrize("value", [
    "899-99-9999",   # one below the range
    "123-45-6789",   # an ordinary (real-looking) number
    "000-12-3456",
    "666-12-3456",
    "100-12-3456",
])
def test_rejects_numbers_outside_the_test_range(value):
    result = check_ssn(value)
    assert not result.ok and result.reason == "not_test_range"
    assert result.normalized is None          # the rejected number is not kept


@pytest.mark.parametrize("value", [
    "90-123-4567", "901-2345-67", "9012345678", "90123456",   # wrong grouping / length
    "901-23-456a", "abc-de-fghi", "901-23-4567-",              # letters or junk
    "901-23 4567", "901 23-4567",                              # mixed separators
    "９０１-２３-４５６７",                                      # full-width Unicode digits
    "9²¹-23-4567",                                   # superscript digits
    901234567,                                                 # a bare integer is not text
    ["901-23-4567"], {"ssn": "901-23-4567"}, 9.0,
])
def test_rejects_bad_format(value):
    result = check_ssn(value)
    assert not result.ok and result.reason == "bad_format"


@pytest.mark.parametrize("value", [None, "", "   "])
def test_empty_is_its_own_reason(value):
    assert check_ssn(value).reason == "empty"


def test_normalizes_to_dashed_form_and_masks():
    result = check_ssn("901 23 4567")
    assert result.normalized == "901-23-4567"
    assert result.masked == "***-**-4567"
    assert require_test_ssn("901234567") == "901-23-4567"


def test_rejected_number_never_appears_in_error_repr_or_message():
    real = "123-45-6789"
    with pytest.raises(InvalidTestSsn) as caught:
        require_test_ssn(real)
    assert real not in str(caught.value) and "6789" not in str(caught.value)
    result = check_ssn(real)
    assert real not in repr(result) and real not in str(result) and "6789" not in repr(result)
    assert real not in result.message and "6789" not in result.message
    assert caught.value.reason == "not_test_range"


def test_every_failure_has_a_plain_language_message():
    assert check_ssn("123-45-6789").message.startswith("This practice system only accepts test numbers")
    assert check_ssn("12").message and check_ssn("").message and check_ssn("901-23-4567").message == ""


# --- never request an SSN the return does not need ------------------------------------------------
def test_taxpayer_ssn_always_needed():
    assert required_ssn_fields({}) == ["intake.taxpayer.ssn"]
    assert required_ssn_fields({"filing_status": "single"}) == ["intake.taxpayer.ssn"]


def test_spouse_ssn_only_for_joint_or_separate():
    for status in ("mfj", "mfs"):
        assert "intake.spouse.ssn" in required_ssn_fields({"filing_status": status})
    for status in ("single", "hoh", "qss"):
        assert "intake.spouse.ssn" not in required_ssn_fields({"filing_status": status})


def test_one_dependent_ssn_per_listed_dependent():
    intake = {"filing_status": "hoh", "dependents": [{"name": "A"}, {"name": "B"}]}
    assert required_ssn_fields(intake)[1:] == ["intake.dependents.0.ssn", "intake.dependents.1.ssn"]


def test_guard_blocks_unneeded_and_repeat_requests():
    single = {"filing_status": "single", "taxpayer": {}}
    assert ssn_request_allowed("intake.taxpayer.ssn", single)
    assert not ssn_request_allowed("intake.spouse.ssn", single)            # single filers have no spouse line
    assert not ssn_request_allowed("intake.employer.ssn", single)          # nobody else ever needs one
    assert not ssn_request_allowed("intake.dependents.0.ssn", single)      # no such dependent
    assert ssn_request_allowed("intake.taxpayer.birth_date", single)       # not an SSN field: not our call
    have = {"filing_status": "single", "taxpayer": {"ssn": "901-23-4567"}}
    assert not ssn_request_allowed("intake.taxpayer.ssn", have)            # already accepted, do not ask again
    bad = {"filing_status": "single", "taxpayer": {"ssn": "123-45-6789"}}
    assert ssn_request_allowed("intake.taxpayer.ssn", bad)                 # a rejected value does not count as held


def test_guard_handles_dependent_lists():
    intake = {"filing_status": "hoh", "dependents": [{"ssn": "901-23-4567"}, {"name": "B"}]}
    assert not ssn_request_allowed("intake.dependents.0.ssn", intake)
    assert ssn_request_allowed("intake.dependents.1.ssn", intake)


def test_agrees_with_the_other_teams_checks():
    """Our rule must say the same thing as the copies in state.py, rules.py and the UI screen."""
    from src.agents.rules import TEST_SSN as rules_pattern
    from src.state import validate_intake
    for value in ["901-23-4567", "901234567", "899-12-3456", "123-45-6789", "000-00-0000"]:
        mine = is_test_ssn(value)
        assert mine == bool(rules_pattern.match(value))
        try:
            validate_intake({"taxpayer": {"ssn": value}})
            theirs = True
        except ValueError:
            theirs = False
        assert mine == theirs
