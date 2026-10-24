# Dashboard walkthrough: resolve a HITL event (P7)

Uses the offline demo graph, so no API key is needed. From the repository root, after
`pip install -r requirements.txt`, put the synthetic staff settings in `.env`:

```
SILVERFILE_STAFF_IDS=demo_staff
SILVERFILE_STAFF_PASSCODE=silverfile-demo
```

1. Create one finished session and one that needs staff:
   ```sh
   python run.py start --demo --thread-id demo-clean
   python run.py start --demo --hitl --thread-id demo-hitl
   ```
2. Run `streamlit run streamlit_app.py` and open http://localhost:8501.
3. The overview shows **Needs staff: 1** and **Draft ready: 1**. The HITL queue lists `demo-hitl`:
   E6, "Refund account is not in the taxpayer's name".
4. In the sidebar, sign in as `demo_staff` / `silverfile-demo`.
5. Click **Open & resolve**. Read the reason, the evidence and what the taxpayer heard.
6. Choose **Verified, continue**, write a note (for example "Phoned taxpayer; the account is hers"),
   and click **Resolve and resume**.
7. The return moves to **Draft ready**. The Escalations tab shows the decision, staff ID, time and note.
8. Check from the terminal that the resume was persisted:
   `python run.py status --demo --thread-id demo-hitl` prints `scaffold_complete`.
9. Open **Sample returns** and pick a return. Hover any amount for its source, click it for the full
   provenance record, and use **Download IRS PDF** for the filled official form.

## Suggested demo video segment (about 2 minutes of the 5–10)

| Time | Show |
|---|---|
| 0:00 | Overview counts and the HITL queue; point out "Draft ready" means handed to Kushim, never filed. |
| 0:20 | Try to resolve while signed out: the controls are hidden. Sign in. |
| 0:40 | Open the E6 escalation; read what the taxpayer heard (neutral wording, never accusing). |
| 1:00 | Resolve with a note; show the return move to Draft ready and the audit row. |
| 1:30 | Sample return: hover line 13b, then click it to show the formula, the AGI input, the MCP tool and the cited policy text. |
| 1:50 | Download and open the filled IRS PDF with the DRAFT banner and masked SSNs. |
