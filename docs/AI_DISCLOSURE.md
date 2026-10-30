# AI-use Disclosure (spec 5.3)

Compiled from each member's log in `docs/ai_log/` (R19). Where a log is missing or still has
a placeholder, this page says so rather than filling it in. P2 owns the final version.

## Disclosure

AI wrote most of SilverFile's code, tests and documentation, and the team's work was
mainly specifying, reviewing, running and correcting it. Recorded AI assistance included: OpenAI
Codex (repository scaffold, and P1's shared contracts, LangGraph routing, SQLite
persistence, interrupts and loop guards), Claude Opus 5.5 in Claude Code or the Claude
app (P5 Rules agent and policy corpus, P6 Review agent, CI and Docker, P7 staff dashboard,
taxpayer page and filled IRS PDF, and the October 26 cross-workstream integration fixes),
and Claude Sonnet 5.5 in Claude Code (P2 tax tools, MCP server, Computation agent and golden
returns; P4 W-2 extraction, SSN rule, PII masking, fixtures and eval cases). Each member
gave the AI their workstream's rules from the team's Assumptions & Working Rules document
and the shared contracts in `src/state.py`, and the AI produced first drafts that members
ran, reviewed and corrected through pull requests reviewed by a teammate. Human checks
caught real errors: a 2,000 instead of 1,600 add-on for married filing separately and a
senior deduction wrongly given to an MFS return (P2, by unit tests and re-reading rule
C12); wrong line formulas for lines 24 and 33 in the first review checklist (P6, by hand);
three escalation bugs in the Rules agent, including an empty resolution clearing an
escalation (P5, by P1's code review); guessed IRS PDF field names, truncated SSN fields and
a preselected session-closing option on the staff page (P7, by testing the output); and a
NumPy version that would not install on Python 3.11 (P6). End-to-end testing on October 26
found integration bugs that each component's own tests had missed, such as extraction
being skipped after an early flag, producing a $0-wage draft that Review passed; these were
fixed with regression tests. Runtime tax calculations use deterministic MCP tools; document and direct-entry
amounts come from inputs. AI helped draft the formulas, fixtures and golden expectations,
so deterministic execution alone does not establish correctness. The one runtime model call
(Intake's plain-language document briefing, spec 4.5) does no arithmetic and is mocked
in unit tests (R14). Items not yet verified by a person are listed below.

## Per-member record

| Member | Tool | What AI produced | Human verification recorded | Log |
|---|---|---|---|---|
| P1 Kaiwen | OpenAI Codex | Contracts, graph, routing, persistence, interrupts, loop guards, README | Full suite runs; separate CLI processes for start and staff resume; review of P5's PRs | `kaiwen.md` |
| P2 Jad | Claude Sonnet 5.5 | Tax tools, MCP server, Computation agent, golden returns, P2 docs | Suite run on Python 3.12; oracle cross-check; Oct 27 AI-assisted IRS-source and spreadsheet check of g01–g06. Independent human re-derivation not recorded | `jad.md` |
| P3 Zimo | Claude Sonnet 5.5 (Claude app) | Intake questions, flags, go-back, summaries, direct-entry lines and API-key reader | Zimo records local full-suite runs and fixes; real batch token counts are committed in metrics.md. Introductory model/date placeholders still need cleanup | `zimo.md` |
| P4 Christina | Claude Sonnet 5.5 | W-2 extraction, SSN rule, PII masking, fixtures, eval cases | Reviewed by P4; Ran the full test suite on Mac (352 passed), when test run failed on the dropped-digit problem, it was reported and fix was applied. | `christina.md` |
| P5 Lluc | Claude Opus 5.5 | Rules agent, policy corpus, decision-table tests; Oct 26 integration fixes and spec 4.5 batch | Reviewed by P1; fixes checked to fail on old code and pass on new; end-to-end runs | `lluc.md` |
| P6 Ziling | Claude Opus 5.5 | Review agent, CI, Docker, OCR dependencies | Checklist written and corrected by hand; both eval cases run in Docker with refunds matched | `ziling.md` |
| P7 David | Claude Opus 5.5 | Staff dashboard, taxpayer page, HTML and PDF form | App driven in a browser; seven AI mistakes recorded and fixed | `david.md` |

## Still to verify before submission

- Golden returns re-derived in a spreadsheet by a person (P2, R12).
- Actual API input-token counts for both strategies are now committed in `docs/metrics.md` (PR #44); retain the measurement method and distinguish these from offline estimates.
- P3 and P4 logs are present. P3 records Claude Sonnet 5.5 in the disclosure paragraph, but introductory model/date placeholders remain; the author should resolve them.
- Intake risk handoffs were corrected in PRs #49 and #51; include them in the final-revision end-to-end checks.
- Reconcile the final report and video disclosure with the actual assistance used.
- Every member can explain their own code (R20).
