# Workflow diagram

Rebuild with `python scripts/render_workflow_diagram.py` (Pillow required).

`graph.png` is a conceptual view of the production workflow. The README also contains
a Mermaid version. The executable topology is in `src/graph.py`; routing decisions are
in `src/orchestration.py`.

- A session starts at the Orchestrator, which initially selects Intake.
- Intake, Rules, Computation and Review return their results to the Orchestrator.
- The Orchestrator can return to Intake for another question or missing information.
- Document workers run in parallel and their outputs aggregate before control returns.
- Staff resolution pauses and resumes the same checkpointed session, then routing continues.
- The Orchestrator marks a return draft-ready after Review passes. The routing scaffold
  (`--demo`) instead ends as `scaffold_complete` without calculating a return.
- Review allows three revisions. The stalled-handoff guard checks three repeats of a
  directed pair within ten stalled handoffs, with an 80-handoff no-progress fallback.

The overview groups worker/dispatch details for readability; it is not a generated
state-machine trace. Image editing assistance is recorded in `docs/ai_log/kaiwen.md`.
