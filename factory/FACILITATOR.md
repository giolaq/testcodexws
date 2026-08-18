# Facilitator runbook

## Recommended 100-minute workshop

| Time | Activity | Teaching point |
| --- | --- | --- |
| 0–8 min | Set up live or rehearsal mode | Everyone starts from a known environment. |
| 8–13 min | Show the Pocket Cinema baseline | Agents need an observable product starting point. |
| 13–20 min | Read the TableStory PRD | The group sees the same outcome and ambiguities. |
| 20–32 min | Start the one-agent lights-off control | A fair comparison changes the workflow, not the model or task. |
| 32–44 min | Run and approve Product Review | Product intent becomes an explicit contract. |
| 44–59 min | Run technical experts, review traceability, and publish | Alignment creates an auditable ticket contract. |
| 59–69 min | Inspect and approve QA tests | Human control is based on evidence, not trust. |
| 69–89 min | Observe implementation, retry, merge, and unlock | Bounded verification and synchronization make concurrency legible. |
| 89–100 min | Compare both results and map extension points | Judge reviewability as well as whether the app works. |

## Before the room opens

1. Prefer a disposable checkout:

   ```sh
   ./factory/new_workshop.sh ../software-refactory-live live
   cd ../software-refactory-live
   ```

2. Run the complete preflight and fix every failure:

   ```sh
   ./factory/factory doctor --full
   ```

3. Prepare a second checkout for the live lights-off control:

   ```sh
   ./factory/new_workshop.sh ../software-refactory-control recipe-rebrand
   cd ../software-refactory-control
   git switch -c experiment/lights-off
   ```

   Use the same implementation model and CLI version as the factory. If a live
   agent is unavailable, keep
   `factory/scenarios/recipe-rebrand/lights-off-sample-report.md` ready and label
   it as a discussion fixture, not a benchmark.

4. In another terminal, prepare the deterministic fallback without leaving the
   live checkout in the first terminal:

   ```sh
   ./factory/new_workshop.sh ../software-refactory-fallback recipe-rebrand
   cd ../software-refactory-fallback
   ./factory/factory run --mock --scenario recipe-rebrand --dry-run
   ```

5. Serve the board from the repository root:

   ```sh
   python3 -m http.server 8000
   ```

   Open `http://localhost:8000/factory/dashboard.html` on the presentation display.

6. For live agents, run a smoke prompt through every CLI you will offer. Confirm
   `gh auth status` shows the `project` scope.

7. Use `factory approve --new-project-title "TableStory Workshop"` rather than
   reusing the previous TV rehearsal board. Note the printed number and pass it
   to `factory run`.

## Live commands

Start the control in its prepared checkout, then leave it alone:

```sh
python3 factory/run_lights_off.py --agent codex
```

Return to the factory checkout and run:

```sh
./factory/factory plan recipe-app-prd.md
./factory/factory review product PLAN_ID
./factory/factory approve-product PLAN_ID
./factory/factory continue-plan PLAN_ID
./factory/factory review alignment PLAN_ID
./factory/factory approve PLAN_ID --new-project-title "TableStory Workshop"
./factory/factory run --agent codex --qa-agent claude --review-qa-tests --project-number NUMBER
./factory/factory approve-tests ISSUE
```

Click a dashboard ticket during every phase. Show the attendee the specification,
QA files, prompt, log, changed files, gate output, and history. After a dependency
PR is merged, point out the “PR merged and synchronized” transition before the
next ticket becomes Ready.

At the end, return to the control checkout. Test the same user journeys and
record requirements evidenced, hidden assumptions, review-unit size,
independent QA evidence, safe parallelism, and review/rework time for both
workflows. Do not present a successful control run as a problem; ask which
delivery context makes its smaller control surface sufficient.

## Deterministic fallback

If GitHub, Wi-Fi, or a model CLI is slow, switch to the credential-free scenario:

```sh
./setup_demo.sh --scenario recipe-rebrand --force
./factory/factory run --mock --scenario recipe-rebrand --once
```

If only the planning model is unavailable, run the schema-valid deterministic
experts and continue with the same two human gates:

```sh
./factory/factory plan recipe-app-prd.md --mock
./factory/factory approve-product PLAN_ID --yes
./factory/factory continue-plan PLAN_ID --mock
./factory/factory review alignment PLAN_ID
./factory/factory approve PLAN_ID --new-project-title "TableStory Workshop"
```

This still creates real worktrees, independent QA commits, protected acceptance
tests, implementation commits, verification output, dependency waves, and local
merges. No part of the control-flow explanation needs to change.

The original failure-oriented TV story remains available:

```sh
./setup_demo.sh --scenario tv --force
./factory/factory run --mock --scenario tv --once
```

Ticket #8 is intentionally rejected by QA because “It feels right” is not
objectively testable.

## Recovery

- `setup_demo.sh` refuses uncommitted `demo-app/` changes unless `--force` is explicit.
- A Blocked or QA Review worktree is preserved for inspection.
- `factory retry ISSUE` resets both QA and implementation attempt state.
- `factory approve-tests ISSUE` writes a small approval marker; a running factory
  notices it on the next poll and resumes the preserved worktree.
- The factory refuses a real run from a dirty or non-default branch and refuses
  to unlock dependants until merged commits are reachable from the synchronized base.
