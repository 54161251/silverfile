# AI use log: Jad (P2)

Tool: Claude (Sonnet 5.5, Claude Code session). Scope: P2 workstream only.

## What AI did
- Wrote the first drafts of `tax_math.py`, `mcp_server.py`, `computation.py`, the unit tests, the seven golden returns and `docs/P2_COMPUTATION.md`.
- Looked up 2025 tax parameters (two independent web sources, plus the IRS Social Security worksheet).
- Reconstructed `src/state.py` from the repo's web view to test against the Provenance contract.

## What I (Jad) must still do
- Re-derive each golden return myself (R12). Claude's AI re-derivation is recorded under "Verification record" below; a human re-derivation has not been done.
- Read every file before committing; run the tests on my own machine.

## Mistakes found in AI output (keep this honest)
1. Golden g05 first assumed a 2,000 additional-standard-deduction amount for MFS. The IRS amount for married filing separately is 1,600. The unit test against an independent table caught it; the tools were right, the expectation was wrong.
2. Golden g05 gave an MFS taxpayer a senior-deduction qualifier, and the tool refused (raised an error). Rule C12 says MFS simply gets 0, so refusing was my own invention and could have blocked a valid return. Found by re-reading the rules doc. The tool now returns 0 for MFS and g05 keeps the qualifier to test it.
3. A hand-computed Social Security expectation (schedule-1 line 10 test) used the wrong provisional income (34,200 instead of 32,200). The oracle comparison in the same test caught it.
4. The first test set did not exercise Schedule 1 lines 8 and 10. A mutation check (removing line 8 from provisional income) passed all tests, so tests were added.
5. Test names did not cite rule IDs as R13 requires; renamed (test_<ID>_...).
6. The senior deduction was rounded once at the end instead of rounding Schedule 1-A line 34 first. Found when checking the IRS form line by line (Oct 27); fixed.
7. `pip install` was blocked in the AI sandbox, so `pytest` and `langgraph` were never run there. `mcp==2.3.0` is the installed version, not a version resolved from PyPI.

## Verification record
Done by Claude (AI) on 2026-10-27, not by a human re-derivation. The team may decide whether this satisfies R12.

| What | Re-derived by | Date | Match? |
|---|---|---|---|
| g01, g02, g05 line 6b; g03 line 13b | Claude: literal Pub. 915 Worksheet 1 and Schedule 1-A lines, separate code, not the project's tools | 2026-10-27 | Yes |
| g01-g06, all lines | Claude: Excel workbook with live formulas (`silverfile_golden_check.xlsx`) | 2026-10-27 | Yes, 0 differences |
| Parameters (brackets, standard deduction, add-ons, senior deduction, Social Security) | Claude: checked against Rev. Proc. 2024-40, Rev. Proc. 2025-32, Schedule 1-A (2025), Pub. 915 | 2026-10-27 | Yes |
| Human re-derivation by a team member | not done | | |

Finding from this check: Schedule 1-A rounds line 34 as its own line, so `senior_deduction` was changed to round it first (A23). Before the change a single filer at AGI 75,025 got 5,999; the form gives 5,998. No golden was affected.
