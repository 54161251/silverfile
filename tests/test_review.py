"""P6 Review agent: clean golden returns pass; each kind of planted error is caught and routed."""
import copy
import json
import unittest
from pathlib import Path

from src.agents.computation import compute_return
from src.agents.review import review_return
from src.orchestration import orchestrate
from src.state import validate_update

GOLDEN = sorted(p for p in (Path(__file__).parent / "golden").glob("g0*.json") if "blocked" not in p.name)
NOW = "2026-10-24T12:00:00-04:00"
_CACHE = {}


def computed(path: Path) -> dict:
    """A golden state with its lines filled in by the real Computation agent."""
    if path not in _CACHE:
        state = json.loads(path.read_text(encoding="utf-8"))["state"]
        for document in state.get("documents", []):
            if document["form"] == "1099-R":  # goldens predate the Rules box-7 convention
                document["boxes"].setdefault("7", "7")
        state.setdefault("escalations", [])
        result = compute_return(state, now=NOW)
        assert not result["open_questions"], result["open_questions"]
        state["lines"] = result["lines"]
        _CACHE[path] = state
    return copy.deepcopy(_CACHE[path])


def checks(result: dict) -> set:
    return {(f["check"], f["target_agent"]) for f in result["review_findings"]}


class CleanReturns(unittest.TestCase):
    def test_every_golden_return_passes(self):
        for path in GOLDEN:
            with self.subTest(golden=path.name):
                result = review_return(computed(path))
                self.assertEqual(result, {"review_verdict": "pass", "review_findings": []})

    def test_E3_staff_entered_box_value_passes_review(self):
        state = json.loads(GOLDEN[0].read_text(encoding="utf-8"))["state"]
        state.setdefault("escalations", [])
        w2 = next(d for d in state["documents"] if d["form"] == "W-2")
        state["user_inputs"][f"{w2['doc_id']}.1"] = {"value": 12345, "kind": "human_resolution",
                                                     "entered_by": "staff_jlee", "timestamp": NOW}
        state["lines"] = compute_return(state, now=NOW)["lines"]
        self.assertEqual(state["lines"]["1a"]["value"], 12345)
        self.assertEqual(review_return(state), {"review_verdict": "pass", "review_findings": []})

    def test_output_stays_inside_the_review_contract(self):
        update = validate_update("review", review_return(computed(GOLDEN[0])))
        self.assertEqual(set(update), {"review_verdict", "review_findings"})


class PlantedErrors(unittest.TestCase):
    def setUp(self):
        self.state = computed(GOLDEN[0])  # g01: single, W-2, 1099-INT, SSA-1099

    def review(self):
        return review_return(self.state)

    def test_empty_draft(self):
        self.state["lines"] = {}
        self.assertIn(("P1", "computation"), checks(self.review()))

    def test_missing_line(self):
        del self.state["lines"]["9"]
        self.assertIn(("P1", "computation"), checks(self.review()))

    def test_computed_line_without_formula(self):
        self.state["lines"]["15"]["formula"] = None
        self.assertIn(("P3", "computation"), checks(self.review()))

    def test_wrong_tax_is_recomputed_and_caught(self):
        self.state["lines"]["16"]["value"] += 100
        result = self.review()
        self.assertEqual(result["review_verdict"], "revise")
        self.assertIn(("T1", "computation"), checks(result))
        self.assertTrue(any(f.get("line") == "16" and f["check"] == "T1" for f in result["review_findings"]))

    def test_stale_line_after_document_changed(self):
        self.state["documents"][0]["boxes"]["1"] = 25000  # W-2 wages changed after computation
        found = checks(self.review())
        self.assertIn(("P4", "computation"), found)
        self.assertIn(("T2", "computation"), found)

    def test_line_not_from_its_tool(self):
        self.state["lines"]["16"]["tool"] = {"name": "sum_amounts", "version": "1.0", "tax_year": 2025}
        self.assertIn(("P5", "computation"), checks(self.review()))

    def test_taxable_social_security_above_benefits(self):
        self.state["lines"]["6b"]["value"] = self.state["lines"]["6a"]["value"] + 1
        self.assertIn(("R7", "computation"), checks(self.review()))

    def test_refund_and_amount_owed_together(self):
        self.state["lines"]["37"]["value"] = 5
        self.assertIn(("R9", "computation"), checks(self.review()))

    def test_out_of_scope_line_has_a_value(self):
        self.state["lines"]["13a"]["value"] = 500
        self.assertIn(("R8", "rules"), checks(self.review()))

    def test_box_count_disagrees(self):
        self.state["box_count_12d"] = 2
        self.assertIn(("R5", "rules"), checks(self.review()))

    def test_taxpayer_too_young_for_1040sr(self):
        self.state["intake"]["taxpayer"]["birth_date"] = "1965-03-01"
        found = checks(self.review())
        self.assertIn(("R2", "rules"), found)
        self.assertIn(("R3", "rules"), found)

    def test_standard_deduction_chart_does_not_apply(self):
        self.state["intake"]["can_be_claimed_as_dependent"] = True
        self.assertIn(("R6", "rules"), checks(self.review()))

    def test_unescalated_not_determined_1099r(self):
        self.state["documents"].append({"doc_id": "r_1", "form": "1099-R", "flags": [],
                                        "boxes": {"1": 0, "2a": 0, "7": "7", "2b_not_determined": True}})
        self.assertIn(("S4", "rules"), checks(self.review()))
        self.state["escalations"] = [{"id": "esc_0001", "code": "E3", "status": "resolved", "evidence": ["doc:r_1"]}]
        self.assertNotIn(("S4", "rules"), checks(self.review()))

    def test_advice_request_must_have_been_escalated(self):
        self.state["flags"] = [{"id": "f1", "type": "advice_request", "turn_id": 3}]
        self.assertIn(("S8", "rules"), checks(self.review()))
        self.state["escalations"] = [{"id": "esc_0001", "code": "E4", "status": "resolved", "evidence": ["f1"]}]
        self.assertNotIn(("S8", "rules"), checks(self.review()))

    def test_scope_not_cleared(self):
        self.state["scope"]["in_scope"] = False
        self.assertIn(("S1", "rules"), checks(self.review()))

    def test_upstream_fix_comes_first(self):
        self.state["lines"]["16"]["value"] += 1          # computation problem
        self.state["documents"][0]["confidence"] = {"1": 0.4}  # extraction problem
        self.assertEqual(self.review()["review_findings"][0]["target_agent"], "extraction")


class Routing(unittest.TestCase):
    def test_orchestrator_sends_a_revision_to_the_named_agent(self):
        state = computed(GOLDEN[0])
        state["lines"]["16"]["value"] += 100
        state.update(review_return(state), last_agent="review", iterations=0, mode="production")
        self.assertEqual(orchestrate(state)["next_agent"], "computation")

    def test_orchestrator_finishes_a_passing_review(self):
        state = computed(GOLDEN[0])
        state.update(review_return(state), last_agent="review", mode="production")
        self.assertEqual(orchestrate(state)["status"], "draft_ready")


if __name__ == "__main__":
    unittest.main()
