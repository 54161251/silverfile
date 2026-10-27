# P6 AI assistance log

## October 24, 2026 — Review agent

Tool: Claude (Anthropic, Claude Opus 5.5) in the Claude app, connected to my local copy of the repo.

I wrote the review checklist with Claude first (what to check, and which agent each problem goes back
to), corrected it twice myself (line 24 is 22 + 23 not 16 + Schedule 2; line 33 includes line 26 and
32; 13a must stay 0; added the standard deduction chart exceptions). Claude then read the existing
contracts (`state.py`, `orchestration.py`, `computation.py`, `rules.py`) and generated
`src/agents/review.py`, `tests/test_review.py` and `docs/P6_REVIEW.md` from that checklist.

Verification: the 6 non-blocked golden returns pass review after the real Computation agent runs;
17 planted-error tests each produce the expected finding; full suite 215 passed. Found that goldens
g02-g04 lack the 1099-R box 7 code (reported to P2/P4). The 0.8 confidence threshold is an assumption.

## October 24, 2026 — CI and Docker

Tool: Claude Opus 5.5, same setup.

Claude wrote `.github/workflows/ci.yml`, `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.env.example`
and `docker/entrypoint.sh`. I committed them, opened the PRs and checked the results myself. The CI PR
failed at first because `review.py` was not on main yet; it went green after the review PR was merged and
main was pulled into the branch. I installed Docker Desktop, built and ran the image on my Mac, opened the
dashboard at localhost:8501, signed in as `demo_staff` and saw both demo sessions.

What went wrong: `ci.yml` first ended up in the repository root instead of `.github/workflows/`, and
we moved it. When I asked how to add a Docker section to the README, Claude edited Kaiwen's
README without being asked; I told it to undo that and it restored the file unchanged.

## October 26, 2026 — OCR dependencies and grader simulation

Tool: Claude Opus 5.5, same setup.

P4 asked P6 to add the OCR packages and Tesseract to the build. Claude added them to `requirements.txt`,
the `Dockerfile` and CI. Claude found that the requested `numpy==2.5.3` needs Python 3.12, so it would not
install on our 3.11 target, and switched to 2.4.4; P4's 41 extraction tests pass with it (run by Claude).

Grader simulation, run by me in Docker on macOS: `eval_case_1` read the W-2 image and reached `draft_ready`
with a 2,650 refund; `eval_case_2` stopped at E6, resumed with the resolution file and reached
`draft_ready` with a 1,995 refund. I checked line 34 for both in the staff dashboard. Review passed both on
the first round. Not yet done: a run with made-up data of my own.

## Disclosure paragraph (for docs/AI_DISCLOSURE.md)

P6 (Ziling Yan) used Claude Opus 5.5 in the Claude app, connected to a local copy of the repository.
I worked out the review checklist with Claude and corrected its line formulas myself (lines 24 and 33,
line 13a, the standard deduction chart exceptions). Claude then wrote the review agent, its tests, the CI
workflow, the Docker setup and the OCR dependency changes. I ran and checked the work: the test suite,
the CI results on each pull request, the Docker build on my Mac, and both evaluation cases in Docker, where
I compared the refunds with the hand calculations in the eval write-ups. Claude also caught a numpy version
that would not install on Python 3.11. I have no programming background, so I relied on Claude to explain
each step; the code is AI-written, and my part was the checklist, the corrections, running everything and
confirming the results.

## October 27, 2026 — Traces and grader simulation update

Tool: Claude Opus 5.5, same setup.

Claude wrote `traces/make_traces.py` and generated `traces/eval_case_1.json` and `traces/eval_case_2.json`
from current main. The script masks personal details with P4's `mask_data`, leaves out raw intake answers
and refuses to write a file that still contains an unmasked SSN. Claude also checked the files for SSNs,
birth dates and account details. eval_case_1 ended `draft_ready` with refund 2,650 and eval_case_2 paused
at E6, resumed and ended `draft_ready` with refund 1,995.

Claude reran my made-up MFJ case. The low-confidence W-2 box that looped to E10 on Oct 26 now raises E8;
resolving it with the confirmed wages finished the return with the same 1,741 refund and review passing.
Claude updated docs/P6_GRADER_SIM.md and docs/P6_REPORT_SECTION.md to match. I read the changes,
committed them and opened the PR.
