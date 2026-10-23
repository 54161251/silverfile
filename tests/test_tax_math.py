"""Unit tests for the pure tax functions. Run: python -m unittest discover -s tests -t .  (or pytest)."""
import unittest

from src.tools import tax_math as tm
from tests import oracle

STATUSES = ("single", "mfj", "mfs", "hoh", "qss")


class Rounding(unittest.TestCase):
    def test_A23_half_up_not_bankers(self):
        # Python's round() sends 0.5 and 2.5 to the even neighbour; the spec rounds half up (A23).
        self.assertEqual(tm.income_tax("single", 26775)["value"], 2975)   # 2974.5
        self.assertEqual(tm.senior_deduction("single", 75025, 1)["value"], 5999)  # 5998.5
        self.assertEqual(tm.sum_amounts([{"label": "a", "value": 10.25}, {"label": "b", "value": 5.25}])["value"], 16)  # 15.5

    def test_A23_values_are_whole_dollar_ints(self):
        for result in (tm.income_tax("hoh", 40001), tm.standard_deduction("mfj", 2), tm.subtract(10, 3)):
            self.assertIsInstance(result["value"], int)
            self.assertNotIsInstance(result["value"], bool)

    def test_A23_unrounded_reported_only_when_it_differs(self):
        self.assertIn("unrounded", tm.income_tax("single", 26775))
        self.assertNotIn("unrounded", tm.income_tax("single", 10000))


class IncomeTax(unittest.TestCase):
    def test_C15_matches_oracle_across_bracket_edges(self):
        edges = [0, 1, 5, 11925, 11926, 17000, 23850, 23851, 48475, 48476, 96950, 103350, 197300, 250525,
                 250526, 375800, 375801, 626350, 626351, 751600, 751601, 1_000_000]
        for status in STATUSES:
            for income in edges:
                with self.subTest(status=status, income=income):
                    self.assertEqual(tm.income_tax(status, income)["value"], oracle.tax(status, income))

    def test_C15_qss_uses_joint_schedule(self):
        self.assertEqual(tm.income_tax("qss", 60000)["value"], tm.income_tax("mfj", 60000)["value"])

    def test_C15_negative_income_rejected(self):
        with self.assertRaises(tm.TaxMathError):
            tm.income_tax("single", -1)

    def test_C15_unknown_status_rejected(self):
        with self.assertRaises(tm.TaxMathError):
            tm.income_tax("zzz", 1000)


class Deductions(unittest.TestCase):
    def test_C11_standard_deduction_matches_independent_table(self):
        # IRS 2025 chart: add 2,000 per box if single or head of household, else 1,600.
        for status in STATUSES:
            for boxes in range(0, 3):
                with self.subTest(status=status, boxes=boxes):
                    add = 2000 if status in ("single", "hoh") else 1600
                    self.assertEqual(tm.standard_deduction(status, boxes)["value"], oracle.STD[status] + boxes * add)

    def test_C11_standard_deduction(self):
        cases = {("single", 0): 15750, ("single", 2): 19750, ("mfj", 4): 37900, ("mfj", 3): 36300,
                 ("hoh", 1): 25625, ("mfs", 1): 17350, ("qss", 2): 34700}
        for (status, boxes), expected in cases.items():
            with self.subTest(status=status, boxes=boxes):
                self.assertEqual(tm.standard_deduction(status, boxes)["value"], expected)

    def test_C10_box_count(self):
        self.assertEqual(tm.count_12d_boxes("mfj", True, False, True, True)["value"], 3)
        self.assertEqual(tm.count_12d_boxes("single", True, True)["value"], 2)
        self.assertEqual(tm.count_12d_boxes("hoh", False, False)["value"], 0)

    def test_C10_spouse_boxes_only_on_joint_returns(self):
        with self.assertRaises(tm.TaxMathError):
            tm.count_12d_boxes("single", True, False, spouse_65=True)

    def test_C12_senior_deduction_matches_oracle(self):
        for status in STATUSES:
            for agi in (0, 74999, 75000, 75001, 100000, 150000, 175000, 200000, 400000):
                for people in (0, 1, 2):
                    if people == 2 and status != "mfj":
                        continue
                    with self.subTest(status=status, agi=agi, people=people):
                        self.assertEqual(tm.senior_deduction(status, agi, people)["value"],
                                         oracle.senior(status, agi, people))

    def test_C12_senior_deduction_mfs(self):
        # C12 / A12: MFS gets 0 whatever qualifier count Rules reports.
        for people in (0, 1):
            self.assertEqual(tm.senior_deduction("mfs", 10000, people)["value"], 0)

    def test_C12_senior_deduction_never_negative(self):
        self.assertEqual(tm.senior_deduction("single", 10_000_000, 1)["value"], 0)


class SocialSecurity(unittest.TestCase):
    def test_C6_matches_oracle(self):
        for status in ("single", "mfj", "hoh", "qss", "mfs"):
            for benefits in (0, 5000, 18000, 30000, 42000):
                for other in (0, 10000, 22000, 35000, 60000, 120000):
                    for exempt in (0, 1500):
                        with self.subTest(status=status, benefits=benefits, other=other, exempt=exempt):
                            got = tm.taxable_social_security(status, benefits, other, exempt, 0)["value"]
                            self.assertEqual(got, oracle.taxable_ss(status, benefits, other, exempt, 0))

    def test_C6_adjustments_reduce_provisional_income(self):
        with_adj = tm.taxable_social_security("single", 20000, 30000, 0, 5000)["value"]
        self.assertEqual(with_adj, oracle.taxable_ss("single", 20000, 30000, 0, 5000))
        self.assertLess(with_adj, tm.taxable_social_security("single", 20000, 30000, 0, 0)["value"])

    def test_C6_never_exceeds_85_percent_of_benefits(self):
        self.assertEqual(tm.taxable_social_security("single", 20000, 500000, 0, 0)["value"], 17000)

    def test_C6_zero_below_base(self):
        self.assertEqual(tm.taxable_social_security("single", 20000, 10000, 0, 0)["value"], 0)

    def test_A17_mfs_lived_with_spouse_is_out_of_scope(self):
        with self.assertRaises(tm.TaxMathError):
            tm.taxable_social_security("mfs", 10000, 20000, 0, 0, mfs_lived_with_spouse=True)


class Arithmetic(unittest.TestCase):
    def test_C14_subtract_floor(self):
        self.assertEqual(tm.subtract(5, 10)["value"], 0)
        self.assertEqual(tm.subtract(5, 10, floor_zero=False)["value"], -5)

    def test_C7_sum_records_inputs_and_formula(self):
        result = tm.sum_amounts([{"label": "a", "value": 3}, {"label": "b", "value": 4, "line": "2b"}])
        self.assertEqual(result["value"], 7)
        self.assertEqual(len(result["inputs"]), 2)
        self.assertTrue(result["formula"])
        self.assertEqual(result["tool"]["name"], "sum_amounts")

    def test_C7_non_numeric_rejected(self):
        for bad in ("abc", None, float("nan"), True):
            with self.subTest(bad=bad), self.assertRaises(tm.TaxMathError):
                tm.sum_amounts([{"label": "x", "value": bad}])

    def test_R9_every_tool_carries_audit_metadata(self):
        result = tm.income_tax("single", 50000)
        self.assertEqual(result["tool"]["tax_year"], 2025)
        self.assertTrue(result["inputs"])


if __name__ == "__main__":
    unittest.main()
