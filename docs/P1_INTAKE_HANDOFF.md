# P1 / P3 / P7 interactive Intake contract (October 25)

The demo registry and production loader use P3's `run_interactive(state)`. The legacy
`run(state)`/`latest_answer` helper is not the graph entry point. P3's commits are preserved.

1. Intake asks exactly one question with `interrupt({"type": "intake", "question": text,
   "fields": ["intake.taxpayer.birth_date"]})`. All field paths include their state root.
2. The UI reads the pending snapshot task's interrupt value and displays `question`.
3. It calls `sessions.resume(thread_id, {"answer": text})` on the same thread/database.
4. Intake records the parsed answer and returns the next full-path `open_questions`
   list, or `[]` when its current questionnaire is finished. No raw answer field is added
   to persistent GraphState. LangGraph's checkpointer retains its resume history.
5. With questions remaining, Orchestrator re-enters Intake. New flags go to Rules first,
   so uncertainty/advice/exploitation is not deferred until the whole questionnaire ends.
   After Rules, pending questions or eligibility.missing send control back to Intake.
6. Existing open STOP/GATE escalations always take priority and use staff resolution,
   which is a different interrupt payload from taxpayer question/answer.

## Progress and loop protection

P1 tracks hashes of accepted structured intake answers, user-input values, extracted
document boxes, and completed staff resolutions. New semantic data resets the stalled
handoff window. Previously seen answer snapshots do not reset it, preventing A/B answer
oscillations from running forever. Changing question text, queues, flags, summaries,
derived lines, or provenance timestamps alone is not accepted-answer progress.

The same directed pair three times in ten stalled handoffs still raises E10. The 80-step
fallback now counts handoffs without progress; total_handoffs remains a trace metric.
E9's maximum of three review revisions is unchanged. Graph bookkeeping is owned by P1;
agents must not return progress fields. No extra answer copies are stored by the guard.

## Verified scenarios and remaining P3 work

Tests cover the actual five-question P3 Intake in the complete graph, question order,
full fields, persisted reopen after each answer, 90 progressing turns, discarded answers,
answer oscillation, and prompt/timestamp churn. Rules is not called prematurely for a
normal questionnaire, but an uncertainty flag interrupts for staff promptly.

P3 currently asks filing status, birth date, blindness, dual-status alien and dependent
eligibility only. SSNs, spouse/dependent details, document inventory, direct amounts,
and arbitrary Rules/Computation missing paths are not yet implemented by that question
plan. The integration test preloads a synthetic SSN; it does not claim full tax intake.
P3 must extend question selection to eligibility.missing and calculation open_questions.
P7 still needs the taxpayer page consuming the question/answer contract above.
