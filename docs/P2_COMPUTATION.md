# P2: Computation agent, tax-math MCP server, golden returns

Owner: P2 (Jad). Files: `src/tools/tax_math.py`, `src/tools/mcp_server.py`, `src/agents/computation.py`, `tests/`.

## What it does
`computation.run(state)` fills every derived line of the 1040-SR draft. All arithmetic is done by
MCP tool calls to `silverfile-tax-math` (same server `python -m src.tools.mcp_server` runs over stdio;
the agent calls it in-process). Each line carries a `Provenance` record (kind, formula, inputs, sources,
tool name/version/tax year, citation, timestamp).

**Writes only** `lines` and `open_questions` (R10).
Success: `{"lines": {41 lines}, "open_questions": []}`.
Blocked: `{"lines": {}, "open_questions": ["<state path>: <reason>", ...]}`. Never partial. The orchestrator sends
a non-empty `open_questions` back to Intake; repeated blocking ends at the loop guard (E10).

## Tools (MCP)
| Tool | Used for |
|---|---|
| `sum_amounts(items)` | 1a, 1z, 2a-6a, 9, 14, 18, 21, 24, 25a-d, 32, 33 |
| `subtract(...)` | 4b (QCD), 11a, 15, 22, 34, 37 |
| `count_12d_boxes(...)` | 12d (cross-checked against Rules' `box_count_12d`) |
| `standard_deduction(status, boxes)` | 12e |
| `senior_deduction(status, agi, qualifiers)` | 13b |
| `income_tax(status, taxable_income)` | 16 (rate schedule, not Tax Table; A14) |
| `taxable_social_security(...)` | 6b (IRS worksheet; A17) |

Rounding: `Decimal`, half-up, once per tool call (A23). Python `round()` is never used. Where rounding changed the
value, the formula text shows the unrounded figure (e.g. `[2974.5 before rounding]`).

## Dependency order (why lines are computed in this order)
document + direct lines -> 6b (needs every other income line and line 10) -> 9 -> 11a (AGI) -> 12d, 12e -> 13b (needs AGI)
-> 14 -> 15 -> 16 -> 18 -> 21, 22 -> 24 -> 25a-d -> 32, 33 -> 34 / 37.

## 2025 parameters (verified against two independent sources; re-check against the IRS instructions before demo)
- Standard deduction: 15,750 single/MFS; 31,500 MFJ/QSS; 23,625 HOH. Add 2,000 per 12d box if single or HOH, else 1,600.
- Senior deduction (Schedule 1-A): 6,000 per qualifying person, minus 6% of AGI over 75,000 (150,000 MFJ), per person, floor 0. The 6% reduction (line 34) is rounded to whole dollars first, as the form does line by line (A23).
- Brackets: Rev. Proc. 2024-40 (QSS uses the joint schedule).
- Social Security: base 25,000/32,000 (MFJ), widths 9,000/12,000, 85% cap.

## Input conventions (what Computation reads)
| Source | Field | Notes |
|---|---|---|
| Rules (P5) | `filing_status_validated`, `scope.in_scope`, `box_count_12d`, `eligibility.taxpayer_65_or_older`, `spouse_65_or_older`, `senior_deduction_qualifiers` | Missing -> blocked with the state path named |
| Intake (P3) | `intake.taxpayer.blind`, `intake.spouse.blind`, `intake.mfs_lived_with_spouse` | |
| Intake (P3) | `user_inputs[line]` for 8, 10, 17, 19, 20, 23, 25c, 26, 21*, 32*, 27-31*, 1b-1h* (* optional) | number, or a full provenance record (audit fields kept) |
| Extraction (P4) | `documents[].boxes` | W-2: 1, 2. 1099-INT: 1, 3, 4, 8. 1099-DIV: 1a, 1b, 4. 1099-R: 1, 2a, 4, `ira_sep_simple`, `qcd_amount`. SSA-1099: 5, 6 |
| Intake/Extraction/Staff | `user_inputs["<doc_id>.<box>"]` | Replaces the printed box whenever present (taxpayer confirmation or staff resolution); the source records who entered it. An `unverified` box with no entry blocks. 1099-R box 2a is also blocked while `2b_not_determined` is set and no amount was entered (E3) |

Absent direct lines default to 0 with `kind="default_zero"` (visible on the dashboard). To force Intake to ask instead,
set `REQUIRED_DIRECT_LINES = ("10", "26")` at the top of `computation.py`.

## Handoffs / agreements needed from other workstreams
1. **P5 Rules:** `box_count_12d` must equal age + blindness boxes; a mismatch blocks. `senior_deduction_qualifiers` may list an MFS taxpayer: `senior_deduction` returns 0 for MFS regardless (C12 / A12).
2. **P4 Extraction:** box keys `ira_sep_simple` (bool) and `qcd_amount` on 1099-R are conventions I chose. Agree or tell me the real keys. Superseded/corrected documents must be removed or flagged before Computation, since all documents in `state["documents"]` are summed.
3. **P3 Intake:** ask for Schedule 1 total (8), adjustments (10), Schedule 2 (17, 23), credits (19, 20), estimated payments (26) explicitly, entering 0 when none. Confirmations of low-confidence boxes go in `user_inputs["<doc_id>.<box>"]`.
4. **P1 Orchestrator:** no change needed. Computation returns `open_questions: []` on success, which is what routes to review.
5. **P6 Review:** every computed line has `tool`, `inputs`, `formula`; the formula text for rounded values includes the unrounded figure.

## Known limits (stated, not hidden)
- Line 16 uses the rate schedule (A14). No qualified-dividend/capital-gain worksheet, so the figure can differ from commercial software.
- Lines 7 and 13a are always 0 (out of scope, A18). Dividend capital-gain distributions must be escalated by Rules.
- MFS who lived with spouse: tool refuses (A17); surfaces as an open question rather than an escalation. Rules should catch it first.
- Non-IRA 1099-R is assumed to be a pension/annuity (line 5). IRA flag drives line 4.
- Senior deduction uses AGI as MAGI (exact unless Puerto Rico or foreign-income exclusions exist, which are out of scope).
- Extraction reads W-2 images only. 1099 and SSA-1099 values, and the 1099-R keys `ira_sep_simple` and `qcd_amount`, are supported through structured input and the goldens, not through OCR.

## Verification status
- Unit tests (`unittest`, pytest-compatible). Golden numbers were derived by AI and cross-checked against `tests/oracle.py`, an independent reimplementation.
- R12 (Oct 27): Claude (AI, not a human re-derivation) checked the parameters against Rev. Proc. 2024-40, Rev. Proc. 2025-32, Schedule 1-A and Pub. 915, recomputed g01, g02, g05 line 6b and g03 line 13b from the worksheet lines, and recomputed g01-g06 in an Excel workbook with 0 differences. See docs/ai_log/jad.md.
- Mutation checks: changing a bracket rate fails 59 tests; dropping line 8 from the SS inputs fails the schedule-1 tests.
- Since written, Computation runs in the real graph with the real `src/state.py`, Rules and Review: both evaluation cases (`demo/eval_case_1.md`, `demo/eval_case_2.md`) reach `draft_ready` with the expected line 34 refunds (2,650 and 1,995), and an MFJ two-senior case matched a hand calculation (checked 2026-10-30). The golden unit tests themselves still use the golden state files, not the graph.

## Run
```
pip install -r requirements.txt            # includes mcp
python -m unittest discover -s tests -t .  # or: pytest
python -m src.agents.computation tests/golden/g01_single_ss_50pct.json
python -m src.tools.mcp_server             # stdio MCP server
```
