from copy import deepcopy

from langgraph.types import interrupt

from src.agents.intake import run_interactive
from src.demo_agents import adapters, sample
from src.memory import open_sessions
from src.orchestration import orchestrate
from src.progress import progress_key


def test_P3_real_intake_five_turns_persist_and_only_then_routes_to_rules(tmp_path):
    agents = adapters()
    assert agents["intake"] is run_interactive
    checked = []
    original = agents["rules"]
    def rules(state):
        checked.append(deepcopy(state["intake"]))
        return original(state)
    agents["rules"] = rules
    inputs = sample()
    inputs["intake"] = {"taxpayer": {"ssn": "901-11-1111"}}
    path = tmp_path / "session.db"
    questions = ["intake.filing_status", "intake.taxpayer.birth_date", "intake.taxpayer.blind",
                 "intake.dual_status_alien", "intake.can_be_claimed_as_dependent"]
    answers = ["single", "June 1, 1955", "no", "no", "no"]
    with open_sessions(path, agents) as sessions:
        result = sessions.start("p3", inputs, mode="demo")
    for field, answer in zip(questions, answers):
        payload = result["__interrupt__"][0].value
        assert payload["type"] == "intake" and payload["fields"] == [field]
        assert payload["question"]
        assert not checked  # Rules never sees a half-finished basic questionnaire.
        # Every answer reopens SQLite, matching separate UI requests/restarts.
        with open_sessions(path, agents) as sessions:
            result = sessions.resume("p3", {"answer": answer})
    assert result["status"] == "scaffold_complete"
    assert len(checked) == 1 and checked[0]["taxpayer"]["blind"] is False
    assert result["open_questions"] == []


def test_D5_ninety_new_answers_do_not_hit_stall_or_lifetime_limit(tmp_path):
    agents = adapters()
    def intake(state):
        data = deepcopy(state["intake"])
        answers = data.setdefault("answers", {})
        field = f"q{len(answers)}"
        reply = interrupt({"type": "intake", "question": field, "fields": [f"intake.answers.{field}"]})
        answers[field] = reply["answer"]
        return {"intake": data, "open_questions": [f"intake.answers.q{len(answers)}"] if len(answers) < 90 else []}
    agents["intake"] = intake
    with open_sessions(tmp_path / "session.db", agents) as sessions:
        result = sessions.start("long", sample(), mode="demo")
        for index in range(90):
            assert result["__interrupt__"][0].value["type"] == "intake"
            result = sessions.resume("long", {"answer": f"answer-{index}"})
        assert result["status"] == "scaffold_complete"
        assert result["total_handoffs"] > 80
        assert result["escalations"] == []


def test_D5_identical_question_without_recorded_answers_still_stops(tmp_path):
    agents = adapters()
    def intake(state):
        interrupt({"type": "intake", "question": "Same question", "fields": ["intake.unanswered"]})
        return {"open_questions": ["intake.unanswered"]}  # Deliberately discard the answer.
    agents["intake"] = intake
    with open_sessions(tmp_path / "session.db", agents) as sessions:
        result = sessions.start("stuck", sample(), mode="demo")
        for _ in range(3):
            result = sessions.resume("stuck", {"answer": "not recorded"})
        assert result["status"] == "awaiting_human"
        assert result["escalations"][-1]["code"] == "E10"


def test_D5_timestamps_and_queue_churn_do_not_count_as_answer_progress():
    initial = {"intake": {"filing_status": "single"},
               "user_inputs": {"26": {"value": 0, "timestamp": "old"}}}
    changed = deepcopy(initial)
    changed["user_inputs"]["26"]["timestamp"] = "new"
    changed.update(session_summary="new summary", open_questions=["another.prompt"])
    assert progress_key(initial) == progress_key(changed)


def test_D5_alternating_old_answers_cannot_reset_guard_forever():
    state = {"last_agent": "intake", "open_questions": ["intake.answer"]}
    result = {}
    for answer in ["A", "B"] * 6:
        state["intake"] = {"answer": answer}
        result = orchestrate(state)
        if result.get("escalations"):
            break
        state.update(result)
    assert result["escalations"][0]["code"] == "E10"


def test_E8_new_uncertainty_flag_checks_rules_before_next_question(tmp_path):
    with open_sessions(tmp_path / "session.db", adapters()) as sessions:
        sessions.start("uncertain", {"intake": {}}, mode="demo")
        result = sessions.resume("uncertain", {"answer": "it's complicated"})
        assert result["status"] == "awaiting_human"
        assert result["escalations"][-1]["code"] == "E8"


def test_E5_widowed_answer_goes_to_staff_as_filing_status_ambiguity(tmp_path):
    with open_sessions(tmp_path / "session.db", adapters()) as sessions:
        sessions.start("widowed", {"intake": {}}, mode="demo")
        result = sessions.resume("widowed", {"answer": "widowed"})
        assert result["status"] == "awaiting_human"
        assert [e["code"] for e in result["escalations"]] == ["E5"]


def test_P3_question_queue_without_progress_routes_to_intake():
    assert orchestrate({"last_agent": "intake", "open_questions": ["intake.taxpayer.blind"]})["next_agent"] == "intake"
