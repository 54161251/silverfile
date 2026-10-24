"""Fill the official 2025 Form 1040-SR PDF from the draft's line records (stretch, D7).

The blank form is the IRS fillable PDF (data/forms/f1040sr_2025.pdf, from
https://www.irs.gov/pub/irs-pdf/f1040s.pdf, created 9/5/25). Its field names are opaque
(f2_18 = line 11a), so the mapping below was built by drawing every widget's name over the
rendered pages and reading off the line beside it.

Only values that already exist in `lines` are written: no arithmetic happens here (R9).
Line 11b is the form's own copy of 11a ("Amount from line 11a"). SSNs are masked (R17),
bank details are never written (A22), and every page is stamped DRAFT, NOT FILED.
"""
from __future__ import annotations

import io
import re
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf import PageObject
from pypdf.generic import DictionaryObject, NameObject, StreamObject

BLANK_FORM = Path(__file__).resolve().parents[2] / "data" / "forms" / "f1040sr_2025.pdf"

# Short field names; resolve_names() expands them to the unique fully qualified names.
LINE_FIELDS = {
    "1a": "f1_47[0]", "1b": "f1_48[0]", "1c": "f1_49[0]", "1d": "f1_50[0]",
    "1e": "f1_51[0]", "1f": "f1_52[0]", "1g": "f1_53[0]", "1h": "f1_55[0]",
    "1z": "f1_57[0]",
    "2a": "f2_01[0]", "2b": "f2_02[0]", "3a": "f2_03[0]", "3b": "f2_04[0]",
    "4a": "f2_05[0]", "4b": "f2_06[0]", "5a": "f2_08[0]", "5b": "f2_09[0]",
    "6a": "f2_11[0]", "6b": "f2_12[0]", "7": "f2_13[0]", "8": "f2_15[0]",
    "9": "f2_16[0]", "10": "f2_17[0]", "11a": "f2_18[0]", "12e": "f2_20[0]",
    "13a": "f2_21[0]", "13b": "f2_22[0]", "14": "f2_23[0]", "15": "f2_24[0]",
    "16": "f2_26[0]", "17": "f2_27[0]", "18": "f2_28[0]", "19": "f2_29[0]",
    "20": "f2_30[0]", "21": "f2_31[0]", "22": "f2_32[0]", "23": "f2_33[0]",
    "24": "f2_34[0]",
    "25a": "f3_01[0]", "25b": "f3_02[0]", "25c": "f3_03[0]", "25d": "f3_04[0]",
    "26": "f3_05[0]", "27": "f3_07[0]", "28": "f3_08[0]", "29": "f3_09[0]",
    "30": "f3_10[0]", "31": "f3_11[0]", "32": "f3_12[0]", "33": "f3_13[0]",
    "34": "f3_14[0]", "37": "f3_19[0]",
}
COPY_FIELDS = {"f2_19[0]": "11a"}  # line 11b repeats line 11a on the 2025 form
HEADER_FIELDS = {"taxpayer_first": "f1_14[0]", "taxpayer_last": "f1_15[0]",
                 "taxpayer_ssn": "f1_16[0]", "spouse_first": "f1_17[0]",
                 "spouse_last": "f1_18[0]", "spouse_ssn": "f1_19[0]"}
DEPENDENT_FIELDS = [  # (first name, last name, SSN, relationship) for dependents 1-4
    (f"f1_{31 + i}[0]", f"f1_{35 + i}[0]", f"f1_{39 + i}[0]", f"f1_{43 + i}[0]")
    for i in range(4)]
# Filing status boxes share the name c1_8 under two parents; the on-state tells them apart.
PAGE1 = "topmostSubform[0].Page1[0]."
FILING_STATUS_BOXES = {"single": (PAGE1 + "Single_ReadOrder[0].c1_8[0]", "/1"),
                       "mfj": (PAGE1 + "Single_ReadOrder[0].c1_8[1]", "/2"),
                       "mfs": (PAGE1 + "Single_ReadOrder[0].c1_8[2]", "/3"),
                       "hoh": (PAGE1 + "c1_8[0]", "/4"), "qss": (PAGE1 + "c1_8[1]", "/5")}
BOX_12D = {"taxpayer 65 or older": "c2_17[0]", "taxpayer blind": "c2_18[0]",
           "spouse 65 or older": "c2_19[0]", "spouse blind": "c2_20[0]"}


def _qualified(annotation) -> str:
    parts, node = [], annotation
    while node is not None:
        if "/T" in node:
            parts.append(str(node["/T"]))
        node = node.get("/Parent")
        node = node.get_object() if node is not None else None
    return ".".join(reversed(parts))


def _mask(ssn) -> str:
    """Nine characters, because the form's SSN fields are 9-cell comb fields."""
    digits = re.sub(r"\D", "", str(ssn or ""))
    return f"XXXXX{digits[-4:]}" if len(digits) == 9 else ""


def resolve_names(reader: PdfReader) -> dict[str, str]:
    """Short name (f2_18[0]) -> qualified name, for every short name that is unique in the form."""
    found: dict[str, list[str]] = {}
    for name in reader.get_fields() or {}:
        found.setdefault(name.rsplit(".", 1)[-1], []).append(name)
    index = {short: names[0] for short, names in found.items() if len(names) == 1}
    index.update({name: name for names in found.values() for name in names})
    return index


def _split_name(name: str | None) -> tuple[str, str]:
    parts = (name or "").strip().rsplit(" ", 1)
    return (parts[0], parts[1]) if len(parts) == 2 else (parts[0], "")


def field_values(lines: dict, intake: dict | None = None, filing_status: str | None = None) -> tuple[dict, dict]:
    """(text values, checkbox on-states) keyed by field name."""
    intake = intake or {}
    text = {field: f"{lines[line]['value']:,}" for line, field in LINE_FIELDS.items()
            if line in lines and isinstance(lines[line].get("value"), int)}
    for field, source in COPY_FIELDS.items():
        if source in lines:
            text[field] = f"{lines[source]['value']:,}"
    for role in ("taxpayer", "spouse"):
        person = intake.get(role) or {}
        first, last = _split_name(person.get("name"))
        text[HEADER_FIELDS[f"{role}_first"]], text[HEADER_FIELDS[f"{role}_last"]] = first, last
        text[HEADER_FIELDS[f"{role}_ssn"]] = _mask(person.get("ssn"))
    for fields, dependent in zip(DEPENDENT_FIELDS, intake.get("dependents") or []):
        first, last = _split_name(dependent.get("name"))
        for field, value in zip(fields, (first, last, _mask(dependent.get("ssn")), dependent.get("relationship"))):
            text[field] = value or ""
    checks = {}
    status = filing_status or intake.get("filing_status")
    if status in FILING_STATUS_BOXES:
        field, state = FILING_STATUS_BOXES[status]
        checks[field] = state
    for item in (lines.get("12d") or {}).get("inputs", []):
        if item.get("label") in BOX_12D and item.get("value") is True:
            checks[BOX_12D[item["label"]]] = "/1"
    return {k: v for k, v in text.items() if v}, checks


DRAFT_TEXT = "SILVERFILE DRAFT - NOT FILED - FOR KUSHIM STAFF REVIEW"


def _stamp(writer: PdfWriter) -> None:
    """Red DRAFT line drawn into the top margin of every page (page content, so it always prints)."""
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
                             NameObject("/BaseFont"): NameObject("/Helvetica-Bold")})
    for page in writer.pages:
        width, height = float(page.mediabox.width), float(page.mediabox.height)
        stamp = PageObject.create_blank_page(width=width, height=height)
        stamp[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject(
            {NameObject("/SFDraft"): font})})
        content = StreamObject()
        content.set_data(f"q 0.75 0.11 0.11 rg BT /SFDraft 9 Tf 36 {height - 14:.0f} Td ({DRAFT_TEXT}) Tj ET Q".encode())
        stamp.replace_contents(content)
        page.merge_page(stamp)


def fill_pdf(lines: dict, intake: dict | None = None, filing_status: str | None = None,
             blank: Path = BLANK_FORM) -> bytes:
    """Return the filled PDF as bytes."""
    reader = PdfReader(str(blank))
    names = resolve_names(reader)
    short_text, short_checks = field_values(lines, intake, filing_status)
    text = {names[k]: v for k, v in short_text.items()}
    checks = {names[k]: v for k, v in short_checks.items()}
    writer = PdfWriter(clone_from=reader)
    # The IRS file also carries an XFA copy of the form; viewers that prefer XFA would show it
    # blank. Dropping it makes every viewer use the AcroForm fields filled below.
    acroform = writer._root_object["/AcroForm"]
    if "/XFA" in acroform:
        del acroform["/XFA"]
    for page in writer.pages:
        for ref in page.get("/Annots") or []:
            annotation = ref.get_object()
            if annotation.get("/Subtype") != "/Widget":
                continue
            name = _qualified(annotation)
            if name in checks:
                on = checks[name]
                if on in (annotation.get("/AP") or {}).get("/N", {}):
                    annotation[NameObject("/AS")] = NameObject(on)
                    target = annotation if "/T" in annotation else annotation["/Parent"].get_object()
                    target[NameObject("/V")] = NameObject(on)
        writer.update_page_form_field_values(page, text, auto_regenerate=False)
    writer.set_need_appearances_writer(True)
    _stamp(writer)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
