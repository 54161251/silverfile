"""P4: W-2 extraction. Part A needs no OCR engine; part B reads the real fixture images (skipped without Tesseract)."""
import json
import logging
import re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from src.agents import computation, extraction
from src.extraction import contract, ocr
from src.extraction.schema import (CONFIDENCE_THRESHOLD, ExtractedField, FieldProvenance, SsnReading, W2Record,
                                   Word)
from src.security.pii import contains_raw_ssn
from src.state import ExtractedDocument, merge_documents, validate_update

REPO = Path(__file__).resolve().parents[1]
FIX = REPO / "data" / "fixtures"
NOW = datetime(2026, 10, 26, 14, 0, tzinfo=timezone.utc)
needs_ocr = pytest.mark.skipif(not ocr.TesseractBackend.available(),
                               reason="Tesseract OCR is not installed (apt-get/brew install tesseract)")


# ------------------------------------------------------------------------------------------------------
# Part A: no OCR engine needed
# ------------------------------------------------------------------------------------------------------
def word(text, left, top, width=120, height=20, conf=95.0):
    return Word(text=text, left=left, top=top, width=width, height=height, conf=conf)


def label_words(phrase, left, top):
    """Words of a printed label laid out left to right on one line."""
    out, x = [], left
    for part in phrase.split():
        out.append(word(part, x, top, width=12 * len(part)))
        x += 12 * len(part) + 10
    return out


def page_words():
    """A hand-built page: label for box 1 and box 2 side by side, each with its amount underneath."""
    return (label_words("Wages, tips, other compensation", 900, 240) + [word("31,250.00", 896, 280, 200, 36)]
            + label_words("Federal income tax withheld", 1440, 240) + [word("3,400.00", 1436, 280, 190, 36)]
            + label_words("Social security wages", 900, 380) + [word("31,250.00", 896, 420, 200, 36)])


def test_parse_amount_accepts_only_plain_dollar_amounts():
    assert ocr.parse_amount("31,250.00") == Decimal("31250.00")
    assert ocr.parse_amount("$1,937.50") == Decimal("1937.50")
    assert ocr.parse_amount("0.00") == Decimal("0.00")
    assert ocr.parse_amount("453.13.") == Decimal("453.13")           # trailing OCR punctuation
    for bad in [None, "", "abc", "31,25.00", "31.250,00", "-5.00", "1,2", "1" * 20, "12 34", "5Z000.00"]:
        assert ocr.parse_amount(bad) is None


def test_labels_are_found_and_each_value_attaches_to_its_own_label():
    located = ocr.locate(page_words(), (2000, 1500))
    assert {"1", "2", "3"} <= set(located)
    assert [w.text for w in located["1"].parts] == ["31,250.00"]
    assert [w.text for w in located["2"].parts] == ["3,400.00"]
    assert located["3"].parts[0].top == 420                           # not box 1's amount above it


def test_label_matching_tolerates_small_ocr_slips_and_abbreviations():
    words = (label_words("Wages, tlps, other comp.", 900, 240) + [word("1.00", 896, 280)])
    assert "1" in ocr.find_labels(words)


def test_a_missing_amount_is_not_borrowed_from_the_box_below():
    words = label_words("Wages, tips, other compensation", 900, 240) + label_words(
        "Social security wages", 900, 380) + [word("31,250.00", 896, 420, 200, 36)]
    located = ocr.locate(words, (2000, 1500))
    assert located["1"].parts == []                                    # blank box 1 stays blank
    assert [w.text for w in located["3"].parts] == ["31,250.00"]


def loc(text="31,250.00", conf=95.0):
    label = ocr._Label("1", 1.0, 900, 240, 1200, 260, 20)
    return ocr.Located(label, [word(text, 896, 280, 200, 36, conf)] if text else [], (880, 270, 1300, 330))


def test_decide_reads_a_value_only_when_readings_agree_and_are_confident():
    result = ocr._decide_money("1", [loc(), loc()], ["31,250.00"] * 3)
    assert (result.status, result.value) == ("read", Decimal("31250.00")) and result.confidence >= CONFIDENCE_THRESHOLD


def test_decide_flags_disagreement_and_shows_no_number():
    result = ocr._decide_money("1", [loc()], ["31,250.00", "31,260.00", "31,950.00"])
    assert result.status == "uncertain" and result.value is None


def test_decide_tolerates_one_stray_reading():
    result = ocr._decide_money("1", [loc(), loc()], ["31,250.00", "31,250.00", "81,250.00"])
    assert result.status == "read" and result.value == Decimal("31250.00")


def test_decide_flags_low_confidence_but_keeps_the_consistent_value():
    result = ocr._decide_money("1", [loc(conf=60.0)], ["31,250.00"] * 3)
    assert result.status == "uncertain" and result.value == Decimal("31250.00") and result.confidence < 0.8


def test_decide_refuses_an_amount_with_no_cents():
    """A smudge can leave "87" of "87,654.32". Printed W-2 amounts have cents, so this is never accepted."""
    for partial in ("87", "87,654", "87,654."):
        result = ocr._decide_money("1", [loc(partial)], [partial] * 3)
        assert result.status == "uncertain" and result.value is None


def test_decide_blank_or_garbage_is_unreadable():
    result = ocr._decide_money("2", [loc(None)], ["", "", ""])
    assert result.status == "unreadable" and result.value is None
    assert ocr._decide_money("2", [loc("x#")], ["abc", "", "--"]).status == "unreadable"


def ssn_loc(text, conf=92.0):
    return ocr.Located(ocr._Label("a", 1.0, 100, 240, 500, 260, 20), [word(text, 96, 280, 260, 36, conf)],
                       (80, 270, 500, 330))


def test_ssn_box_returns_only_a_verdict_and_a_masked_number():
    ok = ocr._decide_ssn([ssn_loc("901-23-4567")], ["901-23-4567"] * 3)
    assert (ok.ssn_status, ok.ssn_masked, ok.value, ok.raw_text) == ("accepted", "***-**-4567", None, None)
    real = ocr._decide_ssn([ssn_loc("123-45-6789")], ["123-45-6789"] * 3)
    assert (real.ssn_status, real.ssn_masked) == ("not_test_range", "***-**-****")     # not even the last four
    for result in (ok, real):
        assert not contains_raw_ssn(repr(result)) and "6789" not in repr(real)


def test_ssn_box_disagreement_is_uncertain():
    result = ocr._decide_ssn([ssn_loc("901-23-4567")], ["901-23-4567", "901-23-4568", "902-23-4567"])
    assert result.status == "uncertain" and result.ssn_masked == "***-**-****"


def make_record(**overrides):
    """A W2Record built by hand: box 1 read, box 2 uncertain, SSN accepted."""
    def prov(box):
        return FieldProvenance(source_document="w2_9", source_file="x.png", source_sha256="ab" * 32, page=1, box=box,
                               box_label="label", entered_by="w2-extraction-agent/1.0 (test)", method="ocr",
                               timestamp=NOW, location=(1, 2, 3, 4), raw_text="31,250.00")
    fields = {"1": ExtractedField(box="1", value=Decimal("31250.00"), confidence=0.95, status="read", provenance=prov("1")),
              "2": ExtractedField(box="2", value=None, confidence=0.5, status="uncertain",
                                  reason="the readings of this box gave different answers", provenance=prov("2"))}
    data = dict(doc_id="w2_9", source_file="x.png", method="ocr", fields=fields,
                ssn=SsnReading(status="accepted", masked="***-**-4567", confidence=0.91, provenance=prov("a")),
                extracted_at=NOW, entered_by="w2-extraction-agent/1.0 (test)")
    return W2Record(**(data | overrides))


def test_contract_document_matches_p1_format_and_marks_uncertain_boxes():
    doc = contract.to_extracted_document(make_record(), sha256="ab" * 32)
    ExtractedDocument.model_validate(doc)                              # P1's own model accepts it
    assert doc["boxes"] == {"1": 31250, "2": None, "a": "***-**-4567"}
    assert doc["unverified"] == ["2"]
    assert doc["confidence"]["2"] < CONFIDENCE_THRESHOLD <= doc["confidence"]["1"]
    assert any(f.startswith("extracted_by=w2-extraction-agent/1.0") and "extracted_at=2026-10-26T14:00:00" in f
               for f in doc["flags"])
    assert any(f.startswith("uncertain:2:") for f in doc["flags"])
    assert validate_update("extraction", {"documents": [doc]})["documents"][0]["doc_id"] == "w2_9"


def test_every_unverified_box_has_confidence_below_the_threshold():
    """P6's Review agent (check P7) fails a box under 0.8 that is not unverified, and we keep the reverse true too."""
    record = make_record()
    record.fields["2"] = record.fields["2"].model_copy(update={"confidence": 0.79 + 0.2})   # would be inconsistent
    doc = contract.to_extracted_document(record)
    assert all(doc["confidence"][b] < CONFIDENCE_THRESHOLD for b in doc["unverified"])


def test_amounts_with_cents_stay_exact():
    assert contract.amount_for_contract(Decimal("1937.50")) == 1937.5
    assert contract.amount_for_contract(Decimal("453.13")) == 453.13
    assert contract.amount_for_contract(Decimal("31250.00")) == 31250 and isinstance(contract.amount_for_contract(Decimal("5.00")), int)


def test_merge_is_order_independent_and_idempotent_for_our_documents():
    a = contract.to_extracted_document(make_record())
    b = contract.to_extracted_document(make_record(doc_id="w2_10"))
    assert merge_documents(merge_documents([], [a]), [b]) == merge_documents(merge_documents([], [b]), [a])
    assert merge_documents([a], [a]) == [a]


def test_uncertain_box_makes_computation_ask_the_taxpayer_instead_of_guessing():
    doc = contract.to_extracted_document(make_record())
    state = {"documents": [doc], "user_inputs": {}, "scope": {"in_scope": True}, "filing_status_validated": "single",
             "intake": {"filing_status": "single", "taxpayer": {"blind": False}}, "box_count_12d": 1,
             "eligibility": {"taxpayer_65_or_older": True, "spouse_65_or_older": False, "form_1040sr_eligible": True,
                             "senior_deduction_qualifiers": ["taxpayer"], "missing": []}}
    blocked = computation.run(state)
    assert blocked["lines"] == {} and any("documents.w9" not in q and "w2_9.boxes.2" in q for q in blocked["open_questions"])
    state["user_inputs"] = {"w2_9.2": 3400}                          # the taxpayer confirms box 2
    assert computation.run(state)["open_questions"] == []


def test_structured_upload_is_copied_and_labelled_not_ocr(tmp_path):
    upload = {"doc_id": "d1", "form": "1099-INT", "boxes": {"1": 1200, "note": "ssn 901-23-4567"}, "source_file": "x/y.json"}
    doc = extraction.extract_upload(upload, now=NOW)
    assert doc["boxes"]["1"] == 1200 and "structured_input_not_ocr" in doc["flags"]
    assert doc["confidence"] == {} and doc["unverified"] == [] and doc["source_file"] == "y.json"
    assert not contains_raw_ssn(doc)


def test_missing_wrong_type_and_corrupt_files_are_flagged_never_raised(tmp_path):
    cases = [{"doc_id": "a", "form": "W-2", "source_file": "no/such/file.jpg"},
             {"doc_id": "b", "form": "W-2", "source_file": str(tmp_path / "notes.txt")},
             {"doc_id": "c", "form": "W-2"}]
    (tmp_path / "notes.txt").write_text("hello")
    corrupt = tmp_path / "broken.jpg"
    corrupt.write_bytes(b"not really a jpeg")
    cases.append({"doc_id": "d", "form": "W-2", "source_file": str(corrupt)})
    for upload in cases:
        doc = extraction.extract_upload(upload, now=NOW)
        assert doc["boxes"] == {} and any(f.startswith("unreadable_document:") for f in doc["flags"]), upload
        ExtractedDocument.model_validate(doc)


def test_only_w2_images_are_read(tmp_path):
    doc = extraction.extract_upload({"doc_id": "x", "form": "1099-R", "source_file": str(FIX / "w2_clean_1.png")}, now=NOW)
    assert doc["boxes"] == {} and "unreadable_document:only_w2_images_are_supported" in doc["flags"]


def test_upload_needs_a_doc_id():
    with pytest.raises(ValueError):
        extraction.extract_upload({"form": "W-2"})


def test_oversized_and_unsupported_files_are_rejected_safely(tmp_path):
    big = tmp_path / "big.png"
    big.write_bytes(b"0" * (ocr.MAX_FILE_BYTES + 1))
    with pytest.raises(ocr.UnreadableDocument, match="15 MB"):
        ocr.load_pages(big)
    with pytest.raises(ocr.UnreadableDocument, match="unsupported"):
        ocr.load_pages(tmp_path / "a.exe") if (tmp_path / "a.exe").write_bytes(b"MZ") else None


def test_provenance_file_is_written_with_no_raw_ssn_and_survives_unwritable_folder(tmp_path, monkeypatch):
    record = make_record()
    monkeypatch.setenv("SILVERFILE_EXTRACTION_DIR", str(tmp_path))
    assert extraction._write_provenance(record, "session one/../x")      # session id is sanitised into a folder name
    files = list(tmp_path.rglob("*.provenance.json"))
    assert len(files) == 1 and tmp_path in files[0].parents
    saved = json.loads(files[0].read_text())
    assert saved["fields"]["1"]["provenance"]["box"] == "1" and not contains_raw_ssn(files[0].read_text())
    monkeypatch.setenv("SILVERFILE_EXTRACTION_DIR", str(files[0]))       # a FILE where a folder is needed
    assert extraction._write_provenance(record, "s") is False


# ------------------------------------------------------------------------------------------------------
# Part B: real images through Tesseract
# ------------------------------------------------------------------------------------------------------
def truth(name):
    return json.loads((FIX / f"{name}.truth.json").read_text())


def read(name, suffix="jpg", tmp_path=None, monkeypatch=None):
    if monkeypatch is not None:
        monkeypatch.setenv("SILVERFILE_EXTRACTION_DIR", str(tmp_path))
    path = FIX / f"{name}.{suffix}"
    return extraction.run({"session_id": "t", "uploads": [{"doc_id": "w2_1", "form": "W-2", "source_file": str(path)}]})["documents"][0]


def as_number(text):
    return None if text is None else (int(Decimal(text)) if Decimal(text) == int(Decimal(text)) else float(Decimal(text)))


@needs_ocr
@pytest.mark.parametrize("name,suffix", [("w2_clean_1", "jpg"), ("w2_clean_1", "png"), ("w2_clean_1", "pdf"),
                                         ("w2_scan_2", "jpg"), ("w2_scan_2", "pdf"), ("w2_cents_3", "jpg")])
def test_evaluation_and_cents_documents_are_read_exactly(name, suffix, tmp_path, monkeypatch):
    doc = read(name, suffix, tmp_path, monkeypatch)
    expected = truth(name)["boxes"]
    assert doc["unverified"] == [], doc["flags"]
    for box, text in expected.items():
        assert doc["boxes"][box] == as_number(text), (name, suffix, box)
    assert doc["boxes"]["a"] == "***-**-" + truth(name)["ssn"][-4:]
    assert min(doc["confidence"].values()) >= CONFIDENCE_THRESHOLD


@needs_ocr
def test_smudged_box_is_flagged_not_guessed(tmp_path, monkeypatch):
    doc = read("w2_smudged_box1", tmp_path=tmp_path, monkeypatch=monkeypatch)
    assert "1" in doc["unverified"] and doc["boxes"]["1"] is None
    assert doc["boxes"]["2"] == 9100                                    # the readable boxes are still read
    assert any(f.startswith("uncertain:1:") for f in doc["flags"])


@needs_ocr
def test_blank_box_is_flagged_and_not_turned_into_zero(tmp_path, monkeypatch):
    doc = read("w2_blank_box2", tmp_path=tmp_path, monkeypatch=monkeypatch)
    assert doc["boxes"]["2"] is None and "2" in doc["unverified"]
    assert doc["boxes"]["1"] == 31250 and "1" not in doc["unverified"]


@needs_ocr
def test_non_test_ssn_is_refused_and_nothing_from_that_document_is_used(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    doc = read("w2_real_looking_ssn", tmp_path=tmp_path, monkeypatch=monkeypatch)
    assert "ssn_not_test_range" in doc["flags"]
    assert doc["boxes"]["a"] == "***-**-****"                           # not even the last four digits
    assert all(doc["boxes"][b] is None for b in "123456") and set(doc["unverified"]) == set("123456")
    for text in (json.dumps(doc), caplog.text, *(p.read_text() for p in tmp_path.rglob("*.json"))):
        assert "123-45-6789" not in text and not contains_raw_ssn(text)
        assert not re.search(r"(?<![0-9])123456789(?![0-9])", text) and "***-**-6789" not in text   # not even the last four


@needs_ocr
def test_raw_ssn_never_appears_in_logs_output_or_provenance(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    doc = read("w2_clean_1", tmp_path=tmp_path, monkeypatch=monkeypatch)
    raw = truth("w2_clean_1")["ssn"]
    assert raw not in json.dumps(doc) and raw.replace("-", "") not in json.dumps(doc)
    assert caplog.records and raw not in caplog.text and not contains_raw_ssn(caplog.text)
    sidecar = next(tmp_path.rglob("*.provenance.json")).read_text()
    assert raw not in sidecar and not contains_raw_ssn(sidecar)


@needs_ocr
def test_provenance_for_every_value(tmp_path, monkeypatch):
    doc = read("w2_clean_1", tmp_path=tmp_path, monkeypatch=monkeypatch)
    sha = __import__("hashlib").sha256((FIX / "w2_clean_1.jpg").read_bytes()).hexdigest()
    saved = json.loads(next(tmp_path.rglob("w2_1.provenance.json")).read_text())
    assert set(saved["fields"]) == set("123456")
    for box, field in saved["fields"].items():
        p = field["provenance"]
        assert p["source_document"] == "w2_1" and p["source_file"] == "w2_clean_1.jpg" and p["box"] == box
        assert p["source_sha256"] == sha and p["method"] == "ocr" and p["page"] == 1
        assert p["entered_by"].startswith("w2-extraction-agent/") and "tesseract" in p["entered_by"]
        assert datetime.fromisoformat(p["timestamp"]).tzinfo is not None
        l, t, r, b = p["location"]
        assert 0 <= l < r <= 2000 and 0 <= t < b <= 1500
        assert p["raw_text"] and p["box_label"]
    assert saved["ssn"]["provenance"]["raw_text"] is None
    assert any(f.startswith("extracted_by=w2-extraction-agent") and sha[:16] in f for f in doc["flags"])


@needs_ocr
def test_no_confident_wrong_amounts_across_fixtures(tmp_path, monkeypatch):
    """The safety property: whatever the picture, a box marked as read must equal what is printed."""
    names = ["w2_cents_3", "w2_smudged_box1", "w2_blank_box2", "w2_batch_01", "w2_batch_03", "w2_batch_06", "w2_batch_08"]
    for name in names:
        folder = FIX / "batch" if name.startswith("w2_batch") else FIX
        monkeypatch.setenv("SILVERFILE_EXTRACTION_DIR", str(tmp_path))
        doc = extraction.run({"uploads": [{"doc_id": "w2_1", "form": "W-2", "source_file": str(folder / f"{name}.jpg")}]})["documents"][0]
        expected = json.loads((folder / f"{name}.truth.json").read_text())["boxes"]
        for box in "123456":
            if box not in doc["unverified"]:
                assert doc["boxes"][box] == as_number(expected[box]), (name, box)


@needs_ocr
def test_graph_style_call_returns_exactly_one_assigned_document(tmp_path, monkeypatch):
    monkeypatch.setenv("SILVERFILE_EXTRACTION_DIR", str(tmp_path))
    state = {"session_id": "g", "uploads": [{"doc_id": "w2_7", "form": "W-2", "source_file": "data/fixtures/w2_clean_1.jpg"}]}
    update = extraction.run(state)
    assert set(update) == {"documents"} and [d["doc_id"] for d in update["documents"]] == ["w2_7"]
    assert extraction.run({"uploads": []}) == {"documents": []}


def test_a_missing_ocr_engine_fails_loudly_not_silently(monkeypatch):
    from src.extraction import extractor
    monkeypatch.setattr(extractor, "_backend", None)
    monkeypatch.setattr(ocr.TesseractBackend, "available", staticmethod(lambda: False))
    with pytest.raises(extractor.OcrUnavailable, match="Tesseract"):
        extractor.default_backend()
