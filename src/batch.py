"""Spec 4.5 batch: 10 documents for one household, in order, in one session (A24, D1).

Each document goes through the production Extraction agent (OCR), then Intake's document
briefing (src/agents/intake_briefing.py). Per-document input tokens are saved for the
strategy used, and docs/metrics.md is rebuilt from whatever runs exist.

    python run.py batch                         # selective recall (context strategy on)
    python run.py batch --no-context-strategy   # full history
    python run.py batch --estimate              # offline: no API call, estimated tokens

Actual counts are the usage the API reports. --estimate counts characters / 4 and stands in
a fixed-length placeholder for earlier briefings; its numbers are labeled as estimates.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from src.agents.intake_briefing import PROMPT, DocumentBriefing, brief, build_messages

REPO = Path(__file__).resolve().parents[1]
MANIFEST = REPO / "data" / "fixtures" / "batch" / "manifest.json"
RESULTS = REPO / "runtime" / "metrics"
METRICS_DOC = REPO / "docs" / "metrics.md"
LABELS = {"full_history": "Strategy disabled (full history)",
          "selective_recall": "Strategy enabled (selective recall)"}
STAND_IN = DocumentBriefing(message="x" * 300, boxes_to_confirm=[])


def estimate_tokens(messages: list[dict]) -> int:
    return (len(PROMPT) + sum(len(m["content"]) for m in messages)) // 4


def run_batch(strategy: str, *, client=None, estimate: bool = False, manifest: Path = MANIFEST,
              extract=None, session_id: str = "batch") -> list[dict]:
    if extract is None:
        from src.agents.extraction import run as extract
    uploads = json.loads(Path(manifest).read_text(encoding="utf-8"))["uploads"]
    done, rows = [], []
    for number, upload in enumerate(uploads, start=1):
        document = extract({"session_id": session_id, "uploads": [upload]})["documents"][0]
        messages = build_messages(strategy, done, document)
        if estimate:
            briefing, tokens = STAND_IN, estimate_tokens(messages)
        else:
            briefing, tokens = brief(client, messages)
        done.append({"document": document, "briefing": briefing})
        rows.append({"n": number, "doc_id": document["doc_id"], "input_tokens": tokens,
                     "boxes_to_confirm": briefing.boxes_to_confirm})
    return rows


def save_run(strategy: str, rows: list[dict], *, estimate: bool, model: str | None,
             results: Path = RESULTS) -> Path:
    results.mkdir(parents=True, exist_ok=True)
    kind = "estimated" if estimate else "actual"
    path = results / f"{kind}_{strategy}.json"
    path.write_text(json.dumps({"strategy": strategy, "kind": kind, "model": None if estimate else model,
                                "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                "rows": rows}, indent=2) + "\n", encoding="utf-8")
    return path


def _table(runs: dict) -> list[str]:
    off, on = runs.get("full_history"), runs.get("selective_recall")
    count = max(len(r["rows"]) for r in runs.values())
    lines = [f"| Document | {LABELS['full_history']} | {LABELS['selective_recall']} |", "|---|---:|---:|"]
    for i in range(count):
        cells = [f"{r['rows'][i]['input_tokens']:,}" if r and i < len(r["rows"]) else "not run"
                 for r in (off, on)]
        doc = next(r["rows"][i]["doc_id"] for r in (off, on) if r and i < len(r["rows"]))
        lines.append(f"| {i + 1} ({doc}) | {cells[0]} | {cells[1]} |")
    for label, r in (("disabled", off), ("enabled", on)):
        if r:
            first, last = r["rows"][0]["input_tokens"], r["rows"][-1]["input_tokens"]
            lines.append(f"\nStrategy {label}: document 1 = {first:,} tokens, document {len(r['rows'])} = "
                         f"{last:,} tokens ({last / first:.1f}x).")
    return lines


def write_metrics(results: Path = RESULTS, doc: Path = METRICS_DOC) -> Path:
    runs = {}
    for path in sorted(results.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        runs.setdefault(data["kind"], {})[data["strategy"]] = data
    out = ["# Context Strategy Measurements (spec 4.5)", "",
           "Batch: the 10 W-2 images in `data/fixtures/batch/` for one household (A24, D1), processed in "
           "order in one session by `python run.py batch`. Each document is read by the production "
           "Extraction agent (OCR), then Intake's document briefing calls the model "
           "(`src/agents/intake_briefing.py`, prompt `src/prompts/document_briefing.md`).", "",
           "- **Disabled** (`--no-context-strategy`): every earlier document and briefing is resent.",
           "- **Enabled** (default, D3 selective recall): the current document plus a code-built "
           "summary of session decisions that does not grow with the number of documents.", ""]
    actual = runs.get("actual")
    out.append("## Actual input tokens (API usage)")
    out.append("")
    if actual:
        models = sorted({r["model"] for r in actual.values() if r.get("model")})
        out.append(f"Reported by the API as `usage.input_tokens` plus cache tokens. Model: "
                   f"{', '.join(models) or 'not recorded'}.")
        out.append("")
        out += _table(actual)
    else:
        out.append("Not measured yet: run both commands with a key in `.env` "
                   "(`SILVERFILE_MODEL`, `ANTHROPIC_API_KEY`).")
    if runs.get("estimated"):
        out += ["", "## Estimated input tokens (offline, no API call)", "",
                "Characters / 4, including the system prompt; earlier briefings replaced by a "
                "300-character stand-in. These are estimates, not API usage.", ""]
        out += _table(runs["estimated"])
    out += ["", "## Reproduce", "", "```sh", "python run.py batch --no-context-strategy",
            "python run.py batch", "```", "",
            "Each run saves `runtime/metrics/<actual|estimated>_<strategy>.json` and rebuilds this page."]
    doc.write_text("\n".join(out) + "\n", encoding="utf-8")
    return doc
