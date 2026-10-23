from threading import Barrier
import pytest

from src.demo_agents import adapters, sample
from src.memory import open_sessions


def test_parallel_workers_really_overlap_and_join(tmp_path):
    agents = adapters()
    barrier = Barrier(2)
    original = agents["extraction"]
    def extract(state):
        barrier.wait(timeout=5)  # A serial implementation fails this test.
        return original(state)
    agents["extraction"] = extract
    with open_sessions(tmp_path / "state.db", agents) as sessions:
        result = sessions.start("parallel", sample(), mode="demo")
        assert result["status"] == "scaffold_complete"
        assert [d["doc_id"] for d in result["documents"]] == ["w2_1", "w2_2"]
        assert result["lines"] == {}


def test_interrupt_survives_reopening_sqlite(tmp_path):
    path = tmp_path / "state.db"
    with open_sessions(path, adapters()) as sessions:
        result = sessions.start("hitl", sample(hitl=True), mode="demo")
        assert result["__interrupt__"]
        assert result["status"] == "awaiting_human"
        esc_id = result["pending_escalation"]
    with open_sessions(path, adapters()) as sessions:
        result = sessions.resume("hitl", {"escalation_id": esc_id, "option": "verified_continue",
                                          "note": "Synthetic review confirmed", "resolved_by": "test_staff"})
        assert result["status"] == "scaffold_complete"
        assert result["escalations"][0]["resolution"]["resolved_by"] == "test_staff"


def test_review_sendback_recomputes_then_reaudits(tmp_path):
    agents = adapters()
    calls = []
    def compute(state):
        calls.append("compute")
        return {"lines": {}}
    def review(state):
        calls.append("review")
        if len(calls) == 2:
            return {"review_verdict": "revise", "review_findings": [{"target_agent": "computation", "reason": "seeded error"}]}
        return {"review_verdict": "pass", "review_findings": []}
    agents.update(computation=compute, review=review)
    with open_sessions(tmp_path / "state.db", agents) as sessions:
        result = sessions.start("revise", sample(), mode="demo")
        assert result["status"] == "scaffold_complete"
        assert calls == ["compute", "review", "compute", "review"]


def test_missing_input_pauses_and_resumes_intake(tmp_path):
    inputs = sample()
    del inputs["intake"]["taxpayer"]["ssn"]
    with open_sessions(tmp_path / "state.db", adapters()) as sessions:
        result = sessions.start("missing", inputs, mode="demo")
        assert result["__interrupt__"][0].value["type"] == "intake"
        result = sessions.resume("missing", {"intake.taxpayer.ssn": "901-11-1111"})
        assert result["status"] == "scaffold_complete"


def test_D5_actual_graph_stops_pathological_handoffs(tmp_path):
    agents = adapters()
    agents["intake"] = lambda state: {}
    inputs = sample()
    del inputs["intake"]["taxpayer"]["ssn"]
    with open_sessions(tmp_path / "state.db", agents) as sessions:
        result = sessions.start("cycle", inputs, mode="demo")
        assert result["status"] == "awaiting_human"
        assert result["escalations"][-1]["code"] == "E10"


def test_D5_actual_graph_caps_review_revisions(tmp_path, monkeypatch):
    # Isolate E9; production E10 may stop repeated handoffs even sooner.
    monkeypatch.setattr("src.orchestration.HANDOFF_REPEAT_LIMIT", 100)
    agents = adapters()
    agents["review"] = lambda state: {"review_verdict": "revise",
                                        "review_findings": [{"target_agent": "computation"}]}
    with open_sessions(tmp_path / "state.db", agents) as sessions:
        result = sessions.start("review-loop", sample(), mode="demo")
        assert result["status"] == "awaiting_human"
        assert result["escalations"][-1]["code"] == "E9"
        assert result["iterations"] == 3


def test_R17_bad_resume_is_rejected_before_checkpoint(tmp_path):
    inputs = sample()
    del inputs["intake"]["taxpayer"]["ssn"]
    with open_sessions(tmp_path / "state.db", adapters()) as sessions:
        sessions.start("invalid", inputs, mode="demo")
        before = sessions.snapshot("invalid")
        with pytest.raises(ValueError):
            sessions.resume("invalid", {"intake.taxpayer.ssn": "123-45-6789"})
        assert sessions.snapshot("invalid").config == before.config


def test_A2_existing_thread_cannot_be_overwritten(tmp_path):
    with open_sessions(tmp_path / "state.db", adapters()) as sessions:
        sessions.start("one", sample(), mode="demo")
        with pytest.raises(ValueError, match="already exists"):
            sessions.start("one", sample(), mode="demo")
