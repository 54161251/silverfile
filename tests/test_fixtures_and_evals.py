"""P4: fixture generator and the two evaluation cases (assignment 5.2)."""
import json
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.extraction import ocr
from src.security.ssn import is_test_ssn
from src.state import ResumePayload

REPO = Path(__file__).resolve().parents[1]
FIX = REPO / "data" / "fixtures"
CASES = json.loads((REPO / "evals" / "eval_cases.json").read_text(encoding="utf-8"))["cases"]
needs_ocr = pytest.mark.skipif(not ocr.TesseractBackend.available(), reason="Tesseract OCR is not installed")


def run_generator(*args, cwd=REPO):
    return subprocess.run([sys.executable, str(REPO / "data" / "generate_fixtures.py"), *args],
                          capture_output=True, text=True, cwd=cwd)


# --- fixtures ---------------------------------------------------------------------------------------
def test_committed_fixtures_exist_and_are_openable():
    from PIL import Image
    for name in ["w2_clean_1.jpg", "w2_clean_1.png", "w2_clean_1.pdf", "w2_scan_2.jpg", "w2_cents_3.jpg",
                 "w2_smudged_box1.jpg", "w2_blank_box2.jpg", "w2_real_looking_ssn.jpg", "batch/w2_batch_10.jpg"]:
        assert (FIX / name).stat().st_size > 10_000, name
    with Image.open(FIX / "w2_clean_1.png") as image:
        assert image.size == (2000, 1500)
    for demo in ("w2_image_1.jpg", "w2_image_2.jpg"):
        assert (REPO / "demo" / demo).read_bytes()[:3] == b"\xff\xd8\xff"           # a real JPEG


def test_every_fixture_ssn_is_a_test_number_except_the_one_made_to_be_rejected():
    for truth_file in FIX.rglob("*.truth.json"):
        truth = json.loads(truth_file.read_text())
        assert is_test_ssn(truth["ssn"]) == (truth["name"] != "w2_real_looking_ssn"), truth_file.name


def test_batch_has_ten_documents_and_a_manifest():
    manifest = json.loads((FIX / "batch" / "manifest.json").read_text())["uploads"]
    assert len(manifest) == 10 and len({m["doc_id"] for m in manifest}) == 10
    for entry in manifest:
        assert (REPO / entry["source_file"]).is_file() and entry["form"] == "W-2"


def test_generator_is_deterministic_and_matches_the_committed_ground_truth(tmp_path):
    first, second = tmp_path / "a", tmp_path / "b"
    assert run_generator("--out", str(first), "--no-demo", "--batch-only").returncode == 0
    assert run_generator("--out", str(second), "--no-demo", "--batch-only").returncode == 0
    for path in sorted((first / "batch").glob("*")):
        assert path.read_bytes() == (second / "batch" / path.name).read_bytes(), path.name
    for path in (first / "batch").glob("*.truth.json"):                           # amounts never drift
        assert path.read_text() == (FIX / "batch" / path.name).read_text()
    assert run_generator("--out", str(first), "--no-demo").returncode == 0
    for name in ("w2_clean_1", "w2_scan_2", "w2_cents_3"):
        assert (first / f"{name}.truth.json").read_text() == (FIX / f"{name}.truth.json").read_text()


def test_custom_w2_uses_your_numbers_and_refuses_a_real_looking_ssn(tmp_path):
    target = tmp_path / "mine.jpg"
    done = run_generator("--custom", str(target), "--wages", "41250.00", "--withheld", "3300", "--ssn", "900-11-2222")
    assert done.returncode == 0 and target.is_file()
    assert json.loads((tmp_path / "mine.truth.json").read_text())["boxes"]["1"] == "41250.00"
    refused = run_generator("--custom", str(tmp_path / "bad.jpg"), "--ssn", "123-45-6789")
    assert refused.returncode != 0 and not (tmp_path / "bad.jpg").exists() and "123-45-6789" not in refused.stdout
    assert "900-series" in refused.stderr


@needs_ocr
def test_custom_w2_can_be_read_back_exactly(tmp_path):
    from src.agents import extraction
    target = tmp_path / "mine.png"
    assert run_generator("--custom", str(target), "--wages", "41250.00", "--withheld", "3300.50",
                         "--ssn", "900-11-2222", "--ss-wages", "41250.00", "--ss-tax", "2557.50",
                         "--medicare-wages", "41250.00", "--medicare-tax", "598.13").returncode == 0
    doc = extraction.extract_upload({"doc_id": "w2_1", "form": "W-2", "source_file": str(target)})
    # The reader may decline a box it is unsure of, but it must never return a wrong number.
    truth = {"1": 41250, "2": 3300.5, "3": 41250, "4": 2557.5, "5": 41250, "6": 598.13}
    for box, value in truth.items():
        assert doc["boxes"][box] == value or (doc["boxes"][box] is None and box in doc["unverified"]), box
    assert doc["boxes"]["1"] == 41250 and doc["boxes"]["2"] == 3300.5


# --- the evaluation cases ---------------------------------------------------------------------------
def test_there_are_exactly_two_cases_a_clean_one_and_a_resolved_hitl_one():
    assert [c["type"] for c in CASES] == ["clean", "hitl_resolved"]


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_case_files_exist_and_agree_with_each_other(case):
    for key in ("input_file", "w2_image", "w2_ground_truth", "write_up"):
        assert (REPO / case[key]).is_file(), (case["id"], key)
    inputs = json.loads((REPO / case["input_file"]).read_text())
    assert inputs["uploads"][0]["source_file"] == case["w2_image"]
    assert set(inputs) <= {"intake", "uploads", "user_inputs", "flags", "session_summary"}   # what Sessions.start accepts
    assert is_test_ssn(inputs["intake"]["taxpayer"]["ssn"])
    truth = json.loads((REPO / case["w2_ground_truth"]).read_text())["boxes"]
    for box, text in truth.items():
        expected = float(text)
        assert case["expected"]["w2_extraction"]["boxes"][box] == (int(expected) if expected.is_integer() else expected)


def test_case_2_has_a_prepared_resolution_that_the_graph_would_accept():
    case = CASES[1]
    payload = json.loads((REPO / case["resolution_file"]).read_text())
    resume = ResumePayload.model_validate(payload)
    assert resume.escalation_id == case["expected"]["before_resolution"]["pending_escalation"]
    assert resume.option in case["expected"]["before_resolution"]["escalation"]["options"]
    with pytest.raises(ValidationError):
        ResumePayload.model_validate(payload | {"note": "  "})                       # a blank note is refused
    how = case["how_to_resolve"]
    assert len(how["in_the_dashboard"]) >= 6 and any("run.py resume" in step for step in how["on_the_command_line"])
    assert all(step in (REPO / "demo" / "eval_case_2.md").read_text() for step in
               ["demo_staff", "Open & resolve", "Verified, continue", "Resolve and resume"])


def test_the_documented_commands_match_run_py():
    help_text = subprocess.run([sys.executable, str(REPO / "run.py"), "--help"], capture_output=True, text=True,
                               cwd=REPO).stdout
    if "usage" not in help_text:
        pytest.skip("run.py needs langgraph, which is not installed here")
    for case in CASES:
        for command in case["run"]["cli"]:
            assert command.split()[2] in help_text


@needs_ocr
def test_case_1_clean_run_end_to_end_without_langgraph(tmp_path, monkeypatch):
    from tests import pipeline_sim as sim
    monkeypatch.setenv("SILVERFILE_EXTRACTION_DIR", str(tmp_path))
    case = CASES[0]
    state = sim.run_until_stop(sim.start(sim.load_input(case["input_file"])))
    expected = case["expected"]
    doc = state["documents"][0]
    assert doc["unverified"] == [] and {k: doc["boxes"][k] for k in expected["w2_extraction"]["boxes"]} == expected["w2_extraction"]["boxes"]
    assert state["escalations"] == [] and state["status"] == expected["final_status"]
    assert state["review_verdict"] == "pass"
    assert {line: record["value"] for line, record in state["lines"].items() if record["value"]} == expected["lines"]
    assert "37" not in {k for k, v in state["lines"].items() if v["value"]}
    w2_lines = {k: v for k, v in state["lines"].items() if k in ("1a", "25a")}
    assert {k: v["sources"][0]["box"] for k, v in w2_lines.items()} == {"1a": "1", "25a": "2"}
    assert all(v["sources"][0]["doc_id"] == "w2_1" for v in w2_lines.values())
    _assert_form_is_created(state)


@needs_ocr
def test_case_2_hitl_is_raised_and_then_resolved(tmp_path, monkeypatch):
    from tests import pipeline_sim as sim
    monkeypatch.setenv("SILVERFILE_EXTRACTION_DIR", str(tmp_path))
    case = CASES[1]
    state = sim.run_until_stop(sim.start(sim.load_input(case["input_file"])))
    before = case["expected"]["before_resolution"]
    assert state["status"] == before["status"] and state["pending_escalation"] == before["pending_escalation"]
    [escalation] = state["escalations"]
    for key, value in before["escalation"].items():
        assert escalation[key] == value, key
    assert state.get("lines", {}) == {}                                        # nothing computed while stopped
    assert state["documents"][0]["unverified"] == []
    state = sim.resolve(state, json.loads((REPO / case["resolution_file"]).read_text()))
    after = case["expected"]["after_resolution"]
    assert state["status"] == after["final_status"] and state["review_verdict"] == after["review_verdict"]
    [resolved] = state["escalations"]
    assert resolved["status"] == "resolved" and resolved["resolution"]["resolved_by"] == "demo_staff"
    assert resolved["resolution"]["option"] == "verified_continue" and resolved["resolution"]["note"]
    assert {line: record["value"] for line, record in state["lines"].items() if record["value"]} == after["lines"]
    _assert_form_is_created(state)


def test_wrong_resolution_is_refused_so_the_instructions_cannot_be_applied_to_the_wrong_case():
    from src.human import apply_resolution
    state = {"pending_escalation": "esc_0001", "escalations": [{"id": "esc_0001", "status": "open", "code": "E6",
             "options": ["flag_for_review", "verified_continue", "close_session"]}]}
    good = json.loads((REPO / CASES[1]["resolution_file"]).read_text())
    with pytest.raises(ValueError):
        apply_resolution(state, good | {"escalation_id": "esc_0002"})
    with pytest.raises(ValueError):
        apply_resolution(state, good | {"option": "acknowledge"})
    assert apply_resolution(state, good)["escalations"][0]["status"] == "resolved"


def _assert_form_is_created(state):
    """The 'filled in 1040-SR' rubric item: the dashboard's own renderers accept the finished state."""
    from src.dashboard.form_render import render_page
    html = render_page(state["lines"], state["intake"], {})
    assert "1040" in html and f"{state['lines']['34']['value']:,}" in html and "901-23-4567" not in html \
        and "902-34-5678" not in html                                               # SSNs stay masked on the form
    try:
        from src.dashboard.pdf_fill import fill_pdf
    except ImportError:
        return                                                                       # pypdf not installed here
    assert fill_pdf(state["lines"], state["intake"], state["filing_status_validated"])[:5] == b"%PDF-"
