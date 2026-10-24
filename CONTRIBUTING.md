# Team Collaboration

1. Claim a task and record the owner before starting.
2. Use the team's branch convention `p<N>/<topic>`, such as `p3/intake` or `p7/dashboard`.
3. Keep changes focused and commit your own contributions.
4. Open a pull request explaining the behavior, checks performed, and remaining gaps.
5. Teammates may merge their own PRs once relevant tests pass, there are no unresolved major issues, and conflicts are resolved. A teammate review is encouraged; P1 approval is not required for routine changes. Coordinate changes to shared contracts with affected owners. Do not overwrite another person's work.
6. Include TASKS.md and relevant documentation changes in the same PR as the feature. Follow README's “Keeping this README current” section; explain in the PR if documentation is unaffected.

Never commit `.env`, API keys, real SSNs, or real financial documents. Use synthetic fixtures only. Record AI assistance accurately in docs/AI_DISCLOSURE.md.

The repository owner can invite teammates through Settings → Collaborators using their GitHub usernames. A private repository link alone does not grant access.

Follow the team's Assumptions & Working Rules tab for detailed requirements: cite rule IDs in PRs, keep PRs focused (roughly 300 changed lines maximum), update individual AI logs, and include appropriate tests for implementation changes. The assignment specification takes precedence over team assumptions.

Owner update, October 23: all collaborators may merge their own PRs under the checks
above. This supersedes the older Google Doc's "only P1 merges" restriction. All six
teammates are already listed as collaborators. Settings currently contain no classic
branch protection rules or repository rulesets; this is a team workflow agreement,
not an enforced GitHub approval gate. See GitHub's personal-repository permission guide:
https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/repository-access-and-collaboration/permission-levels-for-a-personal-account-repository
