from src.agents.intake import (
    next_question,
    parse_birth_date,
    parse_filing_status,
    parse_yes_no,
    run,
)


def test_filing_status_married_maps_to_mfj():
    assert parse_filing_status("Married") == "mfj"


def test_widowed_is_not_guessed():
    assert parse_filing_status("widowed") is None


def test_birth_date_formats():
    assert parse_birth_date("03/05/1958") == "1958-03-05"
    assert parse_birth_date("March 5, 1958") == "1958-03-05"
    assert parse_birth_date("banana") is None


def test_yes_no():
    assert parse_yes_no("yes") is True
    assert parse_yes_no("no") is False
    assert parse_yes_no("maybe") is None


def test_questions_asked_in_order():
    assert next_question({})["field"] == "filing_status"
    assert next_question({"filing_status": "single"})["field"] == "birth_date"


def test_false_answer_is_not_asked_again():
    intake = {"filing_status": "single",
              "taxpayer": {"birth_date": "1958-03-05", "blind": False}}
    assert next_question(intake) is None


def test_earlier_answers_are_kept():
    first = run({"latest_answer": "single"})
    second = run({"intake": first["intake"], "latest_answer": "March 5, 1958"})
    assert second["intake"]["filing_status"] == "single"
    assert second["intake"]["taxpayer"]["birth_date"] == "1958-03-05"


def test_unclear_answer_raises_uncertain_flag():
    result = run({"latest_answer": "widowed"})
    assert result["intake"] == {}
    assert result["flags"][0]["type"] == "uncertain_answer"