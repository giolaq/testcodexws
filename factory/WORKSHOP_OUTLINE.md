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
- Ports 5000 and 8000 available.
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

**Do:** Reset Pocket Cinema to the exercise baseline. For a live run, configure
the selected agent and run preflight. Start the dashboard in a second terminal.

```bash
./setup_demo.sh --scenario recipe-rebrand
./factory/factory configure --preset claude-workshop  # live
./factory/factory doctor --full                       # live
python3 -m http.server 8000
```

**Check:** `http://localhost:8000/factory/dashboard.html` loads. For a live run,
doctor reports no blocking errors.

### 2. Inspect the app

**Goal:** Understand the system before changing it.

**Do:** Run Pocket Cinema. Ask attendees to identify navigation, data flow, responsive layouts, and existing tests.

```bash
.factory/venv/bin/python demo-app/app.py
```

**Check:** Each attendee can name one behavior that must survive the rebrand.

### 3. Read the PRD

**Goal:** Express the change as a user outcome, not an implementation request.

**Do:** Read the TableStory PRD and identify the user, desired behavior, compatibility constraints, and observable success.

```bash
sed -n '1,220p' recipe-app-prd.md
```

**Check:** An attendee can explain the change in one sentence without describing code.

### 4. Review product intent

**Goal:** Approve the problem and desired behavior before technical design.

**Do:** Start planning, open the product artifact, revise vague statements, and approve it.

```bash
./factory/factory plan recipe-app-prd.md
export PLAN_ID=<plan-id-from-output>
./factory/factory review product "$PLAN_ID"
./factory/factory revise "$PLAN_ID" product \
  --feedback "Clarify the user journey and measurable outcome."
./factory/factory review product "$PLAN_ID"
./factory/factory approve-product "$PLAN_ID"
```

Add `--mock` to both `plan` and `revise` for rehearsal.

**Check:** The product artifact records a human approval.

### 5. Create tickets

**Goal:** Align architecture, program design, and vertical slices before parallel work begins.

**Do:** Continue planning and review four artifacts:

- Product review: problem, users, behavior, and success.
- Architecture: components, contracts, data, and constraints.
- Program design: types, signatures, layout, and call paths.
- Vertical slices: ordered tickets with acceptance criteria.

```bash
./factory/factory continue-plan "$PLAN_ID"
./factory/factory review alignment "$PLAN_ID"
./factory/factory approve "$PLAN_ID" --new-project-title "TableStory Workshop"
```

For rehearsal, use the same artifacts without GitHub writes:

```bash
./factory/factory continue-plan "$PLAN_ID" --mock
./factory/factory review alignment "$PLAN_ID"
./factory/factory approve-rehearsal "$PLAN_ID" --scenario recipe-rebrand
./factory/factory run --mock --scenario recipe-rebrand --dry-run
```

The planning agents create normal workshop tickets from the PRD. Do not seed five tickets; seeding exists only for fixtures and recovery demonstrations.

**Check:** GitHub Projects shows the approved slices as issues. In rehearsal, the dry run prints the issues that would be created.

### 6. Approve tests

**Goal:** Define acceptance evidence before implementation.

**Do:** Let the QA agent propose tests for the first ticket. Review and approve assertions that prove user-visible behavior.

```bash
./factory/factory run --review-qa-tests --once
./factory/factory approve-tests ISSUE_NUMBER
```

Use `--mock --scenario recipe-rebrand` for rehearsal.

**Check:** The ticket contains tests and its history records QA approval.

### 7. Run the factory

**Goal:** Observe isolated implementation, verification, and review.

**Do:** Run the factory and follow one ticket. Show its exact prompt, agent log, worktree, diff, test output, quality gates, review, and state history.

```bash
./factory/factory run
```

Use `--mock --scenario recipe-rebrand` for rehearsal.

**Check:** At least one ticket reaches Done, and attendees can locate the evidence behind that state.

### 8. Verify the result

**Goal:** Check the integrated product, not only individual tickets.

**Do:** Run the application and tests. Verify browse, search, details, favorites, and TV navigation at desktop, mobile, and TV sizes.

```bash
.factory/venv/bin/python -m pytest -q demo-app/tests
node --test demo-app/static/tests/*.test.js
.factory/venv/bin/python demo-app/app.py
```

Then summarize the factory evidence:

```bash
./factory/factory canvas --output factory-canvas.md
./factory/factory evidence "$PLAN_ID" --canvas factory-canvas.md
```

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
- [Agent configuration](CONFIGURATION.md)
- [Planning workflow](PLANNING.md)
- [Factory command reference](README.md)
