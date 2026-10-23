# AI-use Disclosure — Working Record

This initial repository scaffold, including the README, planning documents, proposed architecture, and collaboration templates, was generated with assistance from OpenAI Codex. It is not a completed implementation. Team members must review these materials and expand this paragraph to describe actual AI assistance in code, tests, debugging, documentation, and verification before submission.

## P2 (Jad Karaki): Claude (Anthropic), October 23, 2026

Tool and use: Claude, in a Claude Code session. Claude drafted the first versions of src/tools/tax_math.py, src/tools/mcp_server.py, src/agents/computation.py, the tests (tests/test_tax_math.py, tests/test_mcp_server.py, tests/test_computation.py, tests/oracle.py), the seven golden returns in tests/golden/, and docs/P2_COMPUTATION.md. Claude also looked up the 2025 tax parameters (standard deduction, senior deduction, rate schedules, Social Security worksheet) from public sources.

Human verification so far: Jad ran the full suite on Python 3.12 against the real src/state.py (159 passed, including the existing tests). The golden numbers were derived by Claude and cross-checked only against an independent re-implementation (tests/oracle.py). Re-deriving them in a spreadsheet (R12) is still pending and will be recorded in docs/ai_log/jad.md.

What the AI got wrong: see docs/ai_log/jad.md. Examples: it used a 2,000 additional standard deduction for married filing separately (the amount is 1,600); it gave an MFS golden return a senior-deduction qualifier; it made an arithmetic slip in a Social Security test expectation; and its first tests did not cover Schedule 1 lines 8 and 10. Automated tests and an independent oracle caught each of these.
