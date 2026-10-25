"""P7 taxpayer page for P3's Intake contract (docs/P1_INTAKE_HANDOFF.md; A19, R17, spec §4.3)."""
from pathlib import Path

import pytest

from src.agents.intake import QUESTIONS, field_path
from src.ui.answers import SSN_MARKER, screen
from src.ui.taxpayer_page import covered, normalise_code, starter_inputs

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(Path(__file__).resolve().parents[1] / "streamlit_app.py")
ANSWERS = ["Single", "March 5, 1958", "no", "no", "no"]


def test_A19_ssn_question_accepts_only_900_series():
    fields = ["intake.taxpayer.ssn"]
    assert screen("901 22 3333", fields).send == "901-22-3333"
    assert screen("901-22-3333", fields).shown == "XXX-XX-3333"
    refused = screen("123-45-6789", fields)
    assert refused.send is None and "start with 9" in refused.notice
    assert screen("my number", fields).send is None


def test_R17_volunteered_ssn_is_removed_before_sending():
    checked = screen("single, and my SSN is 123-45-6789", ["intake.filing_status"])
    assert "123-45-6789" not in checked.send and SSN_MARKER in checked.send
    assert checked.notice
    assert screen("I was born 03/05/1958", ["intake.taxpayer.birth_date"]).send == "I was born 03/05/1958"
    assert screen("call 555-123-4567", []).send == "call 555-123-4567"  # a phone number is not an SSN


def test_empty_and_overlong_answers_are_refused():
    assert screen("   ", []).send is None
    assert screen("x" * 501, []).send is None


def test_starter_inputs_leave_every_intake_question_unanswered():
    intake = starter_inputs()["intake"]
    assert covered(intake) == []
    assert all(field_path(q).startswith("intake.") for q in QUESTIONS)
    assert intake["taxpayer"]["ssn"].startswith("9")  # not yet asked by Intake; synthetic


def test_codes_are_forgiving_to_type():
    assert normalise_code(" sf 7k3q 9xpd ") == "SF-7K3Q-9XPD"


@pytest.fixture
def env(tmp_path, monkeypatch):
    db = tmp_path / "sessions.sqlite"
    monkeypatch.setenv("SILVERFILE_DB", str(db))
    return db


def run(app):
    app.run(timeout=30)
    assert not app.exception, [e.value for e in app.exception]
    return app


def answer(app, text):
    app.text_area(key="sf_answer").input(text)
    next(b for b in app.button if b.label == "Send answer").click()
    return run(app)


def test_B2_one_question_at_a_time_to_a_finished_draft(env):
    app = run(AppTest.from_file(APP))
    next(b for b in app.button if b.label == "Start a new return").click()
    run(app)
    code = app.session_state["sf_thread"]
    for text in ANSWERS:
        assert len(app.text_area) == 1  # exactly one open question
        answer(app, text)
    assert any("never files" in s.value for s in app.success)
    from src.dashboard.store import Store
    summary, state = Store(env).state(code)
    assert summary.group == "completed"
    assert state["intake"]["filing_status"] == "single" and state["intake"]["taxpayer"]["birth_date"] == "1958-03-05"


def test_R17_volunteered_ssn_never_reaches_the_database(env):
    app = run(AppTest.from_file(APP))
    next(b for b in app.button if b.label == "Start a new return").click()
    run(app)
    answer(app, "single 123-45-6789")
    assert b"123-45-6789" not in env.read_bytes()
    assert b"123456789" not in env.read_bytes()


def test_E8_not_sure_reaches_staff_and_taxpayer_sees_neutral_message(env):
    app = run(AppTest.from_file(APP))
    next(b for b in app.button if b.label == "Start a new return").click()
    run(app)
    next(b for b in app.button if b.label == "I'm not sure").click()
    run(app)
    assert any("flag this for a volunteer" in i.value for i in app.info)
    assert not app.text_area  # no question while staff decide


def test_resume_by_code_shows_what_was_covered(env):
    first = run(AppTest.from_file(APP))
    next(b for b in first.button if b.label == "Start a new return").click()
    run(first)
    code = first.session_state["sf_thread"]
    answer(first, "Single")
    answer(first, "March 5, 1958")

    later = run(AppTest.from_file(APP))  # a new browser session on Friday
    later.text_input[0].input(code.lower().replace("-", " "))
    next(b for b in later.button if b.label == "Continue").click()
    run(later)
    summary = " ".join(e.body for e in later.expander[0].markdown)
    assert "Single" in summary and "1958-03-05" in summary
    assert len(later.text_area) == 1  # picks up at the blindness question
