"""Computation agent tests: golden returns, contract validity, and blocking behaviour."""
import copy
import json
import unittest
from pathlib import Path

from src.agents import computation
from src.agents.computation import compute_return, run
from src.state import AGENT_FIELDS, validate_update

GOLDEN_DIR = Path(__file__).parent / "golden"
NOW = "2025-10-30T12:00:00-04:00"
ALL_LINES = ("1a 1z 2a 2b 3a 3b 4a 4b 5a 5b 6a 6b 7 8 9 10 11a 12d 12e 13a 13b 14 15 16 17 18 19 20 21 22 "
             "23 24 25a 25b 25c 25d 26 32 33 34 37").split()


def load_goldens():
    return {path.stem: json.loads(path.read_text()) for path in sorted(GOLDEN_DIR.glob("g*.json"))}


GOLDENS = load_goldens()
SUCCESS = {name: g for name, g in GOLDENS.items() if "expected_open_questions_contain" not in g}
BLOCKED = {name: g for name, g in GOLDENS.items() if "expected_open_questions_contain" in g}


def values(output):
    return {line: record["value"] for line, record in output["lines"].items()}


class GoldenReturns(unittest.TestCase):
    def test_R12_golden_set_is_complete(self):
        self.assertGreaterEqual(len(GOLDENS), 7)
        self.assertTrue(SUCCESS and BLOCKED)

    def test_R12_values_match_hand_derivation(self):
        for name, golden in SUCCESS.items():
            with self.subTest(case=name):
                output = compute_return(copy.deepcopy(golden["state"]), now=NOW)
                self.assertEqual(output["open_questions"], [])
                got = values(output)
                expected = golden["expected_nonzero"]
                for line, value in expected.items():
                    self.assertEqual(got.get(line), value, f"line {line}")
                for line in ALL_LINES:
                    if line not in expected:
                        self.assertEqual(got.get(line), 0, f"line {line} should be 0")

    def test_R12_every_line_is_present(self):
        for name, golden in SUCCESS.items():
            with self.subTest(case=name):
                self.assertEqual(set(values(compute_return(copy.deepcopy(golden["state"]), now=NOW))), set(ALL_LINES))

    def test_R10_output_passes_the_state_contract(self):
        for name, golden in SUCCESS.items():
            with self.subTest(case=name):
                output = compute_return(copy.deepcopy(golden["state"]), now=NOW)
                checked = validate_update("computation", copy.deepcopy(output))
                self.assertEqual(set(checked), AGENT_FIELDS["computation"])
                self.assertEqual(set(checked["lines"]), set(ALL_LINES))

    def test_R10_blocked_cases(self):
        for name, golden in BLOCKED.items():
            with self.subTest(case=name):
                output = compute_return(copy.deepcopy(golden["state"]), now=NOW)
                self.assertEqual(output["lines"], {})
                self.assertTrue(output["open_questions"])
                for fragment in golden["expected_open_questions_contain"]:
                    self.assertTrue(any(fragment in q for q in output["open_questions"]), fragment)
                validate_update("computation", copy.deepcopy(output))

    def test_R12_confirmed_values_are_marked_in_sources(self):
        for name, golden in SUCCESS.items():
            for line, doc_id in golden.get("expect_source_confirmed", {}).items():
                with self.subTest(case=name, line=line):
                    record = compute_return(copy.deepcopy(golden["state"]), now=NOW)["lines"][line]
                    self.assertTrue(any(s.get("doc_id") == doc_id and s.get("confirmed_by") == "user_input"
                                        for s in record["sources"]))


class Arithmetic(unittest.TestCase):
    """Identities that must hold on any computed return, independent of the golden numbers."""

    def test_C7_C9_C13_C14_C19_C20_line_identities(self):
        for name, golden in SUCCESS.items():
            with self.subTest(case=name):
                v = values(compute_return(copy.deepcopy(golden["state"]), now=NOW))
                self.assertEqual(v["9"], v["1z"] + v["2b"] + v["3b"] + v["4b"] + v["5b"] + v["6b"] + v["7"] + v["8"])
                self.assertEqual(v["11a"], v["9"] - v["10"])
                self.assertEqual(v["14"], v["12e"] + v["13a"] + v["13b"])
                self.assertEqual(v["15"], max(0, v["11a"] - v["14"]))
                self.assertEqual(v["24"], v["22"] + v["23"])
                self.assertEqual(v["25d"], v["25a"] + v["25b"] + v["25c"])
                self.assertEqual(v["33"], v["25d"] + v["26"] + v["32"])
                self.assertEqual(v["34"], max(0, v["33"] - v["24"]))
                self.assertEqual(v["37"], max(0, v["24"] - v["33"]))
                self.assertTrue(v["34"] == 0 or v["37"] == 0)

    def test_C6_6b_never_exceeds_85_percent_of_6a(self):
        for name, golden in SUCCESS.items():
            with self.subTest(case=name):
                v = values(compute_return(copy.deepcopy(golden["state"]), now=NOW))
                self.assertLessEqual(v["6b"], 0.85 * v["6a"] + 0.5)


class ScheduleOneFeedsSocialSecurity(unittest.TestCase):
    """Lines 8 and 10 change provisional income, so they must change 6b (no golden exercises this)."""

    def run_with(self, **user_inputs):
        state = copy.deepcopy(SUCCESS["g01_single_ss_50pct"]["state"])
        state["user_inputs"] = user_inputs
        return values(compute_return(state, now=NOW))

    def oracle_6b(self, line8=0, line10=0):
        from tests import oracle
        return oracle.taxable_ss("single", 24000, 20000 + 1200 + line8, 0, line10)

    def test_C6_line_8_raises_taxable_benefits(self):
        got = self.run_with(**{"8": 2000})
        self.assertEqual(got["6b"], self.oracle_6b(line8=2000))
        self.assertEqual(got["6b"], 5520)
        self.assertEqual(got["9"], 20000 + 1200 + 2000 + 5520)

    def test_C6_line_10_lowers_taxable_benefits_and_agi(self):
        got = self.run_with(**{"10": 1000})
        self.assertEqual(got["6b"], self.oracle_6b(line10=1000))
        self.assertEqual(got["6b"], 3600)  # provisional 32,200; 0.5 x 7,200
        self.assertEqual(got["11a"], got["9"] - 1000)


class Provenance(unittest.TestCase):
    def setUp(self):
        self.lines = compute_return(copy.deepcopy(SUCCESS["g02_mfj_two_seniors_ss_cap"]["state"]), now=NOW)["lines"]

    def test_R9_kinds(self):
        self.assertEqual(self.lines["16"]["kind"], "computed")
        self.assertEqual(self.lines["26"]["kind"], "user_input")
        self.assertEqual(self.lines["7"]["kind"], "default_zero")
        self.assertEqual(self.lines["10"]["kind"], "default_zero")

    def test_R9_computed_lines_cite_a_tool_and_inputs(self):
        for line, record in self.lines.items():
            if record["kind"] == "computed":
                with self.subTest(line=line):
                    self.assertTrue(record["tool"]["name"])
                    self.assertEqual(record["tool"]["tax_year"], 2025)
                    self.assertTrue(record["inputs"] and record["formula"])

    def test_C1_document_lines_trace_to_boxes(self):
        sources = self.lines["6a"]["sources"]
        self.assertEqual(sorted(s["doc_id"] for s in sources), ["ssa_1", "ssa_2"])
        self.assertTrue(all(s["box"] == "5" for s in sources))
        self.assertEqual(self.lines["5a"]["sources"][0]["doc_id"], "r_1")

    def test_A23_unrounded_value_is_kept_in_formula(self):
        record = compute_return(copy.deepcopy(SUCCESS["g04_hoh_pension_half_dollar_credits"]["state"]), now=NOW)["lines"]["16"]
        self.assertEqual(record["value"], 718)
        self.assertIn("717.5", record["formula"])

    def test_R9_timestamps_have_a_timezone(self):
        self.assertTrue(all(r["timestamp"] == NOW for r in self.lines.values()))
        default = compute_return(copy.deepcopy(SUCCESS["g01_single_ss_50pct"]["state"]))["lines"]["9"]["timestamp"]
        self.assertRegex(default, r"[+-]\d\d:\d\d$|Z$")

    def test_C8_full_provenance_record_in_user_inputs_is_preserved(self):
        state = copy.deepcopy(SUCCESS["g01_single_ss_50pct"]["state"])
        state["user_inputs"]["23"] = {"value": 50, "kind": "human_resolution", "entered_by": "staff:jlee",
                                      "timestamp": NOW, "citation": "policy.md#schedules"}
        record = compute_return(state, now=NOW)["lines"]["23"]
        self.assertEqual((record["value"], record["kind"], record["entered_by"]), (50, "human_resolution", "staff:jlee"))
        validate_update("computation", {"lines": {"23": record}})


class Blocking(unittest.TestCase):
    def state(self, **changes):
        state = copy.deepcopy(SUCCESS["g01_single_ss_50pct"]["state"])
        state.update(changes)
        return state

    def blocked(self, state, fragment):
        output = compute_return(state, now=NOW)
        self.assertEqual(output["lines"], {})
        self.assertTrue(any(fragment in q for q in output["open_questions"]), output["open_questions"])
        return output

    def test_R10_missing_prerequisites_are_named(self):
        self.blocked(self.state(filing_status_validated=None), "filing_status")
        self.blocked(self.state(scope={"in_scope": False}), "scope.in_scope")
        self.blocked(self.state(eligibility={}), "eligibility")
        state = self.state()
        del state["box_count_12d"]
        self.blocked(state, "box_count_12d")

    def test_C10_box_count_disagreement_blocks(self):
        self.blocked(self.state(box_count_12d=2), "box_count_12d")

    def test_C1_blank_required_box(self):
        state = self.state()
        state["documents"][0]["boxes"]["1"] = None
        self.blocked(state, "documents.w2_1.boxes.1")

    def test_C1_negative_or_non_numeric_box(self):
        for bad in (-5, "abc"):
            with self.subTest(bad=bad):
                state = self.state()
                state["documents"][0]["boxes"]["1"] = bad
                self.blocked(state, "documents.w2_1.boxes.1")

    def test_C8_bad_user_input(self):
        self.blocked(self.state(user_inputs={"19": -10}), "user_inputs.19")
        self.blocked(self.state(user_inputs={"20": "lots"}), "user_inputs.20")

    def test_A17_mfs_who_lived_with_spouse_is_out_of_worksheet(self):
        golden = SUCCESS["g05_mfs_senior_deduction_zero"]["state"]
        state = copy.deepcopy(golden)
        state["intake"]["mfs_lived_with_spouse"] = True
        output = compute_return(state, now=NOW)
        self.assertEqual(output["lines"], {})
        self.assertTrue(any("Social Security" in q for q in output["open_questions"]))

    def test_C12_mfs_with_senior_qualifier_still_gets_zero(self):
        state = copy.deepcopy(SUCCESS["g05_mfs_senior_deduction_zero"]["state"])
        state["eligibility"]["senior_deduction_qualifiers"] = ["taxpayer"]
        output = compute_return(state, now=NOW)
        self.assertEqual(output["open_questions"], [])
        self.assertEqual(values(output)["13b"], 0)

    def test_C8_required_direct_lines_switch(self):
        original = computation.REQUIRED_DIRECT_LINES
        computation.REQUIRED_DIRECT_LINES = ("10", "26")
        try:
            output = compute_return(self.state(), now=NOW)
            self.assertEqual(output["lines"], {})
            self.assertEqual(sum("user_inputs.10" in q or "user_inputs.26" in q for q in output["open_questions"]), 2)
            ok = compute_return(self.state(user_inputs={"10": 0, "26": 0}), now=NOW)
            self.assertEqual(ok["open_questions"], [])
        finally:
            computation.REQUIRED_DIRECT_LINES = original

    def test_R10_blocked_output_never_mixes_lines_and_questions(self):
        output = compute_return(self.state(box_count_12d=3), now=NOW)
        self.assertFalse(output["lines"] and output["open_questions"])


class Behaviour(unittest.TestCase):
    def test_R10_input_state_is_not_mutated(self):
        for golden in GOLDENS.values():
            state = copy.deepcopy(golden["state"])
            before = copy.deepcopy(state)
            compute_return(state, now=NOW)
            self.assertEqual(state, before)

    def test_R9_deterministic(self):
        state = SUCCESS["g02_mfj_two_seniors_ss_cap"]["state"]
        self.assertEqual(compute_return(copy.deepcopy(state), now=NOW), compute_return(copy.deepcopy(state), now=NOW))

    def test_R10_document_order_does_not_matter(self):
        state = copy.deepcopy(SUCCESS["g02_mfj_two_seniors_ss_cap"]["state"])
        shuffled = copy.deepcopy(state)
        shuffled["documents"].reverse()
        self.assertEqual(compute_return(state, now=NOW), compute_return(shuffled, now=NOW))

    def test_R10_only_contract_fields_are_returned(self):
        output = run(copy.deepcopy(SUCCESS["g01_single_ss_50pct"]["state"]))
        self.assertEqual(set(output), {"lines", "open_questions"})

    def test_R10_works_inside_a_running_event_loop(self):
        import asyncio

        async def inside():
            return compute_return(copy.deepcopy(SUCCESS["g01_single_ss_50pct"]["state"]), now=NOW)

        self.assertEqual(asyncio.run(inside())["lines"]["34"]["value"], 1345)

    def test_C4_ira_flag_routes_to_line_4_not_5(self):
        state = copy.deepcopy(SUCCESS["g03_single_ira_qcd_phaseout"]["state"])
        v = values(compute_return(state, now=NOW))
        self.assertEqual((v["4a"], v["5a"]), (120000, 0))

    def test_C1_multiple_w2s_are_summed(self):
        state = copy.deepcopy(SUCCESS["g01_single_ss_50pct"]["state"])
        state["documents"].append({"doc_id": "w2_2", "form": "W-2", "boxes": {"1": 5000, "2": 400}})
        v = values(compute_return(state, now=NOW))
        self.assertEqual((v["1a"], v["25a"]), (25000, 1900))

    def test_C7_negative_schedule_1_total_is_allowed(self):
        state = copy.deepcopy(SUCCESS["g01_single_ss_50pct"]["state"])
        state["user_inputs"]["8"] = -300
        out = compute_return(state, now=NOW)
        self.assertEqual(out["open_questions"], [])
        self.assertEqual(values(out)["8"], -300)

    def test_R10_cli_main_runs(self):
        import contextlib
        import io

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = computation.main([str(GOLDEN_DIR / "g01_single_ss_50pct.json")])
        self.assertEqual(code, 0)
        self.assertIn("1,345", buffer.getvalue())
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(computation.main([str(GOLDEN_DIR / "g07_blocked_low_confidence_box.json")]), 1)


if __name__ == "__main__":
    unittest.main()
