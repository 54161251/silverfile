"""Intake document briefing and context strategy (P3, B2; spec 4.5, D3).

After each document is read, Intake tells the taxpayer in plain words what was read and what
to check. This is SilverFile's model-calling step, so it is where context grows when many
documents are processed in one session (the 10-document batch, A24).

Two ways to build the request for document N:
- full_history (--no-context-strategy): every earlier document and every earlier briefing
  are resent, so input grows with each document.
- selective_recall (default, D3): only the current document plus a short summary of
  session decisions so far. The summary is built in code and has a bounded size.

The model sees only doc_id, form, boxes and unverified boxes: no flags or timestamps, and
the SSN box is already masked by Extraction (R17). Output is parsed into DocumentBriefing
(R8); a refusal or unparseable answer is retried once, then BriefingFailed (E8 for the caller).
The model comes from SILVERFILE_MODEL and defaults to DEFAULT_MODEL (R18, R6); the refusal
fallback comes from the environment (R6).
"""
from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

PROMPT = (Path(__file__).resolve().parents[1] / "prompts" / "document_briefing.md").read_text(encoding="utf-8")
DEFAULT_MODEL = "claude-opus-5-5"  # R18: used when SILVERFILE_MODEL is unset or empty
STRATEGIES = ("selective_recall", "full_history")
PENDING_SHOWN = 5  # keeps the summary bounded however many boxes are pending


class DocumentBriefing(BaseModel):
    message: str = Field(description="Two to four plain sentences for the taxpayer.")
    boxes_to_confirm: list[str] = Field(default_factory=list,
                                        description="Box numbers that were hard to read.")


class BriefingFailed(RuntimeError):
    """The model refused twice or never returned a valid DocumentBriefing (R8 -> E8)."""


def document_view(document: dict) -> dict:
    return {key: document.get(key) for key in ("doc_id", "form", "boxes", "unverified")}


def session_summary(done: list[dict]) -> str:
    """Selective recall: what the session has decided so far, in a size that does not grow."""
    if not done:
        return "Nothing has been read yet in this session."
    forms = Counter(item["document"]["form"] for item in done)
    pending = [f"{item['document']['doc_id']} box {box}"
               for item in done for box in item["briefing"].boxes_to_confirm]
    shown = ", ".join(pending[-PENDING_SHOWN:]) if pending else "none"
    more = f" (and {len(pending) - PENDING_SHOWN} earlier)" if len(pending) > PENDING_SHOWN else ""
    kinds = ", ".join(f"{count} {form}" for form, count in sorted(forms.items()))
    return (f"Documents already read and explained to the taxpayer: {kinds}; the last one was "
            f"{done[-1]['document']['doc_id']}. Amounts still waiting for the taxpayer to confirm: "
            f"{shown}{more}.")


def _document_turn(document: dict) -> str:
    return "Document just read:\n" + json.dumps(document_view(document), sort_keys=True)


def build_messages(strategy: str, done: list[dict], document: dict) -> list[dict]:
    if strategy == "full_history":
        messages = []
        for item in done:
            messages.append({"role": "user", "content": _document_turn(item["document"])})
            messages.append({"role": "assistant", "content": item["briefing"].model_dump_json()})
        messages.append({"role": "user", "content": _document_turn(document)})
        return messages
    if strategy == "selective_recall":
        return [{"role": "user", "content": f"Earlier in this session: {session_summary(done)}\n\n"
                                            + _document_turn(document)}]
    raise ValueError(f"Unknown context strategy {strategy!r}; expected one of {STRATEGIES}")


def _input_tokens(usage) -> int:
    """All input the model read: uncached plus cache writes and reads."""
    return sum(getattr(usage, name, 0) or 0 for name in
               ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))


def model_name() -> str:
    """SILVERFILE_MODEL if set and not blank, otherwise DEFAULT_MODEL."""
    return (os.environ.get("SILVERFILE_MODEL") or "").strip() or DEFAULT_MODEL


def brief(client, messages: list[dict]) -> tuple[DocumentBriefing, int]:
    """One briefing. Returns the parsed output and the input tokens the API reported."""
    request = dict(model=model_name(), max_tokens=4000, system=PROMPT, messages=messages,
                   output_format=DocumentBriefing, output_config={"effort": "low"})
    fallback = os.environ.get("SILVERFILE_REFUSAL_FALLBACK", "").strip()
    if fallback:
        request.update(betas=["server-side-fallback-2026-07-01"], fallbacks=fallback)
    for _attempt in range(2):  # R8: one retry
        try:
            response = client.beta.messages.parse(**request)
        except ValidationError:
            continue
        if response.stop_reason != "refusal" and response.parsed_output is not None:
            return response.parsed_output, _input_tokens(response.usage)
    raise BriefingFailed("No valid briefing after one retry")
