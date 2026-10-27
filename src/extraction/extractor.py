"""Turn one W-2 file into a typed W2Record with provenance on every value (P4).

This is the "no interpretation" layer: it copies what is printed on the form, says how sure it is, and
records where each value came from. It never decides what a number means for the return and never adds
numbers together.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from src.extraction.ocr import OcrBackend, TesseractBackend, file_sha256, load_pages, read_w2_page
from src.extraction.schema import (AGENT_NAME, OcrUnavailable, UnreadableDocument, AGENT_VERSION, MONEY_BOXES, SSN_BOX, SSN_BOX_LABEL,
                                   ExtractedField, FieldProvenance, SsnReading, W2Record)

__all__ = ["OcrUnavailable", "UnreadableDocument", "default_backend", "extract_w2"]

_WITHHELD_REASON = ("this document's Social Security number is not a test number, so no amounts are used "
                    "from it (a person must review)")


_backend: OcrBackend | None = None


def default_backend() -> OcrBackend:
    """The Tesseract engine, created once. Raises OcrUnavailable with install instructions if it is missing."""
    global _backend
    if _backend is None:
        if not TesseractBackend.available():
            raise OcrUnavailable(
                "The Tesseract OCR program is not installed. Install it (macOS: `brew install tesseract`; "
                "Ubuntu/Docker: `apt-get install tesseract-ocr`; Windows: the UB Mannheim installer), "
                "then run `pip install -r requirements.txt`.")
        _backend = TesseractBackend()
    return _backend


def extract_w2(path: Path, doc_id: str, *, backend: OcrBackend | None = None,
               now: datetime | None = None) -> tuple[W2Record, str]:
    """Read a W-2 image or PDF. Returns (record, sha256 of the file). Raises UnreadableDocument for bad files."""
    now = now or datetime.now(timezone.utc)
    pages = load_pages(path)                      # may raise UnreadableDocument (safe message)
    sha = file_sha256(path)
    backend = backend or default_backend()        # after the file check, so a bad file is flagged even with no OCR
    entered_by = f"{AGENT_NAME}/{AGENT_VERSION} ({backend.name})"

    # Use the page on which most box labels were found (a PDF may start with a cover sheet).
    scored = []
    for number, page in enumerate(pages, start=1):
        results = read_w2_page(page, backend)
        scored.append((sum(1 for r in results.values() if r.location is not None), -number, number, results))
    _, _, page_no, results = max(scored)

    def provenance(box: str, label: str, result) -> FieldProvenance:
        return FieldProvenance(
            source_document=doc_id, source_file=path.name, source_sha256=sha, page=page_no, box=box,
            box_label=label, entered_by=entered_by, method="ocr", timestamp=now, location=result.location,
            raw_text=None if box == SSN_BOX else result.raw_text)

    fields: dict[str, ExtractedField] = {}
    for box, label in MONEY_BOXES.items():
        r = results[box]
        fields[box] = ExtractedField(box=box, value=r.value, confidence=min(max(r.confidence, 0.0), 1.0),
                                     status=r.status, reason=r.reason, provenance=provenance(box, label, r))

    ssn_result = results[SSN_BOX]
    ssn = SsnReading(status=ssn_result.ssn_status or "unreadable", masked=ssn_result.ssn_masked or "***-**-****",
                     confidence=min(max(ssn_result.confidence, 0.0), 1.0),
                     provenance=provenance(SSN_BOX, SSN_BOX_LABEL, ssn_result))
    flags: list[str] = []
    if ssn.status == "not_test_range":
        # Fail closed: this looks like a real person's document. Keep none of its amounts.
        flags.append("ssn_not_test_range")
        ssn = ssn.model_copy(update={"masked": "***-**-****"})
        for box, field in fields.items():
            fields[box] = field.model_copy(update={"value": None, "status": "uncertain",
                                                   "confidence": min(field.confidence, 0.5),
                                                   "reason": _WITHHELD_REASON})
    return (W2Record(doc_id=doc_id, source_file=path.name, method="ocr", fields=fields, ssn=ssn, flags=flags,
                     extracted_at=now, entered_by=entered_by), sha)
