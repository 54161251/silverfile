# P1 contract handoff (R8/R10)

The five Pydantic models live in src/state.py. State keys intentionally preserve P5's
existing interface. Agent adapters return partial dictionaries and cannot write another
agent's fields. Graph bookkeeping is written by the integration layer, not agents.

Documents use an order-independent reducer keyed by doc_id. Equal duplicate records
are harmless; conflicting duplicate IDs fail rather than selecting a completion order.
Use a new document ID for a corrected upload. Escalations are sequential ID upserts,
so a resolved record replaces its earlier open version without discarding other records.

Human resolutions require a nonblank note and staff identifier. The dashboard sends
ResumePayload; the runtime records resolution time itself. Computation returns line
records with whole-dollar integer values, tool metadata, inputs, formula and timestamp.

P2 may return open_questions for missing calculation inputs; this is the integration
extension needed for routing back to Intake. No financial arithmetic belongs to P1.
