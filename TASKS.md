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

## Milestone 2 — One complete clean case
- [ ] Implement intake, saved sessions, and fake-SSN validation.
- [ ] Implement extraction from a synthetic W-2 image.
- [ ] Implement cited eligibility and scope checks.
- [ ] Implement required calculations through deterministic MCP tools.
- [ ] Generate a populated draft 1040-SR and inspectable provenance.
- [ ] Implement an independent audit agent and conditional orchestration.
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
