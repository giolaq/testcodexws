# Facilitator runbook

## Recommended 100-minute workshop

| Time | Activity | Teaching point |
| --- | --- | --- |
| 0–8 min | Show Pocket Cinema and the target TableStory brief | Agents need an observable product goal. |
| 8–18 min | Run Product Review and inspect behavior, scope, and mockup needs | Product intent becomes an explicit contract. |
| 18–23 min | Approve product, then run the three technical experts | Technical planning cannot outrun product agreement. |
| 23–38 min | Review architecture, program design, slices, and traceability | Thirty minutes of alignment replaces hours of code review. |
| 38–45 min | Approve alignment into a fresh GitHub Project | Tickets become an auditable contract. |
| 45–60 min | Start the first wave with QA review enabled | Independent agents write tests before implementation. |
| 60–70 min | Inspect and approve QA tests | Human control is based on evidence, not trust. |
| 70–82 min | Watch a failure/retry and inspect its log | Verification output becomes the repair prompt. |
| 82–92 min | Merge a PR and watch a dependant unlock | The merged commit is synchronized before reuse. |
| 92–100 min | Reveal TableStory and map extension points | Agents, models, gates, and runtimes are configurable. |

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

3. In a second terminal, prepare the deterministic fallback without leaving the
   live checkout in the first terminal:

   ```sh
   ./factory/new_workshop.sh ../software-refactory-fallback recipe-rebrand
   cd ../software-refactory-fallback
   ./factory/factory run --mock --scenario recipe-rebrand --dry-run
   ```

4. Serve the board from the repository root:

   ```sh
   python3 -m http.server 8000
   ```

   Open `http://localhost:8000/factory/dashboard.html` on the presentation display.

5. For live agents, run a smoke prompt through every CLI you will offer. Confirm
   `gh auth status` shows the `project` scope.

6. Use `factory approve --new-project-title "TableStory Workshop"` rather than
   reusing the previous TV rehearsal board. Note the printed number and pass it
   to `factory run`.

## Live commands

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
