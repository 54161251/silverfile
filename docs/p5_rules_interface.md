# Rules agent interface (P5) — proposal for P1, P3, P4, P6, P7

Status: proposal. Written before `state.py` exists. Field names below are what
`src/agents/rules.py` reads today; P1's `state.py` wins, and P5 will rename to match.

## What Rules reads

`intake` (written by Intake, P3):

| Field | Type | Used for |
|---|---|---|
| `filing_status` | `single` / `mfj` / `mfs` / `hoh` / `qss` | A21, E5 |
| `taxpayer.birth_date`, `spouse.birth_date` | ISO date | A3, A4, 12d, senior deduction |
| `taxpayer.blind`, `spouse.blind` | bool | 12d |
| `taxpayer.ssn`, `spouse.ssn` | 900-series string | senior deduction (A12) |
| `taxpayer.stated_age` (optional) | int | E2 age conflict |
| `spouse` | object or null | E5 (married status without spouse, and the reverse) |
| `spouse.date_of_death` | ISO date or null | E5 |
| `hoh_qualifying_person` | bool | E5 |
| `marital_status_unclear` | bool | E5 |
| `can_be_claimed_as_dependent` | bool | E7 |
| `dual_status_alien` | bool | E7 (**Intake needs this question**) |
| `mfs_spouse_itemizes`, `mfs_claim_spouse_boxes`, `mfs_lived_with_spouse` | bool | E7, E7, E1 |
| `ss_lump_sum_prior_year` | bool | E1 (A17) |
| `out_of_scope_items` | list of codes (`itemize`, `rental`, `tips`, ...) | E1 |
| `document_inventory` | list of form names the user said they have | E2 |
| `refund.method`, `refund.account_owner` | `direct_deposit`/`check`; `taxpayer`/`spouse`/`joint`/`other`/`unknown` | E6 (A22) |

`flags` (contract #4), `documents` (contract #5), `user_inputs` (line → value or
provenance record; read for lines 8, 10, 17, 20, 23, 31 to decide schedules) and
existing `escalations`.

Document box keys Rules needs (P4, please use these in fixtures): 1099-R `"7"`
(distribution code, string), `"2b_not_determined"` (bool) or the document flag
`taxable_amount_not_determined`; 1099-DIV `"2a"`.

## What Rules writes (B4 only)

- `eligibility`: `form_1040sr_eligible`, `taxpayer_65_or_older`, `spouse_65_or_older`,
  `senior_deduction_qualifiers` (list of `"taxpayer"`/`"spouse"` — Computation uses this
  for 13b), `missing` (intake fields Rules needs but doesn't have; the Orchestrator can
  route back to Intake).
- `filing_status_validated`: the status, or `null` while an E5/E7 status issue is open.
- `box_count_12d`: int.
- `schedules`: `schedule_1`, `schedule_1a`, `schedule_2`, `schedule_3` booleans.
- `scope`: `in_scope`, `out_of_scope_items`, `cleared_by_staff`.
- `escalations`: **new** records only (contract #2). The reducer must append or merge by `id`.
- `citations`: list of `{decision, citation}` with `policy.md#anchor`.

Rules is idempotent: re-running after a send-back doesn't duplicate an escalation, and
an escalation resolved with a continuing option no longer blocks scope.

- **What counts as resolved.** `status == "resolved"` **and** `resolution.resolved_by` is
  set **and** `resolution.option` is one of that E-code's options. Anything else (for
  example "resolved" with an empty resolution) is raised again as a new escalation.
  P1/P7: store the resume payload (contract #3) as the escalation's `resolution`.
- **Approvals are tied to the data.** Where the triggering value can change while still
  triggering (refund-account owner, birth dates, stated age, 1099-R code, 1099-DIV box
  2a), the evidence entry carries a short hash of the value, e.g.
  `intake.refund.account_owner@1a2b3c4d`. If the value changes after approval, the key no
  longer matches and Rules escalates again.
- **Missing inputs.** `eligibility.missing` lists anything Rules needs and doesn't have,
  including a missing or non-900-series SSN for the taxpayer, for the spouse (MFJ/MFS),
  and for each dependent's name, SSN and relationship. P1: route to Intake while it is
  non-empty.

## Gaps in the team doc — proposed fixes (needs P1 approval)

1. **Who writes escalation records.** E4/E8 say "raised by Intake" and E2 says "Rules or
   Review", but B2 lets Intake write only `flags` and B6 lets Review write only
   `review_findings`. Proposal: Rules is the only agent that writes `escalations` (except
   E9/E10, raised by the Orchestrator). Intake raises flags; Review reports a finding and
   sends back to Rules.
2. **Triggers with no E-code.** Proposal: MFS spouse 12d boxes (C10) → E7; MFS who lived
   with spouse and lump-sum Social Security (A17) → E1; 1099-R code other than 7 (A15) → E1;
   self-employment adjustment (A8) → E1; 1099-DIV box 2a > 0 (A18) → E1; any document form
   outside the five in-scope forms → E1.
3. **No intake question for dual-status alien** (E7). P3 to add one.
4. **E5 has no flag type for a spouse's death.** Rules reads `spouse.date_of_death` from
   intake instead.
5. **B4 "Reads" should include `flags`, `user_inputs` and `escalations`.**
6. **Refund to spouse's account on a non-joint return** is treated as E6. Confirm.
7. **Escalation `options` snake_case names** are in `rules.ESCALATION_CATALOG`, together with
   the sentence the user hears. P7's dashboard and P3's Intake should import them from
   there, not retype them.
