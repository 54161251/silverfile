# Implementation Backlog

All items are initially unassigned and incomplete. Add an owner and create an issue when work begins.

## Milestone 1 — Agree on interfaces
- [ ] Fill in TEAM.md and assign reviewers.
- [ ] Locate supplied tax_math tools and reference corpus; resolve open questions.
- [ ] Define state, typed document records, provenance, and agent return contracts.
- [ ] Agree on dependency versions and local setup.

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
