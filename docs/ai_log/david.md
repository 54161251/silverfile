# AI use log: David (P7)

Tool: Claude (Opus 5.5) in a Claude session linked to my local clone. Scope: P7 workstream only.

## What AI did
- Read the assignment, the team's Assumptions & Working Rules doc and everything merged on `main`
  (P1 state, graph, memory, human; P2 computation; P5 rules), then asked me clarifying questions
  (staff sign-in strictness, how to show the form before integration, which pieces to build).
- Wrote the first drafts of `src/dashboard/` (store, auth, resolution, form_render, pdf_fill,
  previews, app), `streamlit_app.py`, `.streamlit/config.toml`, the four P7 test files and
  `docs/P7_DASHBOARD.md`.
- Downloaded the blank 2025 Form 1040-SR from irs.gov and mapped its fields by rendering each
  page with field names drawn on top.
- Ran the full test suite (Python 3.11 and 3.13) and drove the app in a headless browser
  to check the queue, sign-in, resolution, hover and click provenance, and the filled PDF.

## Decisions I made
- Build only on merged code; no edits to teammates' files.
- Staff ID + shared passcode from `.env` for sign-in.
- Show P2's golden returns as read-only samples until the full pipeline is merged.
- Build the filled IRS PDF stretch goal.

## Mistakes found in AI output (keep this honest)
1. The first PDF fill used full qualified field names it had guessed; several fields sit under extra
   parents (`YourSocial[0]`, `Table_Dependents[0]`), so filling failed. Replaced with a resolver that
   maps short names to the unique qualified name.
2. SSNs were masked as `XXX-XX-1234`, which is 11 characters; the form's SSN fields are 9-cell comb
   fields and pypdf truncated the value. Changed to `XXXXX1234`.
3. The IRS file also contains an XFA form. The first output kept it, so XFA-first viewers could
   show a blank form. The XFA copy is now removed and a test checks it.
4. The first DRAFT banner was a FreeText annotation that some renderers do not draw; replaced
   with page content.
5. The resolve panel preselected the first option, which for E6 is a closing option ("Flag for
   trained staff review"). Changed to no default so closing is always deliberate.
6. "Last activity" was cut off in a metric tile; replaced with plain text.
7. The first Streamlit tests chained `.click()` into `run()`, which fails because `click()`
   returns the widget, not the app.

## Taxpayer page (October 25)
Claude checked Zimo's Intake contract against P1's session API, ran his five questions end to end,
then wrote `src/ui/` and `tests/test_taxpayer_page.py`. Found during that work: Kaiwen's graph and
`Sessions.resume` store the raw answer in the checkpoint before Intake runs, so SSN screening was
moved into the UI; the existing dashboard app tests assumed the staff page was the default page and
were changed to load it directly.

## What I (David) must still do
- Read every file before committing (R20) and run `pytest` and the app on my own machine.
- Record the demo video (5–10 min).
- Note here anything I changed after review.
