# Software (re)-Factory workshop

Release: `workshop-v1.1.0`

Use this outline to present the workshop. The attendee website contains the commands and checkpoints; keep the live explanation focused on why each decision matters.

## Outcome

In 100 minutes, each attendee turns a PRD into approved Tickets, runs coding
agents in isolated Git worktrees, reviews causal QA evidence, makes an
exact-revision merge decision, and previews post-delivery health.

Attendees should leave able to:

- Explain what an AI software factory adds around coding agents.
- Plan product intent, architecture, program design, and vertical slices before implementation.
- Use GitHub Projects as the shared view of work.
- Explain how an Agent Supervisor coordinates a safe dispatch wave from worker Handoff Receipts.
- Explain the separate authority of the Code Review Agent, Agent Supervisor,
  and orchestrator in the review-and-merge loop.
- Inspect prompts, logs, diffs, tests, and reviews for one ticket.
- Adapt the workflow to their own repository, PRD, agents, and risk level.

The guided exercise uses Pocket Cinema so everyone sees the same evidence. It
ends by showing the transfer path: `factory init --repo PATH` creates a
reviewable Project Contract for an existing codebase, and Live planning accepts
that project's real PRD. Do not imply that the deterministic Rehearsal agents
can implement an arbitrary product.

## Prerequisites

Ask attendees to complete setup before the session.

Everyone needs:

- macOS, Linux, or Windows with WSL2.
- Python 3.11+, Node.js 20+, Git, and a modern browser.
- Ports 5000 and 5050 available.
- A personal local Git repository for Rehearsal. Every attendee works in their
  own repository; the facilitator uses a different repository on screen.

The live path also requires:

- GitHub CLI authenticated with the `project` scope.
- A personal GitHub repository URL saved in **Connect**; its `origin` must match.
- Permission to create issues, branches, and Projects.
- An authenticated Claude, Codex, Cursor, or custom agent CLI.
- Network access to GitHub and the chosen model provider.
- Optional: a second GitHub identity, supplied through
  `FACTORY_REVIEW_GH_TOKEN`, when the demo must show formal PR approval.

Check versions:

```bash
python3 --version
node --version
git --version
gh --version
```

## Choose a path

Use one path for the full session.

| Path | Use it when | External dependencies |
|---|---|---|
| Rehearsal | Learning or running a reliable dry run | Local repository only; no GitHub or model credentials |
| Live | Demonstrating real GitHub issues and agents | GitHub, network, and an authenticated agent CLI; optional second reviewer identity |

Run the rehearsal path before facilitating the live path.

## Schedule

| Time | Step | Result |
|---:|---|---|
| 0–8 | Set up | Healthy factory and isolated demo repository |
| 8–13 | Inspect the app | Shared understanding of the baseline |
| 13–20 | Read the PRD | Testable product outcome |
| 20–35 | Review product intent | Human-approved product brief |
| 35–53 | Create tickets | Approved vertical slices in GitHub or dry-run output |
| 53–63 | Approve tests | Human-approved QA evidence |
| 63–85 | Run the factory | At least one completed ticket with traceable evidence |
| 85–100 | Verify and monitor | Integrated app, Evidence Packet, and read-only Monitor report |

## The workshop story

Start with the minimum responsible loop: a clear issue, one agent, one real
test, one pull request, and a human merge. Introduce each extra control as the
answer to a visible failure:

| Failure | Added capability |
| --- | --- |
| Ambiguous intent | Product Review and human revision |
| Conflicting design assumptions | Architecture, Program Design, and alignment |
| Colliding workers | Dependency waves, remote claims, and worktrees |
| Weak tests | QA-authored RED proof and identical-command GREEN proof |
| Too much review work | Human-attention limits and `NEEDS YOU` back-pressure |
| Lost decisions | Handoff Receipts and sanitized remote summaries |
| Stale post-merge evidence | Read-only Monitor findings |

More agents and more checks consume time and human attention. They are useful
only when they make ownership, evidence, recovery, or a decision clearer.

Repeat the same pattern for every step:

1. **Goal** — state the engineering decision.
2. **Do** — run one short activity.
3. **Check** — show the evidence that permits the next step.

### 1. Set up

**Goal:** Start with a healthy factory and a separate demo repository.

**Do:** Reset Pocket Cinema to the exercise baseline. Then open a second
terminal tab at the repository root and start the local Control Center:

```bash
./setup_demo.sh --scenario recipe-rebrand
```

Keep this second command running for the rest of the workshop:

```bash
./factory/factory control-center
```

Wait for `Factory Control Center: http://127.0.0.1:5050`. The browser should
open automatically; otherwise open that address yourself. In the browser,
select **Connect**, choose the agent preset, save it, and run preflight. Press
`Ctrl+C` only when you want to stop the Control Center. In Rehearsal,
credentials and GitHub writes are not required.

**Check:** <http://127.0.0.1:5050> loads, shows the correct repository, and
preflight reports no blocking errors.

Point out the Overview before continuing: **Current phase** explains what is
happening, **Next checkpoint** opens the next human action, and the progress row
separates completed, current, and pending phases.

### 2. Inspect the app

**Goal:** Understand the system before changing it.

**Do:** Run Pocket Cinema. Ask attendees to identify navigation, data flow, responsive layouts, and existing tests.

```bash
.factory/venv/bin/python demo-app/app.py
```

**Check:** Each attendee can name one behavior that must survive the rebrand.

### 3. Read the PRD

**Goal:** Express the change as a user outcome, not an implementation request.

**Do:** Open **PRD** in the Control Center. Read the supplied TableStory PRD and
identify the user, desired behavior, compatibility constraints, and observable
success.

**Check:** An attendee can explain the change in one sentence without describing code.

### 4. Review product intent

**Goal:** Approve the problem and desired behavior before technical design.

**Do:** Choose Rehearsal or Live agents and select **Start Product Review**.
Open **Planning**, read the Product Review artifact, request a focused revision
when a claim is vague, and approve it when the outcome is testable.

**Check:** The product artifact records a human approval.

### 5. Create tickets

**Goal:** Align architecture, program design, and vertical slices before parallel work begins.

**Do:** In **Planning**, select **Run remaining experts** and review four artifacts:

- Product review: problem, users, behavior, and success.
- Architecture: components, contracts, data, and constraints.
- Program design: types, signatures, layout, and call paths.
- Vertical slices: ordered tickets with acceptance criteria.

Select **Approve and create tickets** only after the requirements trace through
all four artifacts. In Live mode, enter a new Project title or use the Project
number saved on **Connect**.

The planning agents create normal workshop tickets from the PRD. Do not seed five tickets; seeding exists only for fixtures and recovery demonstrations.

**Check:** GitHub Projects shows the approved slices as issues. In rehearsal, the dry run prints the issues that would be created.

### 6. Approve tests

**Goal:** Define acceptance evidence before implementation.

**Do:** Open **Tickets** and select **Run one cycle**. The QA agent proposes
tests for ready tickets before implementation begins. Open one ticket, inspect
its Tests tab, and approve only assertions that prove user-visible behavior.
The focused command must fail for the missing behavior at the pre-implementation
revision. Collection errors, timeouts, skipped tests, or unrelated failures are
not valid evidence.

**Check:** The ticket shows the protected test and focused command as
**RED PROVED**. After implementation, the identical command must show
**GREEN PROVED**.

### 7. Run the factory

**Goal:** Observe supervised, isolated implementation, verification, review
feedback, repair, approval, and merge.

**Do:** Select **Run factory**, then open **Supervisor**. Follow one coordination
checkpoint from worker Handoff Receipts to the supervisor's dispatch instruction
and the orchestrator's validated state change. Return to **Tickets** and follow
the selected Ticket. Show its remote claim, supervisor instruction, exact
prompt, live log, diff, protected tests, gate output, Code Review Agent decision,
Handoff Receipts, and history. In the deterministic run, Ticket #1 receives
`REQUEST_CHANGES`, returns to the same development branch, passes its gates
again, and receives `APPROVE`. The Supervisor may then recommend the exact
revision. Standard and Assured stop for a person to select **Merge exact
revision**. In Live mode, compare the decision with the formal GitHub review or
labelled Factory comment.

If the human decision queue reaches its Charter limit, point to **NEEDS YOU**.
New dispatch pauses until the oldest decision is completed. If another runner
owns the remote claim, this runner must not start a duplicate agent.

**Check:** At least one Ticket reaches Done, and attendees can trace claim →
worker evidence → review comment → repair → approval → Supervisor recommendation
→ human merge.

### 8. Verify and monitor

**Goal:** Check the integrated product, not only individual tickets.

**Do:** Run the application and tests. Verify browse, search, details, favorites, and TV navigation at desktop, mobile, and TV sizes.

```bash
.factory/venv/bin/python -m pytest -q demo-app/tests
node --test demo-app/static/tests/*.test.js
.factory/venv/bin/python demo-app/app.py
```

Then open **Evidence**, complete the Factory Canvas, and create the packet. Open
**Monitor** and preview its read-only findings. Monitor can propose follow-up
work; it cannot repair code or merge in the same run.

**Check:** The integrated app works, the Evidence Packet explains the governed
revision and human decision, and every Monitor finding has an owner.

## Close

An agent is an executor. A factory is the engineering system that supplies context, isolation, quality gates, traceability, and human decisions.

Ask each attendee:

1. Which repeated engineering task is slow or inconsistent?
2. What evidence would make an agent change safe to review?
3. Which decisions should remain human for your use case?

Recommend a proportional workflow:

- **Lean:** one agent, local tests, and diff review.
- **Standard:** planning, supervised dispatch, worktree isolation, QA, gates,
  review rework, a Supervisor recommendation, and human exact-revision merge.
- **Assured:** stricter approvals, deeper gates, a critic, and release evidence.
- **Autonomous Demo:** optional accountability contrast only; it requires an
  explicit opt-in and is never the normal shipping path.

## Facilitator reference

Keep detailed setup and recovery material out of the spoken path:

- [Facilitator runbook](FACILITATOR.md)
- [Control Center](CONTROL_CENTER.md)
- [Agent configuration](CONFIGURATION.md)
- [Planning workflow](PLANNING.md)
- [Factory command reference](README.md)
