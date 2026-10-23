# Team and Ownership

Based on the named assignments in the team's [AI Project document](https://docs.google.com/document/d/1tkAG7Xk9ocj3Wmg04FzHj_xkaeI4_IxfM0N6yviZj9s/edit?tab=t.0), read October 23, 2026. GitHub usernames and reviewers remain to be agreed.

| ID | Member | Workstream | Graded focus area | Responsibilities |
|---|---|---|---|---|
| P1 | Kaiwen | Integrator / Orchestrator | Task division and management | State contract, graph, routing, loop guard, checkpointer, merges, README |
| P2 | Jad | Computation + MCP, then report | Inter-agent communication | Golden returns, tax-math tools, Computation agent; report and AI disclosure from Wednesday |
| P3 | Zimo | Intake + memory | Agent memory | Conversational agent, accessibility, resumability, intake flags, context-window metrics |
| P4 | Christina | Extraction + security + fixtures | Security | W-2 extraction, SSN rule, PII masking, fixture data, both eval cases |
| P5 | Lluc | Rules + escalation | Guardrails and ethics | Eligibility & Rules agent, policy.md, escalation decisions E1–E8 |
| P6 | Ziling | Review + QA/DevOps | MLOps/DevOps | Review agent, CI, test harness, Docker, grader simulation |
| P7 | David | Dashboard + demo | To confirm with instructor | Staff dashboard, HITL resolution, form with provenance, demo video |

Six agents remain required; the dashboard is a separate application workstream, not a seventh agent. Each member commits their own work and records AI assistance. P1 coordinates shared contracts and integration; all collaborators may merge their own tested PRs without major unresolved issues (owner update, October 23).

The assignment page specifies six-person teams. The actual team has seven members; instructor approval of the team size and P7's graded focus area is not recorded here.

## Integration handoffs

| Interface | Owners |
|---|---|
| State and agent contracts | Kaiwen with everyone |
| Intake flags → escalation decisions | Zimo → Lluc |
| Golden returns → fixtures and QA | Jad → Christina / Ziling |
| Review findings → revision routing | Ziling → Kaiwen |
| Escalation records → dashboard | Lluc → David |
| Interrupt/resume mechanism → resolution buttons | Kaiwen → David |
| Batch fixtures → context metrics | Christina → Zimo |
| Workstream write-ups and AI logs → report | Everyone → Jad |

The Google Doc's Assumptions & Working Rules tab contains detailed interfaces, rules, and individual schedules. The assignment specification takes precedence over team assumptions. Team code freeze: Friday October 30 at 9 p.m.; submission: Saturday October 31. Verify deadline updates in Canvas.
