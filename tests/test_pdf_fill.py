"""P7 stretch output: the official 2025 Form 1040-SR PDF filled from the draft lines (D7, R9, R17)."""
import io
import json
import re
from pathlib import Path

import pytest
from pypdf import PdfReader

from src.agents.computation import compute_return
from src.dashboard.form_render import SECTIONS
from src.dashboard.pdf_fill import BLANK_FORM, fill_pdf, resolve_names

GOLDEN = Path(__file__).parent / "golden"


@pytest.fixture(scope="module")
def g02():
    state = json.loads((GOLDEN / "g02_mfj_two_seniors_ss_cap.json").read_text(encoding="utf-8"))["state"]
    state["intake"]["taxpayer"].update(name="Margaret Ellison", ssn="901-22-3333")
    state["intake"]["spouse"].update(name="Walter Ellison", ssn="902-33-4444")
    state["intake"]["dependents"] = [{"name": "Rosa Ellison", "ssn": "903-44-5555", "relationship": "grandchild"}]
    return state, compute_return(state)["lines"]


def test_D7_filled_pdf_carries_values_boxes_and_masked_ssn(g02):
    state, lines = g02
    reader = PdfReader(io.BytesIO(fill_pdf(lines, state["intake"], "mfj")))
    fields = {name.rsplit(".", 1)[-1]: field.get("/V") for name, field in reader.get_fields().items()}
    assert fields["f2_18[0]"] == "100,500" and fields["f2_19[0]"] == "100,500"  # 11a and its 11b copy
    assert fields["f1_47[0]"] == "40,000" and fields["f3_14[0]"] == "213"
    assert fields["f1_16[0]"] == "XXXXX3333"
    assert fields["c2_17[0]"] == "/1" and fields["c2_20[0]"] == "/1" and fields["c2_18[0]"] == "/Off"
    assert "/XFA" not in reader.trailer["/Root"]["/AcroForm"]
    assert "SILVERFILE DRAFT" in reader.pages[0].extract_text()


@pytest.mark.parametrize("status,state", [("single", "/1"), ("mfj", "/2"), ("mfs", "/3"), ("hoh", "/4"), ("qss", "/5")])
def test_A21_each_filing_status_checks_exactly_one_box(status, state):
    reader = PdfReader(io.BytesIO(fill_pdf({}, {}, status)))
    checked = [field.get("/V") for name, field in reader.get_fields().items()
               if re.search(r"c1_8\[\d\]$", name) and field.get("/V") not in (None, "/Off")]
    assert checked == [state]


def test_pdf_field_map_matches_the_blank_form():
    from src.dashboard import pdf_fill
    names = resolve_names(PdfReader(str(BLANK_FORM)))
    wanted = list(pdf_fill.LINE_FIELDS.values()) + list(pdf_fill.COPY_FIELDS) + list(pdf_fill.HEADER_FIELDS.values())
    wanted += [field for row in pdf_fill.DEPENDENT_FIELDS for field in row] + list(pdf_fill.BOX_12D.values())
    assert all(name in names for name in wanted)
    assert {line for _, rows in SECTIONS for line, _ in rows} >= set(pdf_fill.LINE_FIELDS)
