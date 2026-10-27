# AI log — Lluc (P5, Rules + escalation)

R19: tool used, task, what it got wrong, what I changed.

Tool for every entry: Claude Code (Claude Opus 5.5) in VS Code, working in my local clone.
Claude wrote the code and tests; I gave the tasks, read the results, opened the PRs and
passed on the reviewers' comments.

## 2026-10-23 — Rules agent

- **Task:** `data/policy.md`, `src/agents/rules.py` (deterministic Rules agent, E1–E8
  escalation records), `tests/test_decision_table.py` and `docs/p5_rules_interface.md`,
  written from the team's Assumptions & Working Rules doc before `state.py` existed.
- **Decision:** no LLM in Rules. Every decision maps to a fixed `policy.md` anchor, which is
  testable and avoids a model inventing citations (B4 allows an LLM for citations only).
- **What it got wrong (found by Kaiwen's review of PR #2):**
  1. An escalation marked "resolved" with an empty resolution was treated as cleared.
  2. An approval stayed valid after the underlying data changed (e.g. refund-account owner).
  3. A missing SSN silently removed senior-deduction eligibility instead of being reported
     as missing.
- **What changed (PR #3):** resolutions must name the staff member and a valid option;
  evidence carries a hash of the triggering value; missing or non-900 SSNs go to
  `eligibility.missing`. New tests were checked to fail on the old code.

## 2026-10-26 — integration testing and fixes across workstreams

The team asked me to work through the remaining-tasks list together. Claude ran every
escalation through the real graph (raise, resolve with the dashboard's payload, resume)
and with real OCR (Tesseract installed in an isolated conda folder). Each fix is on its own
branch with the workstream owner as co-author.

- **P5:** Rules escalates on Extraction flags (`ssn_not_test_range` → E7, unreadable
  document and unconfirmed low-confidence boxes → E8); "widowed/divorced/separated" now
  reaches E5 instead of a generic E8.
- **Found by testing, fixed:** extraction was skipped when a flag came before the
  documents were read (draft with $0 wages that Review passed); re-extracting a document
  crashed the graph; a preparer's E3 amount was ignored by Computation; Python arithmetic
  remained in Computation (R9); the batch had ten SSNs for one household.
- **Added:** the spec 4.5 context strategy and batch measurement, W-2 upload on the
  taxpayer page, dashboard field suggestion for document escalations, this disclosure.
- **What Claude got wrong this session:** an earlier status report said the SSN loop on
  `main` was fixed by PR #21 before checking (it was not; the fix was in the unmerged P3
  branch); a first test fixture lacked fields the progress tracker needs; a first
  token-growth test threshold was too strict for short documents; one set of edits was
  made on `main` before moving it to a branch (nothing was committed to `main`).
- **Not done by Claude:** actual API token counts (no key on this machine); the report;
  the demo video.
