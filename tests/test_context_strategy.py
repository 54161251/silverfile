"""Spec 4.5 context strategy and Intake document briefing, with a mocked model (R14)."""
from types import SimpleNamespace

import pytest

from src import batch
from src.agents import intake_briefing as ib


class FakeMessages:
    """Stands in for client.beta.messages: reports input tokens from the request size."""

    def __init__(self, replies=None):
        self.requests, self.replies = [], list(replies or [])

    def parse(self, **request):
        self.requests.append(request)
        reply = self.replies.pop(0) if self.replies else "ok"
        size = (len(request["system"]) + sum(len(m["content"]) for m in request["messages"])) // 4
        parsed = None if reply == "refusal" else ib.DocumentBriefing(message="We read your W-2. Does it look right?")
        return SimpleNamespace(stop_reason="refusal" if reply == "refusal" else "end_turn", parsed_output=parsed,
                               usage=SimpleNamespace(input_tokens=size, cache_creation_input_tokens=0,
                                                     cache_read_input_tokens=0))


def fake_client(replies=None):
    return SimpleNamespace(beta=SimpleNamespace(messages=FakeMessages(replies)))


def fake_extract(state):
    upload = state["uploads"][0]
    return {"documents": [{"doc_id": upload["doc_id"], "form": "W-2",
                           "boxes": {"1": 41250, "2": 3300, "a": "***-**-3456"}, "unverified": [],
                           "flags": ["extracted_by=w2-extraction-agent/1.0; extracted_at=2026-10-26T12:00:00"]}]}


@pytest.fixture(autouse=True)
def model_env(monkeypatch):
    monkeypatch.setenv("SILVERFILE_MODEL", "test-model")
    monkeypatch.setenv("SILVERFILE_REFUSAL_FALLBACK", "default")


def run(strategy, client):
    return [row["input_tokens"] for row in batch.run_batch(strategy, client=client, extract=fake_extract)]


def test_D3_selective_recall_is_flat_and_full_history_grows():
    off, on = run("full_history", fake_client()), run("selective_recall", fake_client())
    assert len(off) == len(on) == 10
    assert all(later > earlier for earlier, later in zip(off, off[1:]))  # grows every document
    assert off[-1] > 2 * off[0]
    assert max(on) - min(on) < (off[-1] - off[0]) / 10                    # materially flatter


def test_D3_request_shapes():
    done = [{"document": fake_extract({"uploads": [{"doc_id": f"w2_{i}"}]})["documents"][0],
             "briefing": ib.DocumentBriefing(message="m", boxes_to_confirm=["2"])} for i in range(4)]
    current = fake_extract({"uploads": [{"doc_id": "w2_9"}]})["documents"][0]
    assert len(ib.build_messages("full_history", done, current)) == 9
    (only,) = ib.build_messages("selective_recall", done, current)
    assert "4 W-2" in only["content"] and "w2_3 box 2" in only["content"]


def test_R17_model_sees_no_flags_timestamps_or_full_ssn():
    client = fake_client()
    run("full_history", client)
    sent = str(client.beta.messages.requests[-1]["messages"])
    assert "extracted_at" not in sent and "flags" not in sent
    assert "***-**-3456" in sent and "906-12" not in sent


def test_selective_recall_summary_stays_bounded_with_many_pending_boxes():
    done = [{"document": {"doc_id": f"w2_{i}", "form": "W-2"},
             "briefing": ib.DocumentBriefing(message="m", boxes_to_confirm=["1", "2"])} for i in range(40)]
    assert len(ib.session_summary(done)) < 300


def test_R8_refusal_is_retried_once():
    client = fake_client(["refusal", "ok"])
    briefing, _ = ib.brief(client, [{"role": "user", "content": "x"}])
    assert briefing.message and len(client.beta.messages.requests) == 2


def test_R8_two_failures_raise_for_E8():
    with pytest.raises(ib.BriefingFailed):
        ib.brief(fake_client(["refusal", "refusal"]), [{"role": "user", "content": "x"}])


def test_R6_model_and_fallback_come_from_environment(monkeypatch):
    client = fake_client()
    ib.brief(client, [{"role": "user", "content": "x"}])
    request = client.beta.messages.requests[-1]
    assert request["model"] == "test-model" and request["fallbacks"] == "default"
    assert "temperature" not in request
    monkeypatch.setenv("SILVERFILE_REFUSAL_FALLBACK", "")
    ib.brief(client, [{"role": "user", "content": "x"}])
    assert "fallbacks" not in client.beta.messages.requests[-1]
    monkeypatch.delenv("SILVERFILE_MODEL")
    with pytest.raises(ib.BriefingFailed):
        ib.brief(client, [{"role": "user", "content": "x"}])


def test_metrics_page_lists_both_strategies_and_labels_estimates(tmp_path):
    results, doc = tmp_path / "results", tmp_path / "metrics.md"
    for strategy in ib.STRATEGIES:
        rows = batch.run_batch(strategy, estimate=True, extract=fake_extract)
        batch.save_run(strategy, rows, estimate=True, model=None, results=results)
    text = batch.write_metrics(results, doc).read_text()
    assert "Not measured yet" in text and "These are estimates" in text
    assert text.count("| 10 (w2_batch_10) |") == 1


def test_R5_offline_estimate_keeps_the_measured_table_already_on_the_page(tmp_path):
    results, doc = tmp_path / "results", tmp_path / "metrics.md"
    for strategy in ib.STRATEGIES:   # a real run: its raw files exist when the page is first written
        rows = batch.run_batch(strategy, estimate=True, extract=fake_extract)
        batch.save_run(strategy, rows, estimate=False, model="claude-test", results=results)
    measured = batch.write_metrics(results, doc).read_text()
    assert "Not measured yet" not in measured and "Model: claude-test." in measured
    for path in results.glob("actual_*.json"):   # fresh clone: raw files are not in git
        path.unlink()
    rows = batch.run_batch("selective_recall", estimate=True, extract=fake_extract)
    batch.save_run("selective_recall", rows, estimate=True, model=None, results=results)
    after = batch.write_metrics(results, doc).read_text()
    assert "Not measured yet" not in after
    section = lambda text: text.split(batch.ACTUAL_HEADING)[1].split("\n## ")[0]
    assert section(after) == section(measured) and "| 10 (w2_batch_10) |" in section(after)
    assert "## Estimated input tokens (offline, no API call)" in after


def test_R5_a_new_measured_run_replaces_the_kept_table(tmp_path):
    results, doc = tmp_path / "results", tmp_path / "metrics.md"
    for model in ("claude-old", "claude-new"):
        for strategy in ib.STRATEGIES:
            rows = batch.run_batch(strategy, estimate=True, extract=fake_extract)
            batch.save_run(strategy, rows, estimate=False, model=model, results=results)
        text = batch.write_metrics(results, doc).read_text()
    assert "Model: claude-new." in text and "claude-old" not in text

