# Evaluation case 2: a human-in-the-loop event that staff resolve

The system stops for a person, a staff member resolves it, and the same session carries on to a finished
Form 1040-SR. All data is fake.

| | |
|---|---|
| Taxpayer | Single, born 5 March 1958, test SSN 902-34-5678, not blind, no dependents |
| Documents | One W-2: `demo/w2_image_2.jpg` (a slightly crooked, noisy scan) |
| W-2 amounts | Box 1 wages 24,800.00; box 2 federal tax withheld 2,100.00 |
| The trigger | The taxpayer could not say whose bank account the refund goes to (`refund.account_owner = unknown`) |
| Input file | `demo/eval_case_2_input.json` |
| Resolution file | `demo/eval_case_2_resolution.json` (for the command-line route) |
| Full definition | `evals/eval_cases.json` (id `eval_case_2`) |

## Why it stops

Elder financial abuse often travels through tax refunds. When a refund is headed to an account the taxpayer
cannot describe, SilverFile must notice and stop (assignment section 4.4, condition 6). It does not decide
whether anything is wrong. The Rules agent raises escalation **E6** ("Refund account is not in the taxpayer's name"),
the graph pauses at a LangGraph interrupt, and no tax lines are calculated until a person decides.

## How to resolve it: in the dashboard

1. `python run.py start --input demo/eval_case_2_input.json --thread-id eval-case-2` (it prints `pending_escalation: esc_0001`).
2. Copy `.env.example` to `.env`. It already holds the demo staff sign-in: ID `demo_staff`, passcode `silverfile-demo`.
3. `python -m streamlit run streamlit_app.py`, then open http://localhost:8501.
4. In the sidebar, sign in as `demo_staff` / `silverfile-demo`. (Signed out, the page is read-only.)
5. Under **HITL queue** find `eval-case-2` (code E6) and click **Open & resolve**.
6. Read the reason and what the taxpayer heard. Choose **Verified, continue**. (Nothing is preselected, so closing a case is always deliberate.)
7. Write a note, for example: *Phoned the taxpayer; the refund account is in his own name. Verified.*
8. Click **Resolve and resume**. The return moves to **Draft ready**.
9. Open it. **Escalations** shows E6 resolved with your staff ID, the time, your decision and note. **Draft form** shows the filled 1040-SR with **line 34 refund = 1,995**.

## How to resolve it: command line

```sh
python run.py start  --input demo/eval_case_2_input.json      --thread-id eval-case-2
python run.py status --thread-id eval-case-2                  # status: awaiting_human, pending_escalation: esc_0001
python run.py resume --thread-id eval-case-2 --input demo/eval_case_2_resolution.json
python run.py status --thread-id eval-case-2                  # status: draft_ready
```

The resolution file is the exact payload the dashboard sends: `{"escalation_id": "esc_0001", "option": "verified_continue", "note": "...", "resolved_by": "demo_staff"}`.

The other choices end differently: `close_session` closes the case with no return, and `flag_for_review` leaves it for a volunteer. Only `verified_continue` produces the finished return.

## Check the arithmetic by hand

24,800 income, minus 17,750 standard deduction (15,750 + 2,000 for 65 or older) and 6,000 senior deduction, leaves 1,050. Tax at 10% is 105. Withholding of 2,100 minus 105 gives a 1,995 refund.
