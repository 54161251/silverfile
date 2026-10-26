"""The ONLY file that knows P1's shared document format (src/state.py `ExtractedDocument`).

Our rich record (schema.py) carries full provenance for every value. P1's contract currently has no
field for that, so this file squeezes what it can into the fields P1 defined and passes the rest on
through a side file (see agents/extraction.py). If P1 adds a `provenance` field to ExtractedDocument,
this file starts filling it automatically (see `_contract_has`); nothing else needs to change.

Mapping, box by box (what Computation, Rules and Review already read):
    boxes        {"1": 31250, "2": 3400, ..., "a": "***-**-4567"}  numbers are whole-dollar ints, or floats if cents
    confidence   {"1": 0.95, ...}                                   0..1, per box
    unverified   ["1", ...]                                         boxes that need the taxpayer to confirm them
    flags        ["extracted_by=...", "uncertain:1:reason", ...]    plain-text notes for people and the dashboard
    source_file  file name only
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import PurePath

from src.extraction.schema import AGENT_NAME, AGENT_VERSION, CONFIDENCE_THRESHOLD, SSN_BOX, W2Record
from src.security.pii import mask_text
from src.state import ExtractedDocument

# A box listed as unverified must show a confidence below the threshold (P6's Review agent checks this).
_CAP_FOR_UNVERIFIED = CONFIDENCE_THRESHOLD - 0.01


def _contract_has(field: str) -> bool:
    return field in ExtractedDocument.model_fields


def amount_for_contract(value: Decimal | None):
    """Whole dollars become an int, amounts with cents a float (what tax_math.to_decimal expects)."""
    if value is None:
        return None
    return int(value) if value == value.to_integral_value() else float(value)


def provenance_flag(entered_by: str, when: datetime, sha256: str | None, method: str) -> str:
    """One text line carrying who/what entered the values and when (assignment 4.2), inside P1's `flags`."""
    parts = [f"extracted_by={entered_by}", f"method={method}", f"extracted_at={when.isoformat()}"]
    if sha256:
        parts.append(f"source_sha256={sha256[:16]}")
    return "; ".join(parts)


def to_extracted_document(record: W2Record, sha256: str | None = None) -> dict:
    """Build the dict the graph merges into state["documents"]. Validated against P1's model before returning."""
    boxes: dict = {}
    confidence: dict[str, float] = {}
    unverified: list[str] = []
    flags = [provenance_flag(record.entered_by, record.extracted_at, sha256, record.method)]

    for box in sorted(record.fields):
        field = record.fields[box]
        boxes[box] = amount_for_contract(field.value)
        conf = round(field.confidence, 3)
        if field.uncertain:
            unverified.append(box)
            conf = min(conf, _CAP_FOR_UNVERIFIED)
            flags.append(f"uncertain:{box}:{field.status}:{field.reason or 'not read confidently'}")
        confidence[box] = conf

    if record.ssn.status != "absent":
        # Box "a" holds the MASKED number only. The full SSN is never stored (assignment 4.3).
        boxes[SSN_BOX] = record.ssn.masked
        confidence[SSN_BOX] = min(round(record.ssn.confidence, 3), 1.0)
        if record.ssn.status not in ("accepted",):
            flags.append(f"ssn_{record.ssn.status}")
    flags += [f for f in record.flags if f not in flags]

    document = {
        "doc_id": record.doc_id,
        "form": record.form,
        "boxes": boxes,
        "confidence": confidence,
        "unverified": unverified,
        "flags": [mask_text(f) for f in flags],
        "source_file": record.source_file,
    }
    if _contract_has("provenance"):     # future-proof: P1 may add this field
        document["provenance"] = {box: f.provenance.model_dump(mode="json") for box, f in record.fields.items()}
    return ExtractedDocument.model_validate(document).model_dump(mode="json", exclude_none=False)


def structured_passthrough(upload: dict, when: datetime) -> dict:
    """An upload that already carries typed boxes and no picture (the offline demo style).

    Nothing is read, so nothing is claimed: the document is flagged `structured_input_not_ocr` and carries
    no confidence scores. Any SSN-shaped text inside it is masked.
    """
    boxes = {str(k): (mask_text(v) if isinstance(v, str) else v) for k, v in (upload.get("boxes") or {}).items()}
    document = {
        "doc_id": upload["doc_id"],
        "form": upload.get("form", "W-2"),
        "boxes": boxes,
        "confidence": dict(upload.get("confidence") or {}),
        "unverified": list(upload.get("unverified") or []),
        "flags": [provenance_flag(f"{AGENT_NAME}/{AGENT_VERSION} (copied supplied data; nothing was read from an image)",
                                  when, None, "supplied_structured_data"), "structured_input_not_ocr",
                  *[str(f) for f in upload.get("flags") or []]],
        "source_file": PurePath(str(upload["source_file"])).name if upload.get("source_file") else None,
    }
    return ExtractedDocument.model_validate(document).model_dump(mode="json", exclude_none=False)


def unreadable_document(doc_id: str, form: str, source_file: str | None, reason: str, when: datetime) -> dict:
    """A placeholder when a file cannot be used: no boxes, a clear flag, and nothing guessed."""
    document = {
        "doc_id": doc_id, "form": form, "boxes": {}, "confidence": {}, "unverified": [],
        "flags": [provenance_flag(f"{AGENT_NAME}/{AGENT_VERSION}", when, None, "ocr"), f"unreadable_document:{reason}"],
        "source_file": source_file,
    }
    return ExtractedDocument.model_validate(document).model_dump(mode="json", exclude_none=False)
