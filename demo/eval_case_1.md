# Evaluation case 1: clean minimal run

Everything works, nobody has to step in, and a filled-in Form 1040-SR comes out. All data is fake.

| | |
|---|---|
| Taxpayer | Single, born 1 June 1955, test SSN 901-23-4567, not blind, no dependents |
| Documents | One W-2: `demo/w2_image_1.jpg` (a picture, not typed data) |
| W-2 amounts | Box 1 wages 31,250.00; box 2 federal tax withheld 3,400.00 (boxes 3 to 6 are read too) |
| Input file | `demo/eval_case_1_input.json` |
| Full definition | `evals/eval_cases.json` (id `eval_case_1`) |

## Run it

```sh
python run.py start --input demo/eval_case_1_input.json --thread-id eval-case-1
python run.py status --thread-id eval-case-1          # status: draft_ready
python -m streamlit run streamlit_app.py              # http://localhost:8501, open eval-case-1
```

Needs the Tesseract OCR program installed (see README / `docs/P4_EXTRACTION_SECURITY.md`).

## What you should see

1. **Extraction** reads the W-2 picture: boxes 1 to 6 exactly as printed, nothing flagged uncertain, SSN shown only as `***-**-4567`.
2. **No escalation.** The status goes straight through to `draft_ready`; Review passes on the first attempt.
3. **The form.** Draft form tab: line 1a = 31,250, 12e = 17,750, 13b = 6,000, 15 = 7,500, 16 = 750, 25a = 3,400, **34 refund = 2,650**. Hover or click any amount to see where it came from (for 1a and 25a: W-2 `w2_1`, box 1 or 2, read by the W-2 extraction agent, with the time).

## Check the arithmetic by hand

31,250 income, minus a standard deduction of 17,750 (15,750 for single + 2,000 for being 65 or older) and a 6,000 senior deduction, leaves 7,500. Tax at 10% is 750. Withholding of 3,400 minus 750 gives a 2,650 refund.

## Make your own clean case

```sh
python data/generate_fixtures.py --custom my_w2.jpg --wages 41250.00 --withheld 3300.00 --ssn 900-11-2222 --name "Sam Placeholder"
```

Copy `demo/eval_case_1_input.json`, change `source_file` to `my_w2.jpg` and the SSN to match, and run it the same way.
