# AI log - Zimo Li (P3, Intake agent)

R19: tool used, task, what it got wrong, what I changed.

Tool for every entry: Claude [CONFIRM MODEL NAME] in the Claude app. Claude wrote the code
and tests in the chat and told me which file to put them in; I pasted them into my own clone,
ran every test, committed and pushed myself. Claude never had direct access to my repository.

## [CHECK DATE] - Intake agent

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

## Disclosure paragraph (for docs/AI_DISCLOSURE.md)

P3 (Zimo Li) used Claude [CONFIRM MODEL NAME] in the Claude app. Claude wrote the Intake agent
and its tests in the chat, and I put the code into my local copy of the repository, ran the
tests and committed it. Intake itself uses no AI model: it asks fixed questions and reads the
answers with deterministic rules. Claude's mistakes that I caught by running the code are listed
above. The most important was an SSN that could be copied into a flag record; the test that
found it is in `tests/test_intake.py`.