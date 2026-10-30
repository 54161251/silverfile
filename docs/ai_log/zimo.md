# AI log - Zimo Li (P3, Intake agent)

R19: tool used, task, what it got wrong, what I changed.

Tool for every entry: Claude Sonnet 5.5 (Claude Opus 5.5 for the October 30 fix) in the Claude app. Claude wrote the code
and tests in the chat and told me which file to put them in; I pasted them into my own clone,
ran every test, committed and pushed myself. Claude never had direct access to my repository.

## 2026-10-25 - Intake agent

- **Task:** `src/agents/intake.py` and `tests/test_intake.py`: the only agent that talks to the
  taxpayer. One question at a time, plain language, no arithmetic, no advice. Answers become
  `intake` fields, with flags for escalation (advice request, third party answering,
  contradiction, out-of-scope mention, uncertain answer, volunteered SSN), a `session_summary`
  for resuming, and `open_questions` for Rules.
- **Decisions:** Intake uses no model of its own; parsing is deterministic keyword and format
  matching, so every behaviour can be tested. Escalation wording is imported from Rules'
  `ESCALATION_CATALOG`, not rewritten. New questions are conditional (`only_if`) so they do not
  change other people's starter data.
- **What Claude got wrong, and what I changed:**
  1. Claude had me add a `has_dependents` question; it broke 19 of my teammates' tests
     (the graph stopped at Intake). I removed it; dependents are now asked only when Rules names
     a missing dependent field.
  2. A summary label was missing for the SSN question (`KeyError`); I added it.
  3. Twice, code was pasted into the wrong function; I replaced the whole function.
  4. Matching on whole words missed "son's"; fixed.
  5. Several tests failed with `NameError` because I had not updated the import list.

## 2026-10-26 - edge-case tests and fixes

- **Task:** more tests for dependents, corrections, empty and garbled answers, and an SSN mixed
  into other text.
- **Found by these tests and fixed:**
  1. "I am married" was not understood (only the exact word "married" was). The parser now
     reads full sentences, but "not married", "widowed" and mixed answers still go to a person.
  2. A volunteered SSN, when sent together with an advice request, was copied into the flag's
     `excerpt`. All flag excerpts now have SSNs removed, with a test.
  3. Birth dates written as "March 5 1958", "Mar 5, 1958" or "March 5th, 1958" were rejected;
     they are now accepted. Two-digit years are still rejected on purpose.
  4. Added a plain-language hint to the nonresident and dependent questions.
- **What Claude got wrong this session:**
  - Its first test expected `next_question` to return nothing after the dependent fields were
    filled; it correctly returns the next ordinary question. I fixed the test after running it.
  - Claude first called it a bug that "sorry, I meant single" did not change an answer. That was
    wrong: its probe asked the same question twice, which does not happen in the real flow, and
    the code deliberately flags a correction for staff instead of overwriting. I changed no code;
    I kept a test of the real behaviour.
  - Claude first read "my Intake branch is merged" in the meeting notes as done. Checking
    `git branch -r --merged origin/main` showed it was not merged yet.
- **Verification (run by me):** the full test suite after each change (last run after pulling
  `main`: 382 passed, 20 skipped because OCR is not installed on my machine); a test that
  closes and reopens the SQLite database and resumes the session; reading Lluc's diff to check
  that none of my changes were lost.
## Later work (10/28 to 10/29)

- **What I asked Claude to do:** finish the filing-status questions, then Jad's tasks J1 and J2.
- **What changed in Intake:**
  1. Answering just "married" now asks a follow-up, "Will you file together with your spouse, or
     separately?", and records the filing status from the reply. An unclear reply is flagged as
     uncertain. Changing an earlier answer to "married" through go-back clears the old status.
  2. The staff-help rule for filing status (E5) was narrowed to the words widow, widowed,
     widower, divorced and separated, or a death word together with a spouse word. Plain
     "married" no longer triggers it.
  3. J2: after one question, "any of these, or none?", Intake asks for Form 1040 lines 8, 10, 17,
     19, 20, 23 and 26 in plain words and writes numbers to `user_inputs`. "None" fills all seven
     lines with 0. When Computation returns an open question such as `user_inputs.10`, Intake
     maps it to the matching question. Line 25c is not asked because it was not on Jad's list.
  4. J1: `src/api_key.py` reads `ANTHROPIC_API_KEY` from the environment, then `.env`, then a
     gitignored `api_key.txt`. A blank value counts as missing, and the key is never printed.
     `run.py batch` stops with a clear message if no key is found; `--estimate` needs no key.
- **What Claude got wrong:**
  - When it replaced `parse_filing_status`, it also deleted three word lists that other code
    used. Many tests failed with a NameError. I put the lists back after running the tests.
  - Three older tests assumed that "married" meant married filing jointly. They failed after
    the follow-up question was added, and I updated them to the new wording.
  - An edit to a test assertion left a wrong indentation, which caused an `IndentationError`;
    Claude rewrote the whole test function.
  - It said my teammate's change might cause a NameError for a removed import. I checked and
    the import was still there, so there was no problem.
- **Verification (run by me):** the full test suite after each change; the latest run was
  396 passed, 20 skipped because OCR is not installed on my machine. The new tests for the API
  key use fake strings only, and no real key was ever put in a file, in chat or in a commit.
  The Intake work is in PR #41 and the API key work is in PR #42.


## 2026-10-30 - Risk flags reach Rules right away

- **What I asked Claude to do:** fix a review finding: Intake recorded risk flags but kept
  asking questions inside the node, so Rules could not see a flag until the next answer.
- **What changed:** advice requests (E4), someone else answering (E6), out-of-scope items (E1)
  and contradictions (E2) now make Intake return at once, so Rules and a colleague see the flag
  before any more questions. The unanswered question is asked again afterwards. PR #51.
- **What Claude got wrong:** Claude first left contradictions out, because an earlier design
  only recorded them. A second review pointed this out, and contradictions now hand over too.
- **Verification (run by me):** updated the two tests that checked the old behaviour, added
  hand-over tests, and ran the full suite: 402 passed, 0 failed.

## Disclosure paragraph (for docs/AI_DISCLOSURE.md)

P3 (Zimo Li) used Claude Sonnet 5.5 (Claude Opus 5.5 for the October 30 fix) in the Claude app. Claude wrote the Intake agent
and its tests in the chat, and I put the code into my local copy of the repository, ran the
tests and committed it. Intake itself uses no AI model: it asks fixed questions and reads the
answers with deterministic rules. Claude's mistakes that I caught by running the code are listed
above. The most important was an SSN that could be copied into a flag record; the test that
found it is in `tests/test_intake.py`.