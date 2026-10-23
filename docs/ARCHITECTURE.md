# Proposed Architecture and Shared Contracts

Status: design proposal awaiting team agreement.

Use a shared state containing session ID, intake answers, document inventory, extracted records, eligibility decisions with citations, monetary values with provenance, review findings, interrupt status, iteration counts, and context summary.

Each agent returns a typed partial update. Only the orchestrator chooses the next agent. Parallel extraction should key results by document ID and merge without silently overwriting conflicting records. Test different completion orders.

Every monetary record should include value, currency, form line, source type, source document/field or input actor/time, tool name and inputs for computed values, and dependencies on upstream records.

Do not calculate Social Security taxability until other required income inputs are available. Review must independently check values against evidence and route corrections back rather than patching results itself.

Persist checkpoints for resumption. Human resolution must record the decision and preserve audit history. Both review retries and total handoffs need explicit limits and tests.
