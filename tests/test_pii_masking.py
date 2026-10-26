"""P4: PII masking, and proof that raw SSNs never reach logs."""
import io
import logging

import pytest

from src.security.pii import (PIIMaskingFilter, PIIMaskingFormatter, configure_masked_logging,
                              contains_raw_ssn, install_pii_log_masking, mask_data, mask_ssn, mask_text)

RAW = "901-23-4567"
RAW_FORMS = ["901-23-4567", "901234567", "901 23 4567"]


@pytest.mark.parametrize("value", RAW_FORMS + [901234567])
def test_mask_ssn_keeps_only_last_four(value):
    assert mask_ssn(value) == "***-**-4567"


def test_mask_ssn_never_echoes_bad_input_and_is_idempotent():
    for bad in [None, "", "12", "hello", "123-45-678", "9" * 12]:
        assert mask_ssn(bad) == "***-**-****"
    assert mask_ssn("***-**-4567") == "***-**-4567"
    assert mask_ssn(mask_ssn(RAW)) == "***-**-4567"
    assert mask_ssn(RAW, keep_last4=False) == "***-**-****"


def test_mask_text_finds_ssn_email_and_phone_inside_sentences():
    text = f"Call 607-555-0147 or mail jo.doe@example.com; my number is {RAW}, again 901234567."
    out = mask_text(text)
    assert "4567" in out and "901-23" not in out and "901234567" not in out
    assert "jo.doe@example.com" not in out and "607-555-0147" not in out


def test_mask_text_leaves_normal_numbers_alone():
    text = "Wages 52,000.00 withheld 4,100.00 on 2026-10-26T14:40:00+00:00 form W-2 EIN 12-3456789"
    assert mask_text(text) == text


def test_mask_text_does_not_cut_into_longer_digit_runs():
    assert mask_text("order 1901234567890") == "order 1901234567890"


def test_mask_data_by_field_name():
    record = {
        "intake": {"taxpayer": {"ssn": RAW, "name": "Pat Example", "birth_date": "1955-06-01", "blind": False},
                   "refund": {"account_number": "123456789012", "account_owner": "unknown"},
                   "address": "1 Test Lane", "email": "a@b.co", "phone": "607-555-0100"},
        "documents": [{"doc_id": "w2_1", "boxes": {"1": 52000, "a": "***-**-4567",
                                                    "social_security_wages": 52000}}],
        "note": f"typed by mistake: {RAW}",
    }
    out = mask_data(record)
    assert out["intake"]["taxpayer"] == {"ssn": "***-**-4567", "name": "[name withheld]",
                                         "birth_date": "[date of birth withheld]", "blind": False}
    assert out["intake"]["refund"] == {"account_number": "********9012", "account_owner": "unknown"}
    assert out["intake"]["address"] == "[address withheld]"
    assert out["intake"]["email"] == "[email withheld]" and out["intake"]["phone"] == "[phone withheld]"
    assert out["documents"][0]["boxes"] == {"1": 52000, "a": "***-**-4567", "social_security_wages": 52000}
    assert out["note"] == "typed by mistake: ***-**-4567"
    assert not contains_raw_ssn(out)


def test_mask_data_does_not_modify_its_input_and_handles_models():
    from pydantic import BaseModel

    class Person(BaseModel):
        ssn: str
        wages: int

    original = {"p": Person(ssn=RAW, wages=5), "list": [{"ssn": RAW}]}
    out = mask_data(original)
    assert original["list"][0]["ssn"] == RAW and original["p"].ssn == RAW
    assert out["p"] == {"ssn": "***-**-4567", "wages": 5} and out["list"] == [{"ssn": "***-**-4567"}]


def test_contains_raw_ssn():
    assert contains_raw_ssn({"x": [f"abc {RAW}"]})
    assert contains_raw_ssn("901234567")
    assert not contains_raw_ssn({"ssn": "***-**-4567", "amount": "52,000.00"})


# --- logs: the raw SSN must never be written -------------------------------------------------------
@pytest.fixture
def log_stream():
    """A real handler writing to memory, with the masking formatter. Removed afterwards."""
    stream = io.StringIO()
    logger = logging.getLogger("p4.test")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    handler = logging.StreamHandler(stream)
    handler.setFormatter(PIIMaskingFormatter("%(levelname)s %(message)s"))
    logger.addHandler(handler)
    yield logger, stream
    logger.removeHandler(handler)


def test_formatter_masks_message_args_and_tracebacks(log_stream):
    logger, stream = log_stream
    logger.info("taxpayer ssn %s", RAW)
    logger.info(f"f-string {RAW}")
    logger.warning("dict %s", {"ssn": RAW})
    try:
        raise ValueError(f"bad value {RAW}")
    except ValueError:
        logger.exception("failed")
    output = stream.getvalue()
    assert "4567" in output                       # the masked form is there
    for form in RAW_FORMS:
        assert form not in output
    assert not contains_raw_ssn(output)


def test_record_factory_masks_even_with_an_unprotected_handler():
    """A plain handler with a plain formatter, which is what most libraries use."""
    install_pii_log_masking()
    install_pii_log_masking()                      # idempotent
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s | %(custom)s"))
    logger = logging.getLogger("p4.plain")
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    try:
        logger.info("ssn=%s", RAW, extra={"custom": {"ssn": RAW, "n": 1}})
        logger.debug("raw %s and %s", "901234567", RAW, extra={"custom": "none"})
    finally:
        logger.removeHandler(handler)
    output = stream.getvalue()
    assert not contains_raw_ssn(output) and "4567" in output


def test_filter_masks_records_on_a_logger():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(PIIMaskingFilter())
    logger = logging.getLogger("p4.filter")
    logger.propagate = False
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        logger.info("value %s", RAW)
    finally:
        logger.removeHandler(handler)
    assert stream.getvalue().strip() == "value ***-**-4567"


def test_broken_format_string_cannot_leak():
    install_pii_log_masking()
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logger = logging.getLogger("p4.broken")
    logger.propagate = False
    logger.addHandler(handler)
    try:
        logger.info("needs two %s %s", RAW)       # wrong number of arguments
    finally:
        logger.removeHandler(handler)
    assert RAW not in stream.getvalue() and "901234567" not in stream.getvalue()


def test_configure_masked_logging_roundtrip():
    stream = io.StringIO()
    root = logging.getLogger()
    before = list(root.handlers), root.level
    handler = configure_masked_logging(logging.INFO, stream)
    try:
        logging.getLogger("p4.root").info("ssn %s", RAW)
    finally:
        root.removeHandler(handler)
        root.setLevel(before[1])
    assert "***-**-4567" in stream.getvalue() and not contains_raw_ssn(stream.getvalue())
