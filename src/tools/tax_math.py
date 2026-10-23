"""Deterministic tax arithmetic for SilverFile (workstream P2, tax year 2025).

Every function here is pure: same inputs, same output, no I/O, no LLM, no clock. The MCP
server (src/tools/mcp_server.py) exposes each one as a tool, and the Computation agent takes
every dollar amount from these tools (spec section 4: "every number comes from a
deterministic MCP tool call").

Conventions
- Amounts are computed in Decimal and rounded to whole dollars, half away from zero
  ("half up", assumption A23), once per tool call. Python's built-in round() is banker's
  rounding and is never used for money.
- Every tool returns a JSON-serializable dict:
    value     int   whole dollars (a count for count_12d_boxes)
    formula   str   the calculation with the actual numbers substituted
    inputs    list  [{"label", "line"?, "value"}] echo of what was used
    tool      dict  {"name", "version", "tax_year"}
    citation  str   data/policy.md anchor, or None
  plus "unrounded" when rounding changed the value.
- Invalid or out-of-scope input raises TaxMathError. The MCP layer turns that into a tool error.

Sources for the constants (checked 2026-10-23): the assignment spec section 3.2 (standard
deduction, senior deduction, Social Security thresholds); Rev. Proc. 2024-40 rate schedules
(via Bradford Tax Institute and a second tax-bracket summary that agree to the dollar); the IRS
Social Security Benefits Worksheet (Pub. 915 / Form 1040 instructions).
"""
import math
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

TOOL_VERSION = "1.0"
TAX_YEAR = 2025
FILING_STATUSES = ("single", "mfj", "mfs", "hoh", "qss")

CITE_STANDARD_DEDUCTION = "policy.md#standard-deduction"
CITE_SENIOR_DEDUCTION = "policy.md#senior-deduction"
CITE_BOX_COUNT = "policy.md#line-12d-box-count"
CITE_SOCIAL_SECURITY = "policy.md#social-security-exclusions"

# --- Parameters -----------------------------------------------------------------------

STANDARD_BASE = {"single": 15750, "mfs": 15750, "mfj": 31500, "qss": 31500, "hoh": 23625}
# +2,000 per box if unmarried and not a surviving spouse, otherwise +1,600 (spec 3.2.2).
STANDARD_ADDITIONAL = {"single": 2000, "hoh": 2000, "mfj": 1600, "mfs": 1600, "qss": 1600}

SENIOR_AMOUNT = Decimal(6000)
SENIOR_PHASEOUT_RATE = Decimal("0.06")
SENIOR_THRESHOLD = {"mfj": Decimal(150000)}
SENIOR_THRESHOLD_DEFAULT = Decimal(75000)

# Social Security worksheet: (base amount, width of the 50% tier). Lines 8 and 10 of the IRS worksheet.
SS_BASE = {"mfj": (Decimal(32000), Decimal(12000))}
SS_BASE_DEFAULT = (Decimal(25000), Decimal(9000))

_RATES = [Decimal(r) for r in ("0.10", "0.12", "0.22", "0.24", "0.32", "0.35", "0.37")]
_UPPER_LIMITS = {
    "single": [11925, 48475, 103350, 197300, 250525, 626350, None],
    "mfj": [23850, 96950, 206700, 394600, 501050, 751600, None],
    "mfs": [11925, 48475, 103350, 197300, 250525, 375800, None],
    "hoh": [17000, 64850, 103350, 197300, 250500, 626350, None],
}
_UPPER_LIMITS["qss"] = _UPPER_LIMITS["mfj"]  # qualifying surviving spouse uses the joint schedule


class TaxMathError(ValueError):
    """Invalid or out-of-scope input to a tax tool."""


# --- Helpers --------------------------------------------------------------------------

def to_decimal(value: Any, name: str = "value") -> Decimal:
    """Convert a number or numeric string ('$1,234.50') to Decimal. Booleans are rejected."""
    if isinstance(value, bool):
        raise TaxMathError(f"{name}: a true/false value is not an amount")
    if isinstance(value, Decimal):
        amount = value
    elif isinstance(value, int):
        amount = Decimal(value)
    elif isinstance(value, float):
        if not math.isfinite(value):
            raise TaxMathError(f"{name}: {value!r} is not a finite number")
        amount = Decimal(str(value))
    elif isinstance(value, str):
        try:
            amount = Decimal(value.strip().replace("$", "").replace(",", ""))
        except InvalidOperation:
            raise TaxMathError(f"{name}: {value!r} is not a number") from None
    else:
        raise TaxMathError(f"{name}: expected a number, got {type(value).__name__}")
    if not amount.is_finite():
        raise TaxMathError(f"{name}: {value!r} is not a finite number")
    return amount


def round_half_up(value: Any) -> int:
    """Whole dollars, halves rounded away from zero (A23). 2974.5 -> 2975."""
    return int(to_decimal(value).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _plain(value: Decimal) -> str:
    """Readable number for formulas: no exponent, no trailing zeros."""
    if value == value.to_integral_value():
        return str(int(value))
    return format(value.normalize(), "f")


def _term(value: Decimal) -> str:
    return f"({_plain(value)})" if value < 0 else _plain(value)


def _json_number(value: Decimal) -> int | float:
    return int(value) if value == value.to_integral_value() else float(value)


def _status(filing_status: Any) -> str:
    status = str(filing_status).strip().lower()
    if status not in FILING_STATUSES:
        raise TaxMathError(f"Unknown filing status {filing_status!r}; expected one of {', '.join(FILING_STATUSES)}")
    return status


def _flag(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise TaxMathError(f"{name}: expected true or false")
    return value


def _count(value: Any, name: str, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TaxMathError(f"{name}: expected a whole number")
    if not 0 <= value <= maximum:
        raise TaxMathError(f"{name}: {value} is outside 0..{maximum}")
    return value


def _result(tool: str, value: int, formula: str, inputs: list[dict], citation: str | None = None,
            unrounded: Decimal | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "value": int(value),
        "formula": formula,
        "inputs": inputs,
        "tool": {"name": tool, "version": TOOL_VERSION, "tax_year": TAX_YEAR},
        "citation": citation,
    }
    if unrounded is not None and unrounded != Decimal(value):
        out["unrounded"] = _plain(unrounded)
    return out


def _entry(label: str, value: Decimal | int | str | bool, line: str | None = None) -> dict:
    entry: dict[str, Any] = {"label": label}
    if line:
        entry["line"] = line
    entry["value"] = _json_number(value) if isinstance(value, Decimal) else value
    return entry


# --- Tools ----------------------------------------------------------------------------

def sum_amounts(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Add amounts and round the total to whole dollars (half up).

    items: list of {"label": str, "value": number, "line": optional str}. An empty list gives 0.
    Used for every total on the return (lines 1z, 2a/2b, 3a/3b, 4a, 5a/5b, 6a, 9, 14, 18, 21,
    24, 25a-25d, 32, 33) so that all addition goes through one audited code path.
    """
    if not isinstance(items, list):
        raise TaxMathError("items must be a list")
    amounts: list[Decimal] = []
    inputs: list[dict] = []
    for position, item in enumerate(items):
        if not isinstance(item, dict) or "value" not in item:
            raise TaxMathError(f"items[{position}] must be an object with a value")
        amount = to_decimal(item["value"], f"items[{position}].value")
        amounts.append(amount)
        inputs.append(_entry(str(item.get("label", f"item {position + 1}")), amount, item.get("line")))
    total = sum(amounts, Decimal(0))
    if not amounts:
        formula = "0 (nothing to add)"
    else:
        formula = " + ".join(_term(a) for a in amounts)
    return _result("sum_amounts", round_half_up(total), formula, inputs, unrounded=total)


def subtract(minuend: float, subtrahend: float, floor_zero: bool = True,
             minuend_label: str = "minuend", subtrahend_label: str = "subtrahend",
             minuend_line: str | None = None, subtrahend_line: str | None = None) -> dict[str, Any]:
    """Compute minuend - subtrahend, rounded to whole dollars (half up).

    floor_zero=True gives max(0, a - b), used for lines 4b, 15, 22, 34 and 37.
    floor_zero=False allows a negative result, used for AGI (line 11a).
    """
    a = to_decimal(minuend, "minuend")
    b = to_decimal(subtrahend, "subtrahend")
    flag = _flag(floor_zero, "floor_zero")
    difference = a - b
    shown = f"{_term(a)} - {_term(b)}"
    value = round_half_up(difference)
    if flag:
        value = max(0, value)
        shown = f"max(0, {shown})"
    return _result("subtract", value, shown,
                   [_entry(minuend_label, a, minuend_line), _entry(subtrahend_label, b, subtrahend_line)],
                   unrounded=difference if not flag or difference >= 0 else None)


def count_12d_boxes(filing_status: str, taxpayer_65: bool, taxpayer_blind: bool,
                    spouse_65: bool = False, spouse_blind: bool = False) -> dict[str, Any]:
    """Count the boxes checked on line 12d: taxpayer 65+, taxpayer blind, spouse 65+, spouse blind.

    Spouse boxes count only on a joint return (policy.md#line-12d-box-count). A spouse box on
    any other status is rejected, because the case is outside what SilverFile handles.
    """
    status = _status(filing_status)
    boxes = {
        "taxpayer 65 or older": _flag(taxpayer_65, "taxpayer_65"),
        "taxpayer blind": _flag(taxpayer_blind, "taxpayer_blind"),
        "spouse 65 or older": _flag(spouse_65, "spouse_65"),
        "spouse blind": _flag(spouse_blind, "spouse_blind"),
    }
    if status != "mfj" and (boxes["spouse 65 or older"] or boxes["spouse blind"]):
        raise TaxMathError("Spouse age/blindness boxes can be counted only on a joint return (MFJ)")
    count = sum(boxes.values())
    inputs = [_entry("filing status", status)] + [_entry(label, checked) for label, checked in boxes.items()]
    formula = " + ".join(str(int(checked)) for checked in boxes.values()) + f" = {count}"
    return _result("count_12d_boxes", count, formula, inputs, CITE_BOX_COUNT)


def standard_deduction(filing_status: str, box_count: int) -> dict[str, Any]:
    """Line 12e: base amount for the filing status plus an add-on for each checked 12d box.

    2025 base: 15,750 Single/MFS, 31,500 MFJ/QSS, 23,625 HOH. Each box adds 2,000 (Single, HOH)
    or 1,600 (MFJ, MFS, QSS). Standard deduction only: itemizing is out of scope.
    """
    status = _status(filing_status)
    boxes = _count(box_count, "box_count", 4 if status == "mfj" else 2)
    base, add = STANDARD_BASE[status], STANDARD_ADDITIONAL[status]
    value = base + boxes * add
    return _result("standard_deduction", value, f"{base} + {boxes} * {add}",
                   [_entry("filing status", status), _entry("line 12d box count", boxes, "12d")],
                   CITE_STANDARD_DEDUCTION)


def senior_deduction(filing_status: str, agi: float, qualifier_count: int) -> dict[str, Any]:
    """Line 13b: enhanced senior deduction (Schedule 1-A), 2025 to 2028.

    Each qualifying person (decided by the Rules agent: age 65+, valid SSN) starts at
    6,000. Each person's amount is reduced by 6% of the AGI above 75,000 (150,000 if MFJ),
    never below 0. MFS always gets 0 (C12). MAGI is taken to be AGI (line 11a). The line total is rounded once.
    This is separate from, and in addition to, the additional standard deduction on line 12e.
    """
    status = _status(filing_status)
    income = to_decimal(agi, "agi")
    people = _count(qualifier_count, "qualifier_count", 2 if status == "mfj" else 1)
    if status == "mfs":  # rule C12 / A12: MFS gets 0 whatever Rules reports as qualifiers
        return _result("senior_deduction", 0, "married filing separately: senior deduction is 0",
                       [_entry("filing status", status), _entry("AGI (line 11a, used as MAGI)", income, "11a"),
                        _entry("qualifying people (ignored for MFS)", people)], CITE_SENIOR_DEDUCTION)
    threshold = SENIOR_THRESHOLD.get(status, SENIOR_THRESHOLD_DEFAULT)
    excess = max(Decimal(0), income - threshold)
    each = max(Decimal(0), SENIOR_AMOUNT - SENIOR_PHASEOUT_RATE * excess)
    total = each * people
    inputs = [_entry("filing status", status), _entry("AGI (line 11a, used as MAGI)", income, "11a"),
              _entry("qualifying people", people)]
    if people == 0:
        return _result("senior_deduction", 0, "no qualifying person: 0", inputs, CITE_SENIOR_DEDUCTION)
    formula = (f"{people} * max(0, {_plain(SENIOR_AMOUNT)} - {_plain(SENIOR_PHASEOUT_RATE)} * "
               f"max(0, {_term(income)} - {_plain(threshold)}))")
    return _result("senior_deduction", round_half_up(total), formula, inputs, CITE_SENIOR_DEDUCTION,
                   unrounded=total)


def income_tax(filing_status: str, taxable_income: float) -> dict[str, Any]:
    """Line 16: tax from the 2025 rate schedule for the filing status (not the IRS Tax Table).

    Brackets are Rev. Proc. 2024-40. QSS uses the joint schedule. The result is rounded to whole
    dollars (half up). The IRS Tax Table and the qualified-dividends worksheet are not used, so
    results may differ from commercial software by a few dollars (assumption A14).
    """
    status = _status(filing_status)
    income = to_decimal(taxable_income, "taxable_income")
    if income < 0:
        raise TaxMathError("taxable_income cannot be negative")
    inputs = [_entry("filing status", status), _entry("taxable income (line 15)", income, "15")]
    tax = Decimal(0)
    floor = Decimal(0)
    steps: list[str] = []
    for rate, upper in zip(_RATES, _UPPER_LIMITS[status]):
        ceiling = Decimal(upper) if upper is not None else None
        if ceiling is not None and income > ceiling:
            portion = ceiling - floor
            steps.append(f"{_plain(rate * 100)}% * {_plain(portion)}")
            tax += rate * portion
            floor = ceiling
            continue
        portion = income - floor
        if portion > 0 or not steps:
            steps.append(f"{_plain(rate * 100)}% * {_plain(portion)}")
            tax += rate * portion
        break
    return _result("income_tax", round_half_up(tax), " + ".join(steps), inputs, unrounded=tax)


def taxable_social_security(filing_status: str, benefits: float, other_income: float,
                            tax_exempt_interest: float, adjustments: float,
                            mfs_lived_with_spouse: bool = False) -> dict[str, Any]:
    """Line 6b: taxable Social Security, following the IRS Social Security Benefits Worksheet.

    benefits            line 6a (SSA-1099 box 5)
    other_income        lines 1z + 2b + 3b + 4b + 5b + 7 + 8 (everything except the benefits)
    tax_exempt_interest line 2a
    adjustments         line 10
    Provisional income = 0.5 * benefits + other income + tax-exempt interest - adjustments.
    Base amounts 25,000 / 32,000 (MFJ); the 50% tier is 9,000 / 12,000 wide (34,000 / 44,000).
    This must run after every other income line is known (line 6b feeds line 9 and AGI).
    MFS taxpayers who lived with their spouse in 2025 are outside the worksheet: rejected.
    """
    status = _status(filing_status)
    ssb = to_decimal(benefits, "benefits")
    other = to_decimal(other_income, "other_income")
    exempt = to_decimal(tax_exempt_interest, "tax_exempt_interest")
    adjust = to_decimal(adjustments, "adjustments")
    lived_with = _flag(mfs_lived_with_spouse, "mfs_lived_with_spouse")
    if ssb < 0 or exempt < 0 or adjust < 0:
        raise TaxMathError("benefits, tax_exempt_interest and adjustments cannot be negative")
    if status == "mfs" and lived_with:
        raise TaxMathError("MFS taxpayers who lived with their spouse in 2025 are outside the Social Security "
                           "worksheet (escalate to staff)")
    inputs = [_entry("filing status", status),
              _entry("Social Security benefits (line 6a)", ssb, "6a"),
              _entry("other income (lines 1z+2b+3b+4b+5b+7+8)", other),
              _entry("tax-exempt interest (line 2a)", exempt, "2a"),
              _entry("adjustments (line 10)", adjust, "10")]
    if ssb == 0:
        return _result("taxable_social_security", 0, "no Social Security benefits: 0", inputs, CITE_SOCIAL_SECURITY)
    base, width = SS_BASE.get(status, SS_BASE_DEFAULT)
    half = ssb / 2                                            # worksheet line 2
    provisional = half + other + exempt - adjust              # lines 5 - 6 = line 7
    cap = ssb * Decimal("0.85")                               # line 17
    head = (f"provisional income {_plain(provisional)} = {_plain(half)} (half of benefits) + {_term(other)} "
            f"(other income) + {_plain(exempt)} (tax-exempt interest) - {_plain(adjust)} (adjustments); "
            f"base {_plain(base)}")
    if provisional <= base:
        return _result("taxable_social_security", 0, f"{head}; provisional income does not exceed base: 0",
                       inputs, CITE_SOCIAL_SECURITY)
    excess = provisional - base                               # line 9
    upper = max(Decimal(0), excess - width)                   # line 11
    lower = min(excess, width)                                # line 12
    first_tier = min(half, lower / 2)                         # lines 13-14
    second_tier = upper * Decimal("0.85")                     # line 15
    taxable = min(first_tier + second_tier, cap)              # lines 16-18
    formula = (f"{head}; excess {_plain(excess)}; taxable = min(min({_plain(half)}, 0.5 * {_plain(lower)}) + "
               f"0.85 * {_plain(upper)}, 0.85 * {_plain(ssb)}) = min({_plain(first_tier + second_tier)}, "
               f"{_plain(cap)})")
    return _result("taxable_social_security", round_half_up(taxable), formula, inputs, CITE_SOCIAL_SECURITY,
                   unrounded=taxable)


TOOLS = {
    "sum_amounts": sum_amounts,
    "subtract": subtract,
    "count_12d_boxes": count_12d_boxes,
    "standard_deduction": standard_deduction,
    "senior_deduction": senior_deduction,
    "income_tax": income_tax,
    "taxable_social_security": taxable_social_security,
}
