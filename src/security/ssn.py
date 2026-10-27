"""The SSN rule (P4, assignment section 3.2): only the SSA's 900-series test numbers are accepted.

The US government sets aside numbers starting 900 through 999 for testing. SilverFile is a
practice system, so a number outside that range is almost certainly someone's REAL Social
Security number. We refuse it, and we never store, log or echo it.

Why this file exists: the same check was written four times (state.py, ui/answers.py,
rules.py and review.py). This is the single reference version. The other modules can import
`is_test_ssn` / `check_ssn` instead of keeping their own regular expression (see the
interface requests in docs/P4_EXTRACTION_SECURITY.md).

Nothing in this file ever puts a full SSN in an error message, a repr or a log line.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

# ASCII digits only. `str.isdigit()` and `\d` also accept full-width and other Unicode digits,
# which would let a look-alike value slip past the range check.
_SSN_SHAPE = re.compile(r"([0-9]{3})([-\s]?)([0-9]{2})\2([0-9]{4})")

Reason = Literal["ok", "empty", "bad_format", "not_test_range"]

# Plain-language messages the intake page can show a taxpayer. None of them repeats the input.
USER_MESSAGES: dict[str, str] = {
    "ok": "",
    "empty": "Please enter the nine-digit number.",
    "bad_format": "That doesn't look like a nine-digit number. Please enter it like 900-12-3456.",
    "not_test_range": ("This practice system only accepts test numbers that start with 9, "
                       "like 900-12-3456. Please don't enter a real Social Security number."),
}


class InvalidTestSsn(ValueError):
    """Raised by `require_test_ssn`. The message never contains the rejected number."""

    def __init__(self, reason: Reason):
        self.reason = reason
        super().__init__(f"SSN rejected ({reason}): only 900-series test numbers are accepted")


@dataclass(frozen=True)
class SsnCheck:
    """Result of checking one value. Holds the full number ONLY when it passed the rule."""

    ok: bool
    reason: Reason
    normalized: str | None = None   # "901-23-4567" when ok, otherwise None (a rejected number is dropped)
    masked: str = "***-**-****"     # safe to show or log; keeps the last four only for accepted numbers

    def __repr__(self) -> str:  # never print the number, even by accident
        return f"SsnCheck(ok={self.ok}, reason={self.reason!r}, masked={self.masked!r})"

    __str__ = __repr__

    @property
    def message(self) -> str:
        """Plain-language text for the taxpayer (empty when the number was accepted)."""
        return USER_MESSAGES[self.reason]


def check_ssn(value: Any) -> SsnCheck:
    """Apply the testing-range rule.

    Accepted: nine digits starting 900-999, written 901-23-4567, 901 23 4567 or 901234567.
    Rejected: anything else, including numbers 000-899, wrong length, letters, mixed separators,
    non-text values (a bare integer can lose its shape), and Unicode look-alike digits.
    The input is stripped of surrounding spaces first, nothing else is "fixed".
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return SsnCheck(False, "empty")
    if not isinstance(value, str):
        return SsnCheck(False, "bad_format")
    match = _SSN_SHAPE.fullmatch(value.strip())
    if not match:
        return SsnCheck(False, "bad_format")
    area, _sep, group, serial = match.groups()
    if not area.startswith("9"):          # area numbers 900-999 are the test range
        return SsnCheck(False, "not_test_range")
    return SsnCheck(True, "ok", normalized=f"{area}-{group}-{serial}", masked=f"***-**-{serial}")


def is_test_ssn(value: Any) -> bool:
    """True only for an acceptable 900-series test SSN."""
    return check_ssn(value).ok


def require_test_ssn(value: Any) -> str:
    """Return the normalized SSN (901-23-4567) or raise `InvalidTestSsn` without echoing the input."""
    result = check_ssn(value)
    if not result.ok:
        raise InvalidTestSsn(result.reason)
    return result.normalized  # type: ignore[return-value]


# --------------------------------------------------------------------------------------------
# "Never ask for an SSN we don't need" (assignment 4.3). Only the people printed on the return
# have an SSN line on Form 1040-SR: the taxpayer, the spouse on a joint or separate return, and
# each listed dependent. Nobody else (an employer's contact, a helper, a payer) ever needs one.
# --------------------------------------------------------------------------------------------
_DEPENDENT_SSN = re.compile(r"^intake\.dependents\.(\d+)\.ssn$")


def required_ssn_fields(intake: dict | None) -> list[str]:
    """Full state paths of the SSNs this return actually needs, given the intake answers so far."""
    intake = intake or {}
    fields = ["intake.taxpayer.ssn"]
    if intake.get("filing_status") in ("mfj", "mfs"):
        fields.append("intake.spouse.ssn")
    for position, _dependent in enumerate(intake.get("dependents") or []):
        fields.append(f"intake.dependents.{position}.ssn")
    return fields


def ssn_request_allowed(field_path: str, intake: dict | None) -> bool:
    """Guard for Intake: may we ask the taxpayer for the SSN at `field_path` right now?

    Non-SSN fields are not this function's business and return True. For an SSN field the answer
    is True only when the return needs it (see `required_ssn_fields`) and we do not already hold
    an accepted value, so a taxpayer is never asked twice and never asked for an unneeded number.
    """
    if not str(field_path).lower().endswith("ssn"):
        return True
    if field_path not in required_ssn_fields(intake):
        return False
    return not _already_have(field_path, intake or {})


def _already_have(field_path: str, intake: dict) -> bool:
    node: Any = intake
    for part in field_path.split(".")[1:]:           # drop the leading "intake"
        if isinstance(node, list):
            node = node[int(part)] if part.isdigit() and int(part) < len(node) else None
        elif isinstance(node, dict):
            node = node.get(part)
        else:
            return False
        if node is None:
            return False
    return is_test_ssn(node)
