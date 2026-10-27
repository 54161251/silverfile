# P6: Grader simulation

Owner: P6 (Ziling). Inputs are in `evals/p6_grader_sim/`. All data is fake.

Rubric D asks graders to run eval_case_1, eval_case_2, and a clean run with data they make up.
This records what happened when we did the same.

## Results

| Run | Where | Result |
|---|---|---|
| eval_case_1 | Docker on macOS, Oct 26 | W-2 image read, `draft_ready`, review passed first round, line 34 refund 2,650 |
| eval_case_2 | Docker on macOS, Oct 26 | Stopped at E6, resumed with `demo/eval_case_2_resolution.json`, `draft_ready`, refund 1,995 |
| Made up, MFJ | Local, Oct 26 and 27 | Oct 26 stopped at E10. Oct 27 raises E8, resolved by staff, `draft_ready`, refund 1,741 (finding 1) |
| Made up, HOH owes | Local, Oct 26 and 27 | `draft_ready`, review passed, line 37 owed 383 |

Both eval refunds were also checked in the staff dashboard.

## Made-up cases

**MFJ** (`mfj_input.json`). Taxpayer born 1957, spouse born 1963 and blind. W-2 image with wages
48,900.00 and 4,150.00 withheld (scan style), SSA-1099 benefits 22,800, 1099-INT interest 640,
estimated payments 500.

Hand check: provisional income is 11,400 + 49,540 = 60,940, which is 28,940 over the 32,000 base.
Taxable Social Security is min(6,000 + 0.85 x 16,940, 0.85 x 22,800) = 19,380. Line 9 = 68,920.
12d = 2 (taxpayer 65+, spouse blind), so 12e = 31,500 + 2 x 1,600 = 34,700. Only the taxpayer is 65+,
so 13b = 6,000. Line 15 = 28,220. Tax = 10% x 23,850 + 12% x 4,370 = 2,909. Payments 4,650, refund 1,741.
The system matched every line.

**HOH owes** (`hoh_owes_input.json`). Born 1959. W-2 wages 41,250.00 with 900.00 withheld,
1099-DIV ordinary 3,200 and qualified 2,100.

Hand check: line 9 = 44,450, 12e = 23,625 + 2,000 = 25,625, 13b = 6,000, line 15 = 12,825,
tax = 10% x 12,825 = 1,283, owed 1,283 - 900 = 383. The system matched.

## Findings

1. **A made-up W-2 read with low confidence.** OCR read wages 48,900.00 correctly but with low
   confidence, so box 1 was marked unverified. On Oct 26 this looped computation, intake and rules
   until the loop guard raised E10. **Fixed on main by Oct 27:** Rules now raises E8 ("W-2 box 1 was
   not read confidently"). Rerun on Oct 27: staff resolved it with `enter_value`, override
   `user_inputs.w2_1.1 = 48900`, and the return finished `draft_ready` with refund 1,741 and review
   passing. A grader inventing W-2 numbers may see this E8 and can resolve it in the dashboard.
   `mfj_input_confirmed.json` skips it by supplying the confirmed value up front.
2. **Qualified dividends are taxed at ordinary rates.** In the HOH case, 2,100 of qualified
   dividends would be taxed at 0% on a real return, so the draft overstates tax by 210. This is the
   known limit A14 in docs/P2_COMPUTATION.md, not a new bug, but the report should say so.

## Run it

```sh
python run.py start --input evals/p6_grader_sim/mfj_input_confirmed.json --thread-id grader-mfj
python run.py start --input evals/p6_grader_sim/hoh_owes_input.json --thread-id grader-hoh
python run.py start --input evals/p6_grader_sim/mfj_input.json --thread-id grader-e8    # shows finding 1, resolve E8 in the dashboard
```

In Docker, prefix each with `docker compose exec silverfile` after rebuilding the image.

## Traces

`traces/eval_case_1.json` and `traces/eval_case_2.json` record every checkpoint of both eval runs: which
agent ran, where it went next, open escalations, the staff decision, and the final lines with their tool
and formula. Personal details are masked and raw intake answers are left out. Rebuild them with
`python traces/make_traces.py`.
