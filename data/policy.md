# SilverFile Policy Corpus (Tax Year 2025, Form 1040-SR)

Owner: P5 (Rules + escalation). This is the reference corpus the Eligibility & Rules
agent cites (B4). Every Rules decision carries a `policy.md#<anchor>` citation, and the
anchors below are stable: do not rename a heading without updating
`src/agents/rules.py` and telling P2 (provenance citations) and P7 (dashboard links).

Precedence: assignment spec, then the team's Assumptions & Working Rules doc, then this
file. If this file disagrees with either, this file is wrong. Where a case is not covered,
the conservative reading applies: escalate rather than compute.

SilverFile never files and never gives advice (A25). It prepares a draft plus an audit
record for a Kushim staff member.

## 1040-SR eligibility

- The return may use Form 1040-SR only if the taxpayer was born **before 2 January 1961**.
  Someone born on 1 January 1961 qualifies; someone born on 2 January 1961 does not.
  (Spec §3.2.1, A3.)
- On a joint return (MFJ), it is enough that **one** spouse meets the test.
- There is no income limit.
- If no one on the return qualifies, the session escalates as **E7** (wrong form).

## Age 65 test

- "65 or older" for line 12d and for the senior deduction uses the same birth-date test as
  1040-SR eligibility: born before 2 January 1961. (A4.)
- The full birth date is collected and used. A stated age is never used on its own; if a
  stated age conflicts with the birth date, see [Conflicting information](#conflicting-information).

## Blindness

- Blindness is a self-attested yes/no answer. No proof is requested. (A5.)

## Filing status

All five statuses are accepted at intake (Single, MFJ, MFS, HOH, QSS) and then checked
here. (A21, spec §4.4.5.) The following always escalate as **E5** (filing-status ambiguity):

- A spouse died in 2025 or earlier (MFJ vs QSS vs Single needs a human).
- Any claim of Qualifying Surviving Spouse (QSS).
- Head of Household with no qualifying person.
- Unclear marital status, including Single with spouse details. (MFJ or MFS with no
  spouse details yet is not ambiguous: Intake asks the spouse questions.)

## Line 12d box count

- One box each for: taxpayer 65+, taxpayer blind, spouse 65+, spouse blind. (C10.)
- Spouse boxes count **only on MFJ**.
- An MFS return claiming spouse boxes escalates as **E7** (correct data or close), because
  the exception that allows it is outside our scope.

## Standard deduction

- Standard deduction only; itemizing is out of scope. (A10.)
- Base: $15,750 Single/MFS, $31,500 MFJ/QSS, $23,625 HOH. Each 12d box adds $2,000
  (Single, HOH) or $1,600 (MFJ, MFS, QSS). (C11.) The Computation agent applies these
  amounts; Rules supplies only the box count.

## Standard deduction exclusions

The Standard Deduction Chart does not apply in these cases, and each escalates as **E7**:

- The taxpayer can be claimed as someone else's dependent. (A20.)
- The taxpayer is MFS and the spouse itemizes.
- The taxpayer was a dual-status alien.

## Senior deduction

Enhanced senior deduction, Schedule 1-A, carried to line 13b. (Spec §3.2.3, A11–A13.)

- A person qualifies if they pass the [Age 65 test](#age-65-test), have a valid SSN (a
  900-series test SSN counts as valid here), and the filing status is **not MFS** (D11).
- On MFJ, each spouse qualifies separately. On any other status only the taxpayer can
  qualify.
- Rules decides **who** qualifies. The Computation agent computes the amount and the
  phase-out (C12).
- Schedule 1-A covers only this deduction. Tips, overtime and car-loan interest claims are
  out of scope (E1).

## In-scope documents

Only these forms are in scope: W-2, 1099-INT, 1099-DIV, 1099-R, SSA-1099. (Spec §3.3.)
Any other form (for example 1099-NEC, 1099-B, 1099-K, 1099-MISC, Schedule K-1) escalates
as **E1**.

## Document checks

Extraction never guesses a value; these cases stop for a person instead (A19, D4):

- A W-2 whose SSN is outside the 900-999 test range (Extraction flag
  `ssn_not_test_range`) escalates as **E7**. SilverFile may hold only synthetic data
  (R15), so the document is not used; staff close the session or supply a corrected one.
- A document that could not be read at all (flag `unreadable_document:*`) escalates as
  **E8**.
- A box the return needs that was read with low confidence (listed in `unverified`) and
  not yet confirmed escalates as **E8**. Staff choose "Enter value" and enter the box as
  `user_inputs.<doc_id>.<box>`, which Computation uses with human-resolution provenance.
  Interim rule: D4 has Intake confirm these with the taxpayer, but Intake does not ask
  yet. Boxes the return does not use are not escalated.
- An unreadable SSN on a W-2 is not escalated: the SSN is not used on the return.

## Out of scope

These are not attempted. Each escalates as **E1** so a specialist can contact the client:
itemized deductions (Schedule A); self-employment or business income (Schedule C,
1099-NEC) and any self-employment adjustment; rental income (Schedule E); capital gains
requiring Schedule D; digital assets; foreign income or accounts; amended or prior-year
returns; state returns; tips, overtime or car-loan interest deductions. (Spec §3.3, A8,
A10, A11.)

## 1099-R distributions

- Only distribution code **7** is accepted. Any other code escalates as **E1**. (A15.)
- Box 2b "taxable amount not determined" checked always escalates as **E3**, whatever
  other information is available, because the Simplified Method and General Rule are
  outside our scope. (Spec §3.3.)
- IRA/SEP/SIMPLE box checked: line 4. Otherwise: line 5. (Computation applies this.)

## Social Security exclusions

Line 6b uses the supplied worksheet. These cases are outside the worksheet and escalate as
**E1** (A17):

- MFS taxpayers who lived with their spouse at any time in 2025.
- Lump-sum benefit payments for prior years.

## Dividends

- 1099-DIV capital-gain distributions (box 2a) greater than 0 escalate as **E1**, because
  line 7 is out of scope. (A18.)

## Schedules

- Schedules 1, 2 and 3: the user types the totals; they are recorded as direct user input.
  (A8.) Rules records which schedules apply so the draft and dashboard can show them.
- Schedule 1-A applies when at least one person qualifies for the
  [Senior deduction](#senior-deduction).

## Dependents

- Dependents are recorded with name, SSN and relationship only. No dependent credits are
  computed. (A20.)

## Refund account

- No bank routing or account numbers are collected. The draft records only the refund
  method and who owns the account. (A22.)
- A refund going to an account the taxpayer does not own or cannot describe is a possible
  exploitation signal: see [Exploitation and third-party pressure](#exploitation-and-third-party-pressure).

## No tax advice

- Requests for advice, planning or optimization ("Should I convert my IRA?", "Would we pay
  less filing separately?") are out of scope. The question is noted for a volunteer
  preparer and the session continues. This is **E4**, a GATE escalation (D12).

## Exploitation and third-party pressure

Elder financial abuse often travels through tax refunds. SilverFile does not adjudicate;
it notices and stops. Each of these escalates as **E6** (STOP):

- A refund routed to an account the taxpayer cannot describe or does not own.
- Someone else answering for the taxpayer without stated authority.
- Signs that the taxpayer is being told what to say.

Wording rules: the user hears only "I need a colleague to look at this before we
continue." The escalation reason is neutral and factual and never accuses anyone. Free-text
excerpts are not copied into the escalation record; it points at the flag ID instead.

## Conflicting information

- A user statement that conflicts with a document (for example "no pension" while a 1099-R
  is present, or a stated age that does not match the birth date) escalates as **E2**.
  Staff choose which value wins, with a note. (Spec §4.4.)

## Honest uncertainty

- If the user does not know an answer and the agent cannot resolve it, or the agent itself
  is unsure, the item is flagged for a volunteer. This is **E8**, a GATE escalation.

## Volunteered SSN

- An SSN volunteered where it was not requested is rejected, never echoed back and never
  stored. Only the `ssn_volunteered` flag is kept. No escalation is raised. (R17.)

## Escalation decision table

| Code | Trigger | Kind | Section |
|---|---|---|---|
| E1 | Out-of-scope item, document or 1099-R code | STOP | [Out of scope](#out-of-scope) |
| E2 | User statement conflicts with a document | STOP | [Conflicting information](#conflicting-information) |
| E3 | 1099-R box 2b checked | STOP | [1099-R distributions](#1099-r-distributions) |
| E4 | Request for advice | GATE | [No tax advice](#no-tax-advice) |
| E5 | Filing-status ambiguity | STOP | [Filing status](#filing-status) |
| E6 | Exploitation or third-party pressure | STOP | [Exploitation and third-party pressure](#exploitation-and-third-party-pressure) |
| E7 | 1040-SR ineligible, dependent, dual-status, MFS spouse itemizes, MFS spouse boxes; W-2 with a non-test SSN | STOP | [1040-SR eligibility](#1040-sr-eligibility), [Document checks](#document-checks) |
| E8 | Honest uncertainty; unreadable document or unconfirmed low-confidence box | GATE | [Honest uncertainty](#honest-uncertainty), [Document checks](#document-checks) |

E9 (review bound) and E10 (loop guard) are raised by the Orchestrator, not Rules.

Every escalation is resolved by a named Kushim staff member. A resolution never deletes
previously collected answers.
