"""P7 Streamlit dashboard, exercised headlessly with streamlit.testing (B7, E6, R14: no LLM calls)."""
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

from src.demo_agents import adapters, sample  # noqa: E402
from src.memory import open_sessions  # noqa: E402

APP = str(Path(__file__).resolve().parents[1] / "streamlit_app.py")


@pytest.fixture
def env(tmp_path, monkeypatch):
    db = tmp_path / "sessions.sqlite"
    with open_sessions(db, adapters()) as sessions:
        sessions.start("clean-1", sample(), mode="demo")
        sessions.start("hitl-1", sample(hitl=True), mode="demo")
    monkeypatch.setenv("SILVERFILE_DB", str(db))
    monkeypatch.setenv("SILVERFILE_STAFF_IDS", "demo_staff")
    monkeypatch.setenv("SILVERFILE_STAFF_PASSCODE", "synthetic-pass")
    return db


def run(app):
    app.run(timeout=30)
    assert not app.exception, [e.value for e in app.exception]
    return app


def test_B7_overview_counts_and_queue(env):
    app = run(AppTest.from_file(APP))
    metrics = {m.label: m.value for m in app.metric}
    assert metrics["Needs staff"] == "1" and metrics["Draft ready"] == "1"
    assert any(b.label == "Open & resolve" for b in app.button)


def test_B7_resolve_buttons_hidden_until_staff_signs_in(env):
    app = AppTest.from_file(APP)
    app.query_params["thread"] = "hitl-1"
    run(app)
    assert not [b for b in app.button if b.label == "Resolve and resume"]
    assert any("Sign in as Kushim staff" in w.value for w in app.warning)


def test_E6_staff_resolves_hitl_in_dashboard_and_session_resumes(env):
    app = AppTest.from_file(APP)
    app.query_params["thread"] = "hitl-1"
    run(app)
    app.sidebar.text_input[0].input("demo_staff")
    app.sidebar.text_input[1].input("synthetic-pass")
    app.sidebar.button[0].click()
    run(app)
    app.radio[0].set_value("verified_continue")
    app.text_area[0].input("Phoned the taxpayer; the account is hers.")
    next(b for b in app.button if b.label == "Resolve and resume").click()
    run(app)
    assert any("Draft ready" in s.value for s in app.success)
    with open_sessions(env, adapters()) as sessions:
        state = sessions.snapshot("hitl-1").values
    assert state["status"] == "scaffold_complete"
    assert state["escalations"][0]["resolution"]["resolved_by"] == "demo_staff"


def test_B7_wrong_passcode_keeps_dashboard_read_only(env):
    app = run(AppTest.from_file(APP))
    app.sidebar.text_input[0].input("demo_staff")
    app.sidebar.text_input[1].input("guess")
    app.sidebar.button[0].click()
    run(app)
    assert "staff" not in app.session_state
    assert app.sidebar.error


def test_sample_returns_render_without_errors(env):
    app = run(AppTest.from_file(APP))
    assert any(s.label == "Sample return" for s in app.selectbox)
