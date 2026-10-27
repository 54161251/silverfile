# Implementation Backlog

Implementation is still pending. Owners follow TEAM.md and the team's Google Doc:

| Owner | Workstream |
|---|---|
| P1 Kaiwen | Contracts, orchestration, persistence, routing, merging, loop protection |
| P2 Jad | MCP calculations, golden returns, report, AI disclosure |
| P3 Zimo | Intake, memory, accessibility, context metrics |
| P4 Christina | Extraction, security, fixtures, demo inputs |
| P5 Lluc | Eligibility, cited rules, escalation decisions and tests |
| P6 Ziling | Audit, QA, CI, Docker, grader simulation |
| P7 David | Dashboard, human-resolution UI, form/provenance display, video |

## Milestone 1 — Agree on interfaces
- [x] Record all seven named workstreams in TEAM.md.
- [ ] Collect GitHub usernames and agree on reviewers.
- [ ] Confirm instructor approval of seven-person team size and P7's graded focus area.
- [ ] Locate supplied tax_math tools and reference corpus; resolve open questions.
- [ ] Define state, typed document records, provenance, and agent return contracts.
- [ ] Agree on dependency versions and local setup.

P1 update: pinned runtime dependencies, five shared models, orchestration, parallel
aggregation, SQLite resume, validated staff interrupts, loop guards and their local tests
are implemented. The offline skeleton is runnable. Full integration, Python 3.11/CI,
Docker verification, branch protection and supplied-course-file discovery remain pending.
See docs/IMPLEMENTATION_NOTES.md; unchecked application milestones below remain incomplete.

P2 update (Oct 23): tax_math functions, the silverfile-tax-math MCP server, the Computation agent (all 41 lines with provenance), seven golden returns and their tests are implemented (src/tools/, src/agents/computation.py, tests/). Interface and open agreements with P3, P4 and P5 are in docs/P2_COMPUTATION.md. Oct 27: goldens g02-g04 now carry 1099-R code 7 and run in CI; parameters and goldens checked against IRS sources by Claude (AI, see docs/ai_log/jad.md; no human re-derivation); senior-deduction rounding follows Schedule 1-A line 34. Still open for P2: report paragraph (R21) and the final report and AI disclosure (R19).

P7 update (Oct 24): Streamlit staff dashboard (`streamlit run streamlit_app.py`): returns list, HITL
queue, return detail, sign-in, and resolve buttons wired to `Sessions.resume`. Draft 1040-SR as HTML with
hover and click provenance, plus the filled official IRS PDF. See docs/P7_DASHBOARD.md. Still open for P7:
demo video, and showing real sessions' lines once Computation runs in the graph.

P6 update (Oct 24): Review agent (`src/agents/review.py`) runs provenance, totals, rules and scope
checks, recomputing totals through the MCP tools, and sends findings back by target agent. 20 tests in
`tests/test_review.py`; details in docs/P6_REVIEW.md. CI (`.github/workflows/ci.yml`) runs the full suite
and reviews goldens g01, g05, g06 on every push and PR. Docker: `docker compose up --build`, dashboard at
localhost:8501 with two demo sessions, verified on macOS. Still open for P6: README Docker section,
goldens g02-g04 need 1099-R box 7 (P2/P4), grader simulation once Intake and Extraction land.

## Milestone 2 — One complete clean case
- [ ] Implement intake, saved sessions, and fake-SSN validation.
- [ ] Implement extraction from a synthetic W-2 image.
- [ ] Implement cited eligibility and scope checks.
- [x] Implement required calculations through deterministic MCP tools.
- [ ] Generate a populated draft 1040-SR and inspectable provenance.
- [x] Implement an independent audit agent and conditional orchestration.
- [ ] Provide a basic employee dashboard.

## Milestone 3 — Robustness and evidence
- [ ] Add real parallel extraction and a reducer; test merge-order behavior.
- [ ] Bound review retries and test a pathological handoff cycle.
- [ ] Cover all required human-escalation conditions with LangGraph interrupts.
- [ ] Demonstrate human resolution and resume to a completed draft.
- [ ] Demonstrate at least four accessibility/dignity choices.
- [ ] Verify remaining required document types and tax-form fields.
- [ ] Measure real input tokens with context strategy on/off; document results.
- [ ] Test new inputs beyond the prepared examples.

## Milestone 4 — Submission package
- [ ] Complete both demo scenarios and synthetic documents.
- [ ] Verify setup on another teammate's machine.
- [ ] Add sanitized traces, implementation notes, contribution table, and AI disclosure.
- [ ] Record a 5–10 minute demo.
- [ ] Confirm GitHub/Canvas submission method and repository access for graders.

## Optional stretch work
- [ ] Resolve HITL events directly in a neat dashboard (+15).
- [ ] Produce the specified five-page report (+10).
- [ ] Provide a verified Docker container and instructions (+5).
