# Implementation Backlog

Owners follow TEAM.md and the team's Google Doc. Current completion status and remaining work are recorded below:

| Owner | Workstream |
|---|---|
| P1 Kaiwen | Contracts, orchestration, persistence, routing, merging, loop protection |
| P2 Jad | MCP calculations, golden returns, report, AI disclosure |
| P3 Zimo | Intake, memory, accessibility, context metrics |
| P4 Christina | Extraction, security, fixtures, demo inputs |
| P5 Lluc | Eligibility, cited rules, escalation decisions and tests |
| P6 Ziling | Audit, QA, CI, Docker, grader simulation |
| P7 David | Dashboard, human-resolution UI, form/provenance display, video |

## Status audit — October 30, 2026

Updated against main `1a957a2`. Checkboxes below distinguish committed implementation
and recorded evidence from final submission sign-off. Historical owner updates are in
Git history and linked workstream notes.

### Implemented and recorded
- [x] Shared state, validated agent updates, conditional orchestration and parallel extraction reducer.
- [x] SQLite checkpoints, taxpayer interrupts and validated staff resume.
- [x] Review revision limit and progress-aware stalled-handoff guard.
- [x] Expanded Intake, test-SSN checks, spouse/dependent paths, summaries and direct-entry questions for lines 8, 10, 17, 19, 20, 23 and 26.
- [x] Tesseract W-2 image/PDF extraction, masking, synthetic fixtures and ten-document one-household batch.
- [x] Rules policy citations and document-quality escalation checks.
- [x] MCP Computation, staff-entered document-box overrides and tool-backed income summation/direct-input rounding.
- [x] Review agent, golden fixtures with 1099-R code 7, and CI review of g01–g06.
- [x] Taxpayer W-2 upload page, staff dashboard, resolution UI and HTML/PDF provenance output.
- [x] Docker configuration and owner-recorded Docker evaluation runs.
- [x] Sanitized traces for both eval cases and recorded tests using new inputs: [grader simulation](docs/P6_GRADER_SIM.md).
- [x] Actual API input-token table with both strategies: [metrics](docs/metrics.md).
- [x] All seven individual AI logs are present; combined disclosure exists, with remaining review items below.

### Submission priorities
1. [x] **P3/P1: repair Intake risk-flag handoff.** PRs #49 and #51 return advice, third-party, out-of-scope and contradiction flags to Rules before another taxpayer question. Third-party/advice/out-of-scope paths were graph-tested during review; final-revision verification remains below.
2. [ ] **P6/all owners: verify the final revision.** Run both production image cases, staff resume after a restart, and a new grader-style input. Check displayed return lines and provenance. Record environment, exact revision and results.
3. [ ] **P1/P4/P2: define corrected-document replacement.** Extract-once handling is present, but it does not replace superseded records or prevent double counting when corrections get new IDs.
4. [ ] **P2: final report review and independent human golden review.** The updated `Extra Credit Report SilverFile.pdf` was exported from Report SilverFile v2 on October 31 after the user's edits. The Intake coverage, P3 log/metrics, P6 evidence and recorded test/token results have been reconciled. Check the final format and applicable report-length requirement. The IRS-source/spreadsheet check was AI-assisted; no human re-derivation is recorded. Retain the qualified-dividend limitation.
5. [ ] **P7: deliver and link the 5–10 minute video.** Confirm the final demo shows the complete production workflow and accessibility choices.
6. [ ] **All owners: finish personal code review and AI-log cleanup.** P3's model/date entries and October 30 risk-handoff record are supplied in PR #55; remaining personal review must be recorded by its author.
7. [ ] **P1: confirm grader access and submission.** Repository is private. Confirm access, final report/video locations, Canvas upload requirements, deadline and seven-person/P7 approval with the instructor.

P2 records a fresh-clone setup check on one machine on October 30; a second-person
setup check is still required.

### Verification limits

Latest-main CI was successful at audit time. A fresh Windows Python 3.13 run against
`117ce39` passed 399 tests and 610 subtests, with 20 OCR-dependent skips because Tesseract
is absent on this host. CI targets Python 3.11 and installs Tesseract. This documentation
change does not claim a new OCR, Docker or paid-model measurement run.

The UI implements multiple accessibility choices; demonstrate them in the final video.
Current traces and grader-simulation notes are useful evidence, but do not establish
that every recent code change has been covered by a final end-to-end run.

### Administrative questions

See [open questions](docs/OPEN_QUESTIONS.md) for supplied course assets, report length,
submission method, deadline updates and team-size approval. Mark these complete only
with a recorded answer; repository code is not evidence of instructor approval.

### Optional stretch delivery
- [x] Staff dashboard resolution functionality is implemented; final demonstration pending.
- [ ] Verify report length and final content for stretch credit; the uploaded seven-page PDF is present and linked from README.
- [ ] Rerun Docker from a fresh setup on the final revision and retain the result if claiming container stretch credit.
