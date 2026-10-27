# P4 handoff: W-2 extraction, SSN rule, PII masking, fixtures, eval cases

Owner: Christina (P4). All data is fake. Branch: `p4-extraction-security-fixtures`.

## What was built
- **W-2 Extraction agent** (`src/agents/extraction.py`, `src/extraction/*`). Reads a W-2 image/PDF with Tesseract, returns typed records (Pydantic, `src/extraction/schema.py`) with provenance. Does no arithmetic and no tax interpretation. A box it cannot read confidently becomes `None`, is listed in `unverified`, and is never guessed.
- **SSN rule** (`src/security/ssn.py`): only 900-999 accepted (`check_ssn`, `require_test_ssn`); `ssn_request_allowed` says whether an SSN may be asked for at all. A W-2 whose SSN is not a test number fails closed (all money boxes None, flag `ssn_not_test_range`).
- **PII masking** (`src/security/pii.py`): `mask_ssn` (`***-**-1234`), `mask_text`, `mask_data`, `install_pii_log_masking`, `configure_masked_logging`.
- **Fixtures** (`data/generate_fixtures.py`, output in `data/fixtures/`): deterministic fake W-2s (clean, scan, cents, smudged, blank box, real-looking SSN, 10-document batch). `--custom` makes your own.
- **Eval cases** (`evals/eval_cases.json`, write-ups `demo/eval_case_1.md`, `demo/eval_case_2.md`): (1) clean run, refund 2,650; (2) E6 human-in-the-loop, resolved with `verified_continue`, refund 1,995.

## How to call it
```python
from src.agents import extraction
update = extraction.run(state)   # state["uploads"] = [{"doc_id":"w2_1","form":"W-2","source_file":"demo/w2_image_1.jpg"}]
# -> {"documents": [ExtractedDocument-shaped dict, ...]}   (only the `documents` field, per P1's contract)
```
CLI check: `python -m src.agents.extraction demo/w2_image_1.jpg w2_1`

Example output (abridged): `{"doc_id":"w2_1","form":"W-2","boxes":{"1":31250,"2":3400,"3":31250,"4":1937.5,"5":31250,"6":453.13,"a":"***-**-4567"},"confidence":{"1":0.96,...},"unverified":[],"flags":["extracted_by=w2-extraction-agent/1.0 ...; method=ocr; extracted_at=...; source_sha256=..."]}`

Provenance: P1's `ExtractedDocument` has no provenance field, so a summary line goes in `flags` and per-field detail (box, source file, who/what read it, timestamp, confidence) in `runtime/extraction/<session>/<doc_id>.provenance.json` (override with `SILVERFILE_EXTRACTION_DIR`). Only `src/extraction/contract.py` knows P1's format; if P1 adds a `provenance` field it is filled automatically.

## Who needs what
- **P1 Kaiwen**: optional `provenance` field on `ExtractedDocument`; import `src.security.*` instead of private SSN regexes (`validate_intake`).
- **P2 Jad**: amounts arrive as int when whole, float when cents; AI disclosure paragraph is in `docs/ai_log/christina.md`.
- **P3 Zimo**: use `ssn_request_allowed`/`check_ssn`; ask the taxpayer to confirm uncertain boxes via `user_inputs["<doc_id>.<box>"]`.
- **P5 Lluc / P6 Ziling**: escalate on document flags `ssn_not_test_range` and `unreadable_document:*`. P6: add `pillow`, `pytesseract`, `pypdfium2`, `numpy` to `requirements.txt` (versions below) and the `tesseract-ocr` apt package to the Dockerfile and CI.
- **P7 David**: W-2 upload UI passing `uploads: [{doc_id, form, source_file}]`; demo inputs are in `demo/`.

## Known limits
- Needs the Tesseract program installed; image tests skip without it.
- Only W-2s are read. Non-image uploads pass through flagged `structured_input_not_ocr`.
- Deliberately conservative: a few blurry boxes come back "uncertain" instead of read. Amounts without cents are never accepted.
- Not run here against real LangGraph (no PyPI access in my environment); covered by `tests/pipeline_sim.py` with the real agents. Run the CLI commands in the eval write-ups on your machine.
- Versions tested: pillow 12.3.0, pytesseract 0.3.13, pypdfium2 5.13.0, numpy 2.5.3, Tesseract 5.3.4.
