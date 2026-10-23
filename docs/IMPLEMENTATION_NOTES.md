# P1 implementation and handoff

## Implemented now

- Five Pydantic contracts; agent field ownership enforced at adapter outputs (R8/R10).
- Rule-based orchestrator, conditional missing-input routing and review send-backs (B1).
- LangGraph Send fan-out, real concurrent workers, and deterministic aggregation.
- SQLite checkpointer with session IDs and reopen/resume support (A2).
- LangGraph interrupt for STOP and GATE; staff identity, allowed option, note and timestamp.
- Review limit: at most three revisions (E9). Repeated directed handoff pair: three
  occurrences in the last ten handoffs (E10). Total handoffs also limited to 80.
- Derived lines are invalidated after staff resolution before Rules and Computation rerun.
- Readable CLI summaries omit SSNs and raw intake data.

## Workstream integration

P2: src/agents/computation.py run(state) returns lines keyed by form line, each a
Provenance record. Use deterministic MCP tools. Return open_questions for missing inputs.
P3: src/agents/intake.py run(state) may use interrupt for taxpayer input. Return intake,
flags and open_questions; inspect eligibility.missing. Preserve prior answers yourself.
P4: src/agents/extraction.py receives uploads containing exactly one task. Return one
ExtractedDocument with that task's doc_id. Structured demo copying is not OCR.
P5: existing Rules module is used directly; escalation upserts preserve resolutions.
P6: src/agents/review.py returns review_verdict pass/revise and review_findings containing
target_agent and reason. Each audit reruns after correction. Add actual audit checks,
CI, golden-return evaluation and Docker verification.
P7: use open_sessions, start, snapshot and resume. Feed the exact ResumePayload and
authenticate staff before exposing resolution controls. Derive UI state from snapshots.

For a corrected extraction, use a new document ID; old evidence is retained. Document
replacement/supersession semantics still require P4/P2 agreement before real tax runs.
The code does not invent missing agent implementations: production startup fails until
all adapters exist. Demo completion has its own status, scaffold_complete, and no dollars.

## Verification and limitations

Local development uses Python 3.13 because it is the installed interpreter; the team
target is Python 3.11 and still needs that environment verified. Tests exercise actual
LangGraph concurrency, persisted restart, review/revise, and guard interrupts. A barrier
requires both extraction workers to be active at once, so a serial workflow cannot pass.
E9 integration test isolates the review limit by relaxing E10 only in that test; production
E10 can stop a repeated review pattern before E9. The first pytest attempt used an
unwritable sandbox temp location; using a workspace temp directory resolved it.
The current local suite passes 96 tests. Separate CLI processes also passed clean start,
HITL start, and resume using the same database. These are integration checks, not tax
accuracy evidence or a replacement for P2/P6 golden returns.

Docker executable exists but the engine is unavailable; no container run is claimed.
No GitHub CI configuration or branch protection was added by P1. All six teammates
already have collaborator access, and no classic protections or rulesets are configured.
The owner authorized collaborators to merge their own tested PRs without major issues;
CONTRIBUTING.md supersedes the old only-P1-merges policy. No shared API key,
spending cap, token metrics, LLM call or complete draft return is claimed. P4 must add
free-text PII masking; checkpoints are local synthetic-data storage, not a production
security boundary. Session API validates known SSN fields before checkpoint writes.

Course-supplied tax_math and corpus have not been located by this runtime work. P5's
policy.md is present; it is team-authored. D10 and the October 20 Q&A notes remain open.

## Architecture references

- https://docs.langchain.com/oss/python/langgraph/graph-api
- https://docs.langchain.com/oss/python/langgraph/interrupts
- https://docs.langchain.com/oss/python/langgraph/persistence
