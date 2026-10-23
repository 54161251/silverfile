"""Independent re-derivation of the 2025 return math, used to produce and check golden expectations.

Deliberately shares no code with src/tools/tax_math.py: separate bracket tables, plain Fraction
arithmetic, and the IRS Social Security worksheet written line by line. If this file and the
tools disagree, one of them is wrong; check against the IRS instructions before changing either.
"""
from fractions import Fraction as F

BRACKETS = {  # (upper limit, rate) per filing status, Rev. Proc. 2024-40
    "single": [(11925, "0.10"), (48475, "0.12"), (103350, "0.22"), (197300, "0.24"), (250525, "0.32"), (626350, "0.35"), (None, "0.37")],
    "mfs":    [(11925, "0.10"), (48475, "0.12"), (103350, "0.22"), (197300, "0.24"), (250525, "0.32"), (375800, "0.35"), (None, "0.37")],
    "mfj":    [(23850, "0.10"), (96950, "0.12"), (206700, "0.22"), (394600, "0.24"), (501050, "0.32"), (751600, "0.35"), (None, "0.37")],
    "hoh":    [(17000, "0.10"), (64850, "0.12"), (103350, "0.22"), (197300, "0.24"), (250500, "0.32"), (626350, "0.35"), (None, "0.37")],
}
BRACKETS["qss"] = BRACKETS["mfj"]
STD = {"single": 15750, "mfs": 15750, "mfj": 31500, "qss": 31500, "hoh": 23625}


def half_up(x) -> int:
    x = F(x)
    return int((x * 2 + 1) // 2) if x >= 0 else -int((-x * 2 + 1) // 2)


def tax(status, taxable):
    owed, lower = F(0), 0
    for upper, rate in BRACKETS[status]:
        top = taxable if upper is None else min(taxable, upper)
        if top > lower:
            owed += (top - lower) * F(rate)
        if upper is None or taxable <= upper:
            break
        lower = upper
    return half_up(owed)


def taxable_ss(status, benefits, other, exempt, adjustments):
    """Pub. 915 Worksheet 1, lines 1-19."""
    b = F(benefits)
    l7 = b / 2 + other + exempt - adjustments          # lines 2-7
    base, width = (32000, 12000) if status == "mfj" else (25000, 9000)
    if b == 0 or l7 <= base:
        return 0
    l10 = l7 - base                                    # line 9 or 10
    l12 = min(l10, width)                              # line 11/12
    l13 = l12 / 2
    l14 = min(b / 2, l13)
    l15 = max(F(0), l7 - (base + width))
    l16 = F("0.85") * l15
    return half_up(min(l14 + l16, F("0.85") * b))


def senior(status, agi, qualifiers):
    if status == "mfs":
        return 0
    threshold = 150000 if status == "mfj" else 75000
    per_person = max(F(0), 6000 - F("0.06") * max(0, agi - threshold))
    return half_up(per_person * qualifiers)
