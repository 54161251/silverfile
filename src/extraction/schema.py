"""Typed records for the W-2 extraction agent (P4).

Two layers, deliberately separate:

  * THIS FILE: the rich record the extractor builds, including full per-value provenance.
  * contract.py: the only place that knows P1's shared `ExtractedDocument` format. If P1
    changes that format, only contract.py needs to change.

The extractor copies what is printed on the form. It does not interpret tax rules, decide what a
value means for the return, or do arithmetic. "Uncertain" is a first-class outcome: a value we
cannot read confidently is flagged, never guessed.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

AGENT_NAME = "w2-extraction-agent"
AGENT_VERSION = "1.0"

# A value read below this confidence is "uncertain" and must be confirmed by the taxpayer.
# 0.80 is the same threshold P6's Review agent already checks (review.py check P7).
CONFIDENCE_THRESHOLD = 0.80

# W-2 money boxes this agent reads, with the text printed on the form (used to find each box).
# Box "a" (the employee's SSN) is read only to run the SSN rule; it is never stored in full.
MONEY_BOXES: dict[str, str] = {
    "1": "Wages, tips, other compensation",
    "2": "Federal income tax withheld",
    "3": "Social security wages",
    "4": "Social security tax withheld",
    "5": "Medicare wages and tips",
    "6": "Medicare tax withheld",
}
SSN_BOX = "a"
SSN_BOX_LABEL = "Employee's social security number"

FieldStatus = Literal["read", "uncertain", "unreadable"]
EntryMethod = Literal["ocr", "supplied_structured_data"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Word(Strict):
    """One word the OCR engine found, with its position in pixels."""

    text: str
    left: int
    top: int
    width: int
    height: int
    conf: float = Field(ge=-1, le=100)   # percent; -1 means "not a real word" for Tesseract

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height


class FieldProvenance(Strict):
    """Where one extracted value came from (assignment 4.2): document, box, who/what entered it, when."""

    source_document: str                  # the doc_id the rest of the system uses, e.g. "w2_1"
    source_file: str                      # file name only; no folder names from the taxpayer's machine
    source_sha256: str | None = None      # fingerprint of the file, so the exact input can be re-checked
    page: int | None = None
    box: str                              # W-2 box, e.g. "1"
    box_label: str                        # text printed on the form for that box
    entered_by: str                       # which program entered it, e.g. "w2-extraction-agent/1.0 (tesseract 5.3.4)"
    method: EntryMethod
    timestamp: datetime
    location: tuple[int, int, int, int] | None = None   # (left, top, right, bottom) pixels where it was read
    raw_text: str | None = None           # exactly what the OCR engine saw; never set for the SSN box

    @field_validator("timestamp")
    @classmethod
    def has_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamp must include a timezone")
        return value


class ExtractedField(Strict):
    """One value from the form: what was read, how sure we are, and where it came from."""

    box: str
    value: Decimal | None = None          # dollars and cents exactly as printed; None if unreadable
    confidence: float = Field(ge=0, le=1)
    status: FieldStatus
    reason: str | None = None             # plain-language note when status is not "read"
    provenance: FieldProvenance

    @property
    def uncertain(self) -> bool:
        return self.status != "read"


class SsnReading(Strict):
    """What we learned about the employee SSN printed on the W-2. The number itself is NOT kept."""

    status: Literal["accepted", "not_test_range", "unreadable", "absent"]
    masked: str = "***-**-****"           # last four digits only when the number passed the SSN rule
    confidence: float = Field(ge=0, le=1, default=0.0)
    provenance: FieldProvenance | None = None


class W2Record(Strict):
    """Everything extracted from one W-2 document."""

    doc_id: str = Field(min_length=1)
    form: Literal["W-2"] = "W-2"
    source_file: str
    method: EntryMethod
    fields: dict[str, ExtractedField] = Field(default_factory=dict)
    ssn: SsnReading = Field(default_factory=lambda: SsnReading(status="absent"))
    flags: list[str] = Field(default_factory=list)
    extracted_at: datetime
    entered_by: str

    def uncertain_boxes(self) -> list[str]:
        return sorted(box for box, field in self.fields.items() if field.uncertain)
