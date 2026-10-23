# Team Collaboration

1. Claim a task and record the owner before starting.
2. Use the team's branch convention `p<N>/<topic>`, such as `p3/intake` or `p7/dashboard`.
3. Keep changes focused and commit your own contributions.
4. Open a pull request explaining the behavior, checks performed, and remaining gaps.
5. Ask one teammate to review and have P1 (Kaiwen) merge. Do not overwrite another person's work. Branch protection is a team target; this scaffold has not configured it.
6. Update TASKS.md and relevant documentation after merging.

Never commit `.env`, API keys, real SSNs, or real financial documents. Use synthetic fixtures only. Record AI assistance accurately in docs/AI_DISCLOSURE.md.

The repository owner can invite teammates through Settings → Collaborators using their GitHub usernames. A private repository link alone does not grant access.

Follow the team's Assumptions & Working Rules tab for detailed requirements: cite rule IDs in PRs, keep PRs focused (roughly 300 changed lines maximum), update individual AI logs, and include appropriate tests for implementation changes. The assignment specification takes precedence over team assumptions.
