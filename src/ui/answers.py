"""Screen a taxpayer's typed answer before it is sent to Intake (A19, R17).

`sessions.resume` stores the resume value in the checkpoint before Intake reads it, so an SSN
typed into the chat box would be saved even if Intake discarded it. The page therefore
checks every answer first:

- The question asks for an SSN (a field ending in `.ssn`): only a 900-series test number is
  sent. Anything else is refused on screen and never sent.
- Any other question: SSN-shaped numbers are replaced with SSN_MARKER before sending, so
  Intake can raise its `ssn_volunteered` flag without the number ever being stored.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

SSN_SHAPE = re.compile(r"(?<!\d)(\d{3})[- ]?(\d{2})[- ]?(\d{4})(?!\d)")
TEST_SSN = re.compile(r"^9\d{2}-\d{2}-\d{4}$")
SSN_MARKER = "[SSN removed]"
MAX_LENGTH = 500


@dataclass(frozen=True)
class Screened:
    send: str | None           # text to pass to sessions.resume, or None to refuse
    notice: str | None = None   # plain-language message to show the taxpayer
    shown: str | None = None    # what to show in the on-screen transcript


def asks_for_ssn(fields: list[str]) -> bool:
    return any(str(field).lower().endswith("ssn") for field in fields or [])


def screen(text: str, fields: list[str] | None = None) -> Screened:
    text = (text or "").strip()
    if not text:
        return Screened(None, "Please type an answer, or choose “I’m not sure”.")
    if len(text) > MAX_LENGTH:
        return Screened(None, "That answer is very long. Please keep it to a sentence or two.")
    numbers = list(SSN_SHAPE.finditer(text))
    if asks_for_ssn(fields):
        if len(numbers) != 1:
            return Screened(None, "Please type the nine-digit number on its own, like 900-12-3456.")
        number = "-".join(numbers[0].groups())
        if not TEST_SSN.match(number):
            return Screened(None, "This practice system only accepts test numbers that start with 9, "
                                  "like 900-12-3456. Please don’t enter a real Social Security number.")
        return Screened(number, shown=f"XXX-XX-{number[-4:]}")
    if numbers:
        cleaned = SSN_SHAPE.sub(SSN_MARKER, text)
        return Screened(cleaned, "For your safety, we removed a number that looked like a Social Security "
                                 "number. We don’t need it for this question.", shown=cleaned)
    return Screened(text, shown=text)
