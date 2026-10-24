# P7: Staff dashboard, HITL resolution, form with provenance

Owner: P7 (David). Files: `streamlit_app.py`, `src/dashboard/`, `.streamlit/config.toml`,
`data/forms/f1040sr_2025.pdf`, `tests/test_dashboard_*.py`, `tests/test_form_render.py`, `tests/test_pdf_fill.py`.

## Run

```sh
pip install -r requirements.txt
python run.py start --demo --thread-id demo-clean             # a finished draft
python run.py start --demo --hitl --thread-id demo-hitl       # waits for staff (E6)
streamlit run streamlit_app.py                                # http://localhost:8501
```

Staff sign-in reads two variables from the environment or `.env` (R6, R16). Synthetic values for the demo:

```
SILVERFILE_STAFF_IDS=demo_staff,staff_jlee
SILVERFILE_STAFF_PASSCODE=silverfile-demo
SILVERFILE_DB=runtime/sessions.sqlite   # optional; same default as run.py
```

If either staff variable is missing, sign-in is off and the dashboard is read-only (fail closed).

## What staff see

| View | Content |
|---|---|
| Overview | Counts for Needs staff, Waiting on taxpayer, In progress, Draft ready, Closed. "Draft ready" is the brief's "submitted": handed to Kushim, never filed (A25). |
| HITL queue | Every session paused at a staff `interrupt()`, with code, kind, reason, who raised it and when. **Open & resolve** goes to that return. |
| All returns | One row per thread in the checkpointer. Select a row to open it. |
| Return detail | Resolve panel (when waiting), then tabs: Draft form, Escalations (full audit log), Documents (boxes, confidence, unverified), Rules & review, Trace (handoffs). |
| Sample returns | P2's golden returns, computed live by `computation.compute_return`, to show the form while the demo graph has no Computation step. Never listed as sessions. |

## Resolving a HITL event

1. The orchestrator routes an open escalation to the `human` node, which calls `interrupt()` with the escalation record (contract #2).
2. The dashboard finds it in the snapshot (`task.interrupts`, type `staff_resolution`) and shows the record, P5's "what the taxpayer heard" sentence (`rules.ESCALATION_CATALOG`) and the allowed options.
3. Signed-in staff pick an option (none is preselected, so closing a session is always deliberate) and write a note. E2, E3, E5, E7 and E8 options that change data also take a field and value; the field is suggested from the escalation evidence.
4. `Store.resolve` checks the signed-in ID is `resolved_by`, validates the `ResumePayload` (contract #3), checks the escalation is still the pending one, and calls P1's `Sessions.resume`, i.e. `Command(resume=payload)`, with the adapters for the session's mode.
5. P1's `apply_resolution` stamps `resolved_at`, keeps the record, and turns overrides into `human_resolution` provenance. The Escalations tab shows staff ID, time, decision and note.

## Form output (D7)

- **HTML (primary).** `form_render.render_form` lays out the §3.1 lines in 1040-SR order. Hover a value for a one-line source summary. Click it for the full provenance record: kind, formula, inputs (each linked to its line in the downloaded HTML), source document and box, MCP tool and version, the `policy.md` citation with the cited text, who entered it and when. **Download HTML** saves a standalone copy.
- **IRS PDF (stretch).** `pdf_fill.fill_pdf` writes the same values into the official 2025 fillable 1040-SR. Field names were mapped by drawing each widget's name over the rendered page. It fills names, masked SSNs, dependents, filing status, the four 12d boxes (from the 12d provenance inputs), and lines 1a–37. The 2025 form's line 11b is the form's own copy of 11a. The file's XFA copy is removed so every viewer shows the filled values, and each page carries a red DRAFT / NOT FILED line.

## Design choices (for the report)

- **B7:** the dashboard writes only resume payloads. It never edits `lines`, starts sessions, or calls agents. Everything shown comes from checkpoints.
- **R9:** no arithmetic. Values are formatted (thousands separators, parentheses for a Schedule 1 loss), never computed. Line 11b on the PDF is a copy, not a calculation.
- **R17:** SSNs are masked on screen, in the HTML and in the PDF. All text is HTML-escaped before rendering.
- **Staff authentication:** allowed IDs plus a shared passcode from `.env`, compared in constant time. The same failure message is shown whatever was wrong.
- **Double submit and stale tabs:** a resolution for an escalation that is no longer pending is refused with "refresh the dashboard".
- **Readability:** one font family, tabular numbers, 16 px form text, colour plus a text label for every status, and keyboard-reachable provenance (each value is a `<summary>` element).

## Failure mode (R21)

Two staff members open the same escalation in two tabs. A second click after the first has finished is refused ("no longer waiting; refresh"), and a test covers that. But if both press **Resolve** within the same moment, both requests can pass the pending check before either resume is saved, because nothing locks the thread between reading the snapshot and resuming it. The audit log could then show two decisions. A production fix is a per-thread lock, or checking the snapshot's checkpoint ID at resume time.

## Handoffs and open items

| With | Item |
|---|---|
| P3 | The taxpayer page plugs in without editing P7 files: create `src/ui/taxpayer_page.py` with a `page()` function and `streamlit_app.py` adds it to the navigation. |
| P4 / P6 | Please add the three variables above to `.env.example` and the Docker image. The app also needs port 8501 exposed. |
| P1 | Demo adapters use a placeholder Computation, so demo sessions show no lines. Wiring `src.agents.computation.run` into `demo_agents.adapters()` would make every demo session show a real draft here, with no dashboard change. |
| P1 / P2 / P5 | E3 "preparer enters the taxable amount": `apply_resolution` accepts only `intake.*` and `user_inputs.<line>`, and Computation reads 4b/5b from documents, so a human-entered 1099-R taxable amount has no path into the computed lines yet. |
| P2 | Display labels: on the 2025 form line 7 is "7a", line 27 is "27a", and line 11b repeats 11a. Also, `computation.py` adds the other-income lines with Python `sum()` before calling `taxable_social_security`, which is arithmetic outside the MCP tools (R9). |

## Verification

- 36 new tests (`tests/test_dashboard_core.py`, `tests/test_form_render.py`, `tests/test_pdf_fill.py`, `tests/test_dashboard_app.py`). The app tests drive the real Streamlit script headlessly: sign in, resolve an E6 escalation, and confirm the session resumed to `scaffold_complete` with the staff ID in the record.
- Full suite: 195 passed on Python 3.11 and 3.13 (all teammates' tests included).
- Checked by hand in a browser: queue, sign-in, resolution, escalation log, hover tooltip, click-open provenance, and the filled PDF rendered page by page.
