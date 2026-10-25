"""P7 dashboard data layer: listing, grouping, staff auth and resolution through resume (B7)."""
import pytest

from src.dashboard.auth import Staff, authenticate, load_env_file, sign_in_available
from src.dashboard.resolution import build_payload, parse_value, suggested_path, taxpayer_message
from src.dashboard.store import Store
from src.demo_agents import adapters, sample
from src.memory import open_sessions

ENV = {"SILVERFILE_STAFF_IDS": "staff_jlee, demo_staff", "SILVERFILE_STAFF_PASSCODE": "synthetic-pass"}


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "sessions.sqlite"
    with open_sessions(path, adapters()) as sessions:
        sessions.start("clean-1", sample(), mode="demo")
        sessions.start("hitl-1", sample(hitl=True), mode="demo")
        missing = sample()
        del missing["intake"]["taxpayer"]["birth_date"]  # Real P3 question, not the retired fixture adapter.
        sessions.start("waiting-1", missing, mode="demo")
    return path


def test_B7_lists_every_session_grouped_for_staff(db):
    rows = {r.thread_id: r for r in Store(db).summaries()}
    assert set(rows) == {"clean-1", "hitl-1", "waiting-1"}
    assert rows["hitl-1"].group == "needs_staff"
    assert rows["hitl-1"].pending["code"] == "E6"
    assert rows["hitl-1"].open_codes == ["E6"]
    assert rows["clean-1"].group == "completed"
    assert rows["waiting-1"].group == "waiting_taxpayer"
    assert "intake.taxpayer.birth_date" in rows["waiting-1"].intake_fields
    assert [r.group for r in Store(db).summaries()][0] == "needs_staff"  # queue first


def test_B7_missing_database_is_an_empty_list(tmp_path):
    assert Store(tmp_path / "none.sqlite").summaries() == []


def test_E6_staff_resolution_resumes_graph_and_logs_actor(db):
    store = Store(db)
    summary, _ = store.state("hitl-1")
    payload = build_payload(summary.pending, "verified_continue", "Called taxpayer; account is hers.",
                            "staff_jlee")
    after = store.resolve("hitl-1", payload, Staff("staff_jlee"))
    assert after.group == "completed"
    _, state = store.state("hitl-1")
    resolution = state["escalations"][0]["resolution"]
    assert resolution["resolved_by"] == "staff_jlee" and resolution["option"] == "verified_continue"
    assert resolution["resolved_at"] and resolution["note"]


def test_B7_resolution_requires_signed_in_staff_as_actor(db):
    store = Store(db)
    summary, _ = store.state("hitl-1")
    payload = build_payload(summary.pending, "verified_continue", "note", "someone_else")
    with pytest.raises(PermissionError):
        store.resolve("hitl-1", payload, Staff("staff_jlee"))
    with pytest.raises(PermissionError):
        store.resolve("hitl-1", payload, None)


def test_B7_stale_resolution_is_refused(db):
    store = Store(db)
    summary, _ = store.state("hitl-1")
    payload = build_payload(summary.pending, "verified_continue", "first click", "staff_jlee")
    store.resolve("hitl-1", payload, Staff("staff_jlee"))
    with pytest.raises(ValueError):
        store.resolve("hitl-1", payload, Staff("staff_jlee"))  # double submit


def test_E6_closing_option_closes_session(db):
    store = Store(db)
    summary, _ = store.state("hitl-1")
    payload = build_payload(summary.pending, "close_session", "Taxpayer asked to stop.", "demo_staff")
    assert store.resolve("hitl-1", payload, Staff("demo_staff")).group == "closed"


def test_R6_sign_in_fails_closed_without_configuration():
    assert not sign_in_available({})
    assert authenticate("staff_jlee", "", {}) is None
    assert authenticate("staff_jlee", "anything", {"SILVERFILE_STAFF_IDS": "staff_jlee"}) is None


def test_R6_sign_in_checks_id_and_passcode():
    assert authenticate("Staff_JLee ", "synthetic-pass", ENV) == Staff("staff_jlee")
    assert authenticate("staff_jlee", "wrong", ENV) is None
    assert authenticate("intruder", "synthetic-pass", ENV) is None


def test_R16_env_file_never_overrides_real_environment(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("# comment\nSILVERFILE_STAFF_IDS=from_file\nexport OTHER='x'\n", encoding="utf-8")
    environ = {"SILVERFILE_STAFF_IDS": "from_env"}
    load_env_file(env_file, environ)
    assert environ == {"SILVERFILE_STAFF_IDS": "from_env", "OTHER": "x"}


ESC = {"id": "esc_0003", "code": "E5", "kind": "STOP", "options": ["set_filing_status", "convert_to_client_call"],
       "status": "open", "evidence": ["intake.spouse.date_of_death@ab12cd34"]}


def test_E5_set_filing_status_requires_a_valid_status():
    with pytest.raises(ValueError):
        build_payload(ESC, "set_filing_status", "Spoke with taxpayer", "staff_jlee", "intake.filing_status", "")
    payload = build_payload(ESC, "set_filing_status", "Spoke with taxpayer", "staff_jlee",
                            suggested_path(ESC), "qss")
    assert payload["overrides"] == {"intake.filing_status": "qss"}


def test_E2_override_paths_limited_to_runtime_prefixes():
    esc = ESC | {"code": "E2", "options": ["choose_value"], "evidence": ["intake.taxpayer.stated_age@1a2b"]}
    assert suggested_path(esc) == "intake.taxpayer.stated_age"
    with pytest.raises(ValueError):
        build_payload(esc, "choose_value", "Checked ID", "staff_jlee", "lines.16", 5)
    payload = build_payload(esc, "choose_value", "Checked ID", "staff_jlee", "intake.taxpayer.stated_age",
                            parse_value("intake.taxpayer.stated_age", "71"))
    assert payload["overrides"] == {"intake.taxpayer.stated_age": 71}


def test_B7_note_and_known_option_required():
    with pytest.raises(ValueError):
        build_payload(ESC, "convert_to_client_call", "   ", "staff_jlee")
    with pytest.raises(ValueError):
        build_payload(ESC, "verified_continue", "note", "staff_jlee")
    with pytest.raises(ValueError):
        build_payload(ESC | {"status": "resolved"}, "convert_to_client_call", "note", "staff_jlee")


def test_R9_amount_parsing_is_whole_dollars_without_arithmetic():
    assert parse_value("user_inputs.26", "$1,250") == 1250
    with pytest.raises(ValueError):
        parse_value("user_inputs.26", "1250.50")
    with pytest.raises(ValueError):
        parse_value("user_inputs.26", "1000+250")


def test_E4_taxpayer_message_comes_from_rules_catalog():
    assert "volunteer preparer" in taxpayer_message("E4")
    assert taxpayer_message("E9")
