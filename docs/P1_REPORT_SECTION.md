# Integration and orchestration — AI-assisted working draft

The integration layer separates control decisions from tax-domain work. A deterministic
orchestrator chooses an agent from the current state, without extracting documents,
performing tax arithmetic, or conversing with the taxpayer. Shared Pydantic contracts
define provenance, escalation records, staff resume payloads, intake flags, and extracted
documents. Agent adapters are checked against their allowed output fields, preventing
an audit agent from silently changing a computed amount.

Document extraction uses parallel LangGraph tasks. Each worker handles one upload,
and an order-independent reducer joins results by document ID. Identical duplicates
are safe, while conflicting records fail explicitly. SQLite checkpoints preserve the
household session across application restarts. Human review uses a LangGraph interrupt;
the resolution must identify the pending case, an allowed option, a staff member and
a note. The runtime timestamps the decision and rechecks affected downstream work.

Review can return findings to the responsible agent. Three revision attempts are the
maximum, and a separate handoff guard detects a directed pair repeated three times in
the last ten transfers. Either condition pauses for staff review instead of running
indefinitely. Tests demonstrate actual overlapping extraction workers, persistent human
resume, review send-backs, and both guards. A failure mode is inconsistent document
versions: conflicting same-ID extraction results are deliberately rejected; supersession
must be agreed with the extraction and computation owners. The current offline skeleton
proves integration behavior only, and does not yet demonstrate a completed tax return.
