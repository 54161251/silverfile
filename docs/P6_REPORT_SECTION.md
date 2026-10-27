# Review, QA and DevOps (P6) report section

The review agent checks every draft before a person sees it and tries to prove it wrong. It never
changes a number. It returns pass, or revise with a list of findings, and each finding names the
agent that should redo its work. The orchestrator sends the draft back to that agent, and stops
after three revisions or a repeated handoff, so the loop always ends.

Review runs four groups of checks. Provenance checks make sure every line on the form has a full
source record and that the record still matches the documents and the other lines, which catches
stale numbers after a document changes. Totals checks recompute each total by calling the same
MCP tools that computation uses, from review's own reading of the inputs, so review does no math
itself and a wrong input or a skipped step shows up as a mismatch. Rules checks cover 1040-SR
eligibility, the line 12d box count, the standard deduction chart exceptions, and simple
contradictions such as taxable Social Security being larger than total benefits. Scope checks make
sure nothing out of scope, and no intake flag such as an advice request or a sign of pressure,
reached the draft without an escalation. Findings are sorted so the most upstream fix comes first,
since fixing an extraction error also changes everything computed after it. Review cannot raise
escalations itself, so anything that needs a person is sent back to the rules agent.

Twenty tests cover review. All clean golden returns pass, and seventeen planted errors, such as a
wrong tax amount, a stale wage figure or an unescalated 1099-R, each produce the expected finding
and go to the right agent.

On the DevOps side, a GitHub Actions workflow runs the full test suite on every pull request and
every push to main, then computes and reviews three golden returns from start to finish. It
installs Tesseract so the W-2 image tests run too. A
Docker image packages the whole system. One command builds it and starts the staff dashboard,
and two demo sessions are created on first start so a grader sees a finished draft and one waiting
for staff right away. While adding the OCR packages we found that the requested numpy version
needs Python 3.12 and would not install on our 3.11 target, and pinned an earlier one.

For grader simulation we ran both evaluation cases inside Docker and got the expected refunds,
then made up two returns of our own and checked every line by hand. This found one failure mode.
If OCR read a W-2 box with low confidence, computation asked for it to be confirmed, but intake did
not ask that question, so the run looped until the loop guard stopped it. The guard worked as
designed, and the team has since changed rules to raise a clear E8 escalation instead, so
staff can enter the value in the dashboard and the return finishes. It also showed that qualified
dividends are taxed at ordinary rates, a known limit of the tax tools. The traces folder holds a
masked step by step record of both evaluation runs.

Out of scope for this workstream: review does not judge whether a number is reasonable, only
whether it is supported and consistent, and it trusts the MCP tools it calls.
