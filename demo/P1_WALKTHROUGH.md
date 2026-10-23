# P1 integration walkthrough

This checks graph wiring only. It does not read W-2 images, call an LLM/MCP server,
compute a tax return, or replace P4's assignment demo fixtures.

From the repository root, after installing requirements.txt:

```sh
python run.py start --demo --thread-id p1-clean
python run.py start --demo --hitl --thread-id p1-human
python run.py status --demo --thread-id p1-human
python run.py resume --demo --thread-id p1-human --input demo/p1_resume.json
```

The clean case ends as scaffold_complete with two structured synthetic documents.
The human case pauses as awaiting_human with esc_0001, then ends as scaffold_complete
after resolution. The separate commands reopen the same SQLite file. Keep the default
runtime database, or provide the same --db path to every command. Use a fresh thread ID
for another start; existing sessions cannot be overwritten. If several escalations exist,
resolve the pending ID shown by status, one at a time.
