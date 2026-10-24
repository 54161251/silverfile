"""P7 form output: HTML draft with hover and click provenance (spec §4.2, D7, R9, R17)."""
import json
from pathlib import Path

import pytest

from src.agents.computation import compute_return
from src.dashboard.form_render import (hover_summary, mask_ssn, money, policy_excerpt,
                                       render_form, render_page)
from src.dashboard.previews import golden_previews

GOLDEN = Path(__file__).parent / "golden"


@pytest.fixture(scope="module")
def g02():
    state = json.loads((GOLDEN / "g02_mfj_two_seniors_ss_cap.json").read_text(encoding="utf-8"))["state"]
    state["intake"]["taxpayer"].update(name="Margaret Ellison", ssn="901-22-3333")
    state["intake"]["spouse"].update(name="Walter Ellison", ssn="902-33-4444")
    state["intake"]["dependents"] = [{"name": "Rosa Ellison", "ssn": "903-44-5555", "relationship": "grandchild"}]
    return state, compute_return(state)["lines"]


def test_A1_every_spec_line_has_a_row_with_hover_and_click_provenance(g02):
    state, lines = g02
    page = render_form(lines, state["intake"], {"filing_status": "mfj"})
    for line in lines:
        assert f'id="line-{line}"' in page
    assert page.count("<details>") == len(lines)          # click: one provenance panel per value
    assert page.count('role="tooltip"') == len(lines)     # hover: one summary per value
    assert "100,500" in page and "36,300" in page and "213" in page


def test_R9_rendered_values_are_exactly_the_stored_values(g02):
    _, lines = g02
    page = render_form(lines)
    for line, record in lines.items():
        row = page.split(f'id="line-{line}"', 1)[1].split('<div class="sf-row"', 1)[0]
        assert money(record, line) in row


def test_provenance_panel_links_inputs_sources_tool_and_policy(g02):
    _, lines = g02
    row = render_form(lines).split('id="line-9"', 1)[1].split('<div class="sf-row"', 1)[0]
    assert 'href="#line-1z"' in row and 'href="#line-6b"' in row  # inputs jump to their lines
    assert "sum_amounts" in row
    row_1a = render_form(lines).split('id="line-1a"', 1)[1].split('<div class="sf-row"', 1)[0]
    assert "w2_1" in row_1a and "box 1" in row_1a
    row_13b = render_form(lines).split('id="line-13b"', 1)[1].split('<div class="sf-row"', 1)[0]
    assert "policy.md#senior-deduction" in row_13b and "<blockquote>" in row_13b


def test_policy_excerpt_reads_the_cited_section():
    assert "born before 2 January 1961" in policy_excerpt("policy.md#age-65-test")
    assert policy_excerpt("policy.md#no-such-anchor") == ""
    assert policy_excerpt(None) == ""


def test_R17_ssns_are_masked_in_html(g02):
    state, lines = g02
    page = render_form(lines, state["intake"])
    assert "901-22-3333" not in page and "3333" in page
    assert mask_ssn("903-44-5555") == "XXX-XX-5555"


def test_html_escapes_untrusted_text():
    record = {"line": "8", "value": 5, "kind": "user_input", "entered_by": "<script>x</script>",
              "timestamp": "2026-10-24T12:00:00-04:00", "sources": [], "inputs": []}
    page = render_form({"8": record}, {"taxpayer": {"name": "<img src=x onerror=alert(1)>"}})
    assert "<script>" not in page and "<img" not in page


def test_missing_lines_say_not_computed_and_negative_loss_uses_parentheses():
    page = render_form({})
    assert page.count("not computed") >= 30
    assert money({"value": -1250}, "8") == "(1,250)"
    assert money({"value": 3}, "12d") == "3 boxes"


def test_standalone_page_is_a_full_document(g02):
    _, lines = g02
    page = render_page(lines, meta={"title": "Draft for thread x"})
    assert page.startswith("<!doctype html>") and "<title>Draft for thread x</title>" in page


def test_hover_summary_names_kind_tool_and_documents(g02):
    _, lines = g02
    assert "sum_amounts" in hover_summary(lines["1a"]) and "w2_1" in hover_summary(lines["1a"])


def test_golden_previews_compute_through_p2_agent():
    previews = {p["name"]: p for p in golden_previews()}
    assert previews["g02_mfj_two_seniors_ss_cap"]["lines"]["34"]["value"] == 213
    assert previews["g07_blocked_low_confidence_box"]["open_questions"]
