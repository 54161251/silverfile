# P6: Review / Audit agent

Owner: P6 (Ziling). Files: `src/agents/review.py`, `tests/test_review.py`.

## What it does
`review.run(state)` tries to prove the draft wrong before staff see it. It never edits the return.
It writes only `review_verdict` (`pass` or `revise`) and `review_findings`. The orchestrator sends the
draft back to `review_findings[0]["target_agent"]` and stops the loop after 3 revisions (E9) or a
repeated handoff (E10).

Review does no arithmetic. Every total it rechecks comes from the same MCP tools Computation uses,
called with Review's own reading of the documents and lines.

Each finding: `check`, `target_agent`, `reason`, and `line` / `evidence` when known. Findings are
sorted extraction, intake, rules, computation, so the most upstream fix is routed first.

## Checks
| Group | ID | What fails | Sent to |
|---|---|---|---|
| Provenance | P1 | Required line missing, or no lines at all | computation |
| | P2 | Malformed record, or a negative value where none is allowed | computation |
| | P3 | Computed line without tool/inputs/formula; direct input without who/when; default zero not 0 | computation |
| | P4 | Source value no longer matches the document box or the taxpayer's entry | computation |
| | P5 | A total (9, 11a, 12e, 13b, 14, 15, 16, 18, 22, 24, 25d, 33, 34, 37) not made by its tool | computation |
| | P6 | A line used an older value of another line (stale chain) | computation |
| | P7 | Box confidence below 0.8 but not marked unverified | extraction |
| Totals | T1 | Derived line differs from an independent tool call | computation |
| | T2 | Document lines (1a, 2a, 2b, 3a, 3b, 6a, 25a, 25b, 4a+5a) differ from the documents | computation |
| Rules | R1, R2 | Status not validated; nobody born before 2 Jan 1961 | rules |
| | R3, R4 | 65+ flags or senior-deduction people do not match birth dates | rules |
| | R5 | Line 12d box count differs from an independent count | rules / computation |
| | R6 | Chart does not apply (dependent, dual-status alien, MFS spouse itemizes) without E7 | rules |
| | R7 | 4b > 4a, 5b > 5a, 3a > 3b (documents), 6b > 6a (computation) | extraction / computation |
| | R8 | Line 7 or 13a has a value (out of scope) | rules |
| | R9 | Both line 34 and line 37 are above 0 | computation |
| Scope | S1, S2 | Not in scope; an escalation still open | rules |
| | S3-S7 | Out-of-scope form, 1099-R box 2b, 1099-R code not 7, 1099-DIV box 2a, intake out-of-scope item, without a resolved escalation | rules |
| | S8 | Intake flag (advice, third party, refund account, pressure, contradiction, uncertainty) without its escalation | rules |
| | S9 | An SSN that is not 900-series | intake |

Review cannot raise escalations itself (only Rules and the orchestrator write `escalations`), so
anything that needs a person goes back to Rules, which raises it.

## Run
```
python -m src.agents.review tests/golden/g01_single_ss_50pct.json
python -m pytest tests/test_review.py -q
```

## Notes for other workstreams
- P2 / P4: goldens g02-g04 have 1099-R forms without box `"7"`. Rules escalates a missing code as
  E1, and so does Review (S5). The tests add `"7": "7"`; the fixtures should include it.
- P4: the 0.8 confidence threshold (P7) is my assumption. Tell me the real one.
- Line 4b is skipped in the stale-chain check (P6) because its minuend is the box 2a total labelled line 4a.
