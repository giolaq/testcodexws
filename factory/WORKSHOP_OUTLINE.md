# Software (re)-Factory workshop

Use this outline to present the workshop. The attendee website contains the commands and checkpoints; keep the live explanation focused on why each decision matters.

## Outcome

In 100 minutes, each attendee turns a PRD into approved tickets, runs coding agents in isolated Git worktrees, reviews QA evidence, and verifies an integrated application.

Attendees should leave able to:

- Explain what an AI software factory adds around coding agents.
- Plan product intent, architecture, program design, and vertical slices before implementation.
- Use GitHub Projects as the shared view of work.
- Inspect prompts, logs, diffs, tests, and reviews for one ticket.
- Adapt the workflow to their own agents and risk level.

## Prerequisites

Ask attendees to complete setup before the session.

Everyone needs:

- macOS, Linux, or Windows with WSL2.
- Python 3.11+, Node.js 20+, Git, and a modern browser.
- Ports 5000 and 5050 available.
- GitHub CLI and a personal disposable workshop repository. Every attendee
  creates their own; the facilitator uses a separate repository on screen.

The live path also requires:

- GitHub CLI authenticated with the `project` scope.
- Permission to create issues, branches, and Projects.
- An authenticated Claude, Codex, Cursor, or custom agent CLI.
- Network access to GitHub and the chosen model provider.

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
| Rehearsal | Learning or running a reliable dry run | Personal repository only; no Project writes or model calls |
| Live | Demonstrating real GitHub issues and agents | GitHub, network, and an authenticated agent CLI |

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
| 85–100 | Verify the result | Integrated app checked across key journeys and viewports |

## The workshop story

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

**Check:** The ticket contains tests and its history records QA approval.

### 7. Run the factory

**Goal:** Observe isolated implementation, verification, and review.

**Do:** Select **Run factory** and follow one ticket. Open its detail drawer and
show the exact prompt, live agent log, diff, protected tests, gate output, and
state history. The operation panel always shows the equivalent CLI command.

**Check:** At least one ticket reaches Done, and attendees can locate the evidence behind that state.

### 8. Verify the result

**Goal:** Check the integrated product, not only individual tickets.

**Do:** Run the application and tests. Verify browse, search, details, favorites, and TV navigation at desktop, mobile, and TV sizes.

```bash
.factory/venv/bin/python -m pytest -q demo-app/tests
node --test demo-app/static/tests/*.test.js
.factory/venv/bin/python demo-app/app.py
```

Then open **Evidence**, complete the Factory Canvas, and select **Create evidence
packet**.

**Check:** The integrated app works and the evidence report explains why the change is complete.

## Close

An agent is an executor. A factory is the engineering system that supplies context, isolation, quality gates, traceability, and human decisions.

Ask each attendee:

1. Which repeated engineering task is slow or inconsistent?
2. What evidence would make an agent change safe to review?
3. Where must a human make the final decision?

Recommend the smallest useful workflow:

- **Lean:** one agent, local tests, and diff review.
- **Standard:** planning, worktree isolation, QA, gates, and GitHub review.
- **Assured:** stricter approvals, security checks, traceability, and release evidence.

## Facilitator reference

Keep detailed setup and recovery material out of the spoken path:

- [Facilitator runbook](FACILITATOR.md)
- [Control Center](CONTROL_CENTER.md)
- [Agent configuration](CONFIGURATION.md)
- [Planning workflow](PLANNING.md)
- [Factory command reference](README.md)
