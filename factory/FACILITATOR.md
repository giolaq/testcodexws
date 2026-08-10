# Facilitator runbook

## Recommended 80-minute workshop

| Time | Activity | Teaching point |
| --- | --- | --- |
| 0–8 min | Show Pocket Cinema and the target TableStory brief | Agents need an observable product goal. |
| 8–18 min | Run `factory plan recipe-app-prd.md` | The planner proposes work; it does not authorize work. |
| 18–28 min | Review the graph, waves, questions, and acceptance criteria | Humans control scope and dependencies. |
| 28–35 min | Run `factory approve` against a fresh GitHub Project | Tickets become an auditable contract. |
| 35–48 min | Start the first wave with QA review enabled | Independent agents write tests before implementation. |
| 48–58 min | Inspect and approve QA tests | Human control is based on evidence, not trust. |
| 58–68 min | Watch a failure/retry and inspect its log | Verification output becomes the repair prompt. |
| 68–75 min | Merge a PR and watch a dependant unlock | The merged commit is synchronized before reuse. |
| 75–80 min | Reveal TableStory and map extension points | Adapters, models, gates, and runtimes are configurable. |

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
./factory/factory approve .factory/plans/recipe-app-prd-PLAN_ID.json --new-project-title "TableStory Workshop"
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

If only the planning model is unavailable, copy the reviewed fallback plan and
continue with the normal GitHub approval flow:

```sh
cp factory/scenarios/recipe-rebrand/example-plan.json .factory/plans/table-story-fallback.json
./factory/factory approve .factory/plans/table-story-fallback.json --new-project-title "TableStory Workshop"
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
