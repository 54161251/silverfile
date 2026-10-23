# AI use log: Jad (P2)

Tool: Claude (Sonnet 5.5, Claude Code session). Scope: P2 workstream only.

## What AI did
- Wrote the first drafts of `tax_math.py`, `mcp_server.py`, `computation.py`, the unit tests, the seven golden returns and `docs/P2_COMPUTATION.md`.
- Looked up 2025 tax parameters (two independent web sources, plus the IRS Social Security worksheet).
- Reconstructed `src/state.py` from the repo's web view to test against the Provenance contract.

## What I (Jad) must do and have not yet recorded here
- Re-derive each golden return in an independent spreadsheet (R12) and record the result below.
- Read every file before committing; run the tests on my own machine.

## Mistakes found in AI output (keep this honest)
1. Golden g05 first assumed a 2,000 additional-standard-deduction amount for MFS. The IRS amount for married filing separately is 1,600. The unit test against an independent table caught it; the tools were right, the expectation was wrong.
2. Golden g05 gave an MFS taxpayer a senior-deduction qualifier, and the tool refused (raised an error). Rule C12 says MFS simply gets 0, so refusing was my own invention and could have blocked a valid return. Found by re-reading the rules doc. The tool now returns 0 for MFS and g05 keeps the qualifier to test it.
3. A hand-computed Social Security expectation (schedule-1 line 10 test) used the wrong provisional income (34,200 instead of 32,200). The oracle comparison in the same test caught it.
4. The first test set did not exercise Schedule 1 lines 8 and 10. A mutation check (removing line 8 from provisional income) passed all tests, so tests were added.
5. Test names did not cite rule IDs as R13 requires; renamed (test_<ID>_...).
6. `pip install` was blocked in the AI sandbox, so `pytest` and `langgraph` were never run there. `mcp==2.3.0` is the installed version, not a version resolved from PyPI.

## Verification record (fill in)
| Golden | Spreadsheet total re-derived by | Date | Match? |
|---|---|---|---|
| g01 ... g06 | | | |
