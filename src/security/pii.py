"""PII masking (P4): keep personal data out of logs, traces and anything outside the structured record.

What counts as PII here: Social Security numbers, names, dates of birth, street addresses,
e-mail addresses, phone numbers and bank account / routing numbers.

Three layers, use whichever fits:
  1. `mask_ssn(value)`          one SSN  ->  ***-**-1234
  2. `mask_text(text)`         free text: finds SSN-shaped numbers, e-mails and phone numbers
  3. `mask_data(obj)`          dicts / lists / pydantic models: masks by field NAME (ssn, name,
                               birth_date, address ...) and scrubs every string value with mask_text

For logging:
  * `install_pii_log_masking()`  one call; every log record in the process is scrubbed as it is
                                 created, so no handler or library can print a raw SSN.
  * `PIIMaskingFormatter`        also scrubs tracebacks and anything a custom handler adds.
  * `PIIMaskingFilter`           the same scrubbing as a standard logging filter.

Masking is one-way and lossy on purpose. The structured record (state["intake"]) keeps the real
value because Rules and the PDF need it; everything else gets the masked form.
"""
from __future__ import annotations

import logging
import re
from typing import Any

# --- patterns ---------------------------------------------------------------------------------
# Nine digits as 3-2-4 (dashes, spaces or nothing), not part of a longer run of digits.
# The backreference \2 stops mixed separators such as "123-45 6789" from half-matching.
_SSN_IN_TEXT = re.compile(r"(?<![0-9])([0-9]{3})([-\s]?)([0-9]{2})\2([0-9]{4})(?![0-9])")
_ALREADY_MASKED = re.compile(r"^\*{3}-\*{2}-[0-9]{4}$|^\*{3}-\*{2}-\*{4}$")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(r"(?<![0-9])(?:\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s][0-9]{3}[-.\s][0-9]{4}(?![0-9])")

FULL_SSN_MASK = "***-**-****"      # used when even the last four digits must not be kept
EMAIL_MASK = "[email withheld]"
PHONE_MASK = "[phone withheld]"
NAME_MASK = "[name withheld]"
DOB_MASK = "[date of birth withheld]"
ADDRESS_MASK = "[address withheld]"


def mask_ssn(value: Any, keep_last4: bool = True) -> str:
    """Return ***-**-1234 for any SSN-like value. Never raises, never echoes a bad value.

    Anything that is not exactly nine digits becomes ***-**-**** so a typo or a half-typed
    number cannot leak through the "masked" path. Masking a masked value changes nothing.
    """
    if isinstance(value, str) and _ALREADY_MASKED.match(value.strip()):
        return value.strip()
    digits = re.sub(r"[^0-9]", "", str(value)) if value is not None else ""
    if keep_last4 and len(digits) == 9:
        return f"***-**-{digits[-4:]}"
    return FULL_SSN_MASK


def mask_text(text: Any) -> str:
    """Scrub free text: SSN-shaped numbers, e-mail addresses and US phone numbers."""
    if text is None:
        return ""
    result = str(text)
    result = _SSN_IN_TEXT.sub(lambda m: f"***-**-{m.group(4)}", result)
    result = _EMAIL.sub(EMAIL_MASK, result)
    result = _PHONE.sub(PHONE_MASK, result)
    return result


def contains_raw_ssn(value: Any) -> bool:
    """True if any SSN-shaped number (not already masked) appears anywhere in `value`.

    Used by the tests and available for a last-line check before a trace is written.
    """
    return bool(_SSN_IN_TEXT.search(_flatten_text(value)))


def _flatten_text(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    if isinstance(value, dict):
        return " ".join(f"{k} {_flatten_text(v)}" for k, v in value.items())
    if isinstance(value, (list, tuple, set)):
        return " ".join(_flatten_text(v) for v in value)
    return "" if value is None else str(value)


# --- structured data --------------------------------------------------------------------------
_NAME_KEYS = {"name", "fullname", "firstname", "lastname", "middlename", "legalname", "taxpayername",
              "spousename", "dependentname", "employeename", "employeefirstname", "employeelastname"}
_DOB_KEYS = {"birthdate", "dateofbirth", "dob", "birthday"}
_SSN_KEYS = {"ssn", "socialsecuritynumber", "taxpayerid", "tin", "itin"}


def _key_kind(key: Any) -> str | None:
    """Classify a field name. Money fields such as 'social_security_wages' are NOT personal data."""
    k = re.sub(r"[^a-z0-9]", "", str(key).lower())
    if k in _SSN_KEYS or k.endswith("ssn"):
        return "ssn"
    if k in _DOB_KEYS:
        return "dob"
    if k in _NAME_KEYS:
        return "name"
    if "address" in k or k in {"street", "street1", "street2", "city", "zip", "zipcode", "postalcode"}:
        return "address"
    if "email" in k:
        return "email"
    if k in {"phone", "phonenumber", "mobile", "telephone", "cell"}:
        return "phone"
    if "account" in k and "owner" not in k and "type" not in k:
        return "account"
    if "routing" in k:
        return "account"
    return None


def _mask_account(value: Any) -> Any:
    digits = re.sub(r"[^0-9]", "", str(value))
    if len(digits) < 4:
        return "****"
    return "*" * (len(digits) - 4) + digits[-4:]


def mask_data(value: Any, _key: Any = None) -> Any:
    """Deep copy of `value` with personal data masked. The input is never changed.

    Works on dicts, lists, tuples, sets, pydantic models and plain values. A field is masked by
    its NAME first (ssn, name, birth_date, address, email, phone, account, routing) and then every
    remaining string is run through `mask_text`, so an SSN pasted into a free-text field is caught too.
    """
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    kind = _key_kind(_key) if _key is not None else None
    if kind and value not in (None, "", [], {}):
        if kind == "ssn":
            return mask_ssn(value)
        if kind == "dob":
            return DOB_MASK
        if kind == "name":
            return NAME_MASK if isinstance(value, str) else value
        if kind == "address":
            return ADDRESS_MASK
        if kind == "email":
            return EMAIL_MASK
        if kind == "phone":
            return PHONE_MASK
        if kind == "account" and isinstance(value, (str, int)) and not isinstance(value, bool):
            return _mask_account(value)
    if isinstance(value, dict):
        return {k: mask_data(v, k) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [mask_data(v, _key) for v in value]
    if isinstance(value, (set, frozenset)):
        return sorted(mask_data(v, _key) for v in value)
    if isinstance(value, str):
        return mask_text(value)
    return value


# --- logging ----------------------------------------------------------------------------------
_STANDARD_RECORD_FIELDS = set(vars(logging.LogRecord("x", 0, "x", 0, "x", (), None))) | {"message", "asctime"}


def _scrub_record(record: logging.LogRecord) -> None:
    """Replace the message and any custom `extra=` fields on a log record with masked copies."""
    try:
        record.msg = mask_text(record.getMessage())
    except Exception:       # a broken format string must not become a way to print raw data
        record.msg = "[log message withheld: could not be safely formatted]"
    record.args = ()
    for name in list(vars(record)):
        if name not in _STANDARD_RECORD_FIELDS:
            setattr(record, name, mask_data(getattr(record, name), name))


class PIIMaskingFilter(logging.Filter):
    """Standard logging filter: attach to a logger or handler to scrub its records."""

    def filter(self, record: logging.LogRecord) -> bool:
        _scrub_record(record)
        return True


class PIIMaskingFormatter(logging.Formatter):
    """Formatter that masks the finished text, which also covers tracebacks and stack info."""

    def format(self, record: logging.LogRecord) -> str:
        return mask_text(super().format(record))


_installed = False


def install_pii_log_masking() -> None:
    """Scrub every log record in this process as it is created. Safe to call many times."""
    global _installed
    if _installed:
        return
    previous = logging.getLogRecordFactory()

    def factory(*args, **kwargs):
        record = previous(*args, **kwargs)
        _scrub_record(record)
        return record

    logging.setLogRecordFactory(factory)
    _installed = True


def configure_masked_logging(level: int = logging.INFO, stream=None) -> logging.Handler:
    """One-call setup for scripts and the CLI: masked root logger writing to `stream` (stderr)."""
    install_pii_log_masking()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(PIIMaskingFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    handler.addFilter(PIIMaskingFilter())
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(level)
    return handler
