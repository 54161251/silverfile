"""Document Extraction agent (P4). W-2 images/PDFs in, typed records with provenance out.

Contract (P1, docs/IMPLEMENTATION_NOTES.md): `run(state)` receives `state["uploads"]` holding ONE upload per call
(the graph fans out one worker per document) and returns {"documents": [one ExtractedDocument]} for that
upload's `doc_id`. It writes nothing else.

An upload looks like:
    {"doc_id": "w2_1", "form": "W-2", "source_file": "demo/w2_image_1.jpg"}
`source_file` is a PNG/JPG/TIFF image or a PDF, relative to where the program runs (or the repo root).

What this agent will NOT do: interpret tax rules, decide what a value means for the return, or do any
arithmetic. A value it cannot read confidently is flagged `unverified` so Computation asks the taxpayer to
confirm it, and the SSN on the form is checked against the 900-series rule and kept only in masked form.

Try it:  python -m src.agents.extraction demo/w2_image_1.jpg
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.extraction.contract import structured_passthrough, to_extracted_document, unreadable_document
from src.extraction.schema import SUPPORTED_SUFFIXES, OcrUnavailable, UnreadableDocument
from src.security.pii import install_pii_log_masking, mask_data
from src.state import validate_update

log = logging.getLogger("silverfile.extraction")
REPO_ROOT = Path(__file__).resolve().parents[2]


def _find_file(name: str | None) -> Path | None:
    """Locate an upload on disk: as given, else relative to the repo root. None if there is no such file."""
    if not name:
        return None
    candidate = Path(str(name))
    for path in ([candidate] if candidate.is_absolute() else [Path.cwd() / candidate, REPO_ROOT / candidate]):
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES:
            return path
    return None


def provenance_dir(session_id: str | None) -> Path:
    """Where the full per-value provenance files go. Set SILVERFILE_EXTRACTION_DIR to move it."""
    base = Path(os.environ.get("SILVERFILE_EXTRACTION_DIR") or (REPO_ROOT / "runtime" / "extraction"))
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", session_id or "") or "default"
    return base / safe


def _write_provenance(record, session_id: str | None) -> bool:
    """Save the rich record (every value with source, box, who entered it, timestamp). Best effort, never fatal."""
    try:
        folder = provenance_dir(session_id)
        folder.mkdir(parents=True, exist_ok=True)
        text = json.dumps(record.model_dump(mode="json"), indent=2)
        (folder / f"{re.sub(r'[^A-Za-z0-9_.-]', '_', record.doc_id)}.provenance.json").write_text(text + "\n", encoding="utf-8")
        return True
    except OSError:
        log.warning("could not write the provenance file for %s", record.doc_id)
        return False


def extract_upload(upload: dict, *, session_id: str | None = None, backend=None, now: datetime | None = None) -> dict:
    """One upload in, one contract-valid document dict out. Never raises for a bad FILE (it is flagged instead)."""
    doc_id = upload.get("doc_id")
    if not isinstance(doc_id, str) or not doc_id.strip():
        raise ValueError("Every upload needs a doc_id")
    form = upload.get("form") or "W-2"
    now = now or datetime.now(timezone.utc)
    name = upload.get("source_file")
    path = _find_file(name)
    shown_name = Path(str(name)).name if name else None

    if path is None:
        if upload.get("boxes"):
            log.info("document %s: structured data supplied, nothing to read", doc_id)
            return structured_passthrough(upload, now)
        log.warning("document %s: no readable file was supplied", doc_id)
        return unreadable_document(doc_id, form, shown_name, "file_not_found_or_unsupported_type", now)
    if form != "W-2":
        log.warning("document %s: only W-2 images can be read (got %s)", doc_id, form)
        return unreadable_document(doc_id, form, path.name, "only_w2_images_are_supported", now)
    # Imported here so the agent module loads (and structured demo uploads work) even where Pillow or the
    # OCR engine is not installed; only reading a real image needs them.
    from src.extraction.extractor import extract_w2
    try:
        record, sha = extract_w2(path, doc_id, backend=backend, now=now)
    except UnreadableDocument as exc:
        log.warning("document %s: %s", doc_id, exc)
        return unreadable_document(doc_id, form, path.name, str(exc).replace(" ", "_"), now)

    written = _write_provenance(record, session_id)
    document = to_extracted_document(record, sha)
    if not written:
        document["flags"].append("provenance_file_not_written")
    log.info("document %s: read %d of %d boxes confidently, %d need confirmation, ssn %s",
             doc_id, sum(not f.uncertain for f in record.fields.values()), len(record.fields),
             len(record.uncertain_boxes()), record.ssn.status)
    return document


def run(state: dict) -> dict:
    """Graph entry point: extract every upload in `state["uploads"]` (the graph supplies exactly one)."""
    install_pii_log_masking()               # raw SSN-shaped text can never reach a log from here on
    session_id = state.get("session_id")
    documents = [extract_upload(upload, session_id=session_id) for upload in state.get("uploads") or []]
    return validate_update("extraction", {"documents": documents})


def main(argv: list[str] | None = None) -> int:
    """Command line: read one W-2 and print a masked summary (no raw SSN, no taxpayer name)."""
    args = argv if argv is not None else sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print("usage: python -m src.agents.extraction FILE [DOC_ID]\n"
              "Reads one W-2 image or PDF and prints the extracted boxes as JSON.")
        return 0
    install_pii_log_masking()
    try:
        from src.extraction.extractor import default_backend
        default_backend()
    except OcrUnavailable as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    result = run({"uploads": [{"doc_id": args[1] if len(args) > 1 else "w2_1", "form": "W-2", "source_file": args[0]}]})
    print(json.dumps(mask_data(result["documents"][0]), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
