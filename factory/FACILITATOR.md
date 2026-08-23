# Facilitator runbook

Release: `workshop-v1.1.0`

Use [WORKSHOP_OUTLINE.md](WORKSHOP_OUTLINE.md) for the presentation path and
[COMPATIBILITY.md](COMPATIBILITY.md) for upgrades and migration behavior. This
runbook is the detailed preparation, release, and recovery reference; do not
read it as the attendee script.

Use this runbook to prepare and deliver the 100-minute Software (re)-Factory
workshop. The attendee website contains the full instructions. Your job is to
keep time, make the control points visible, and stop the group when evidence is
weak.

For the first dry run, use a Self-paced Rehearsal Run. It exercises the complete workflow
without GitHub writes or model latency. Demonstrate a Live Run only after the
rehearsal path works from a clean checkout.

## Readiness checklist

Complete this checklist before attendees arrive:

- [ ] macOS, Linux, or WSL 2 is available.
- [ ] Python 3.11 or later includes the `venv` module.
- [ ] Node.js 20 or later and Git are on `PATH`.
- [ ] Ports 5000 and 5050 are free.
- [ ] The presentation browser can open localhost pages.
- [ ] The workshop repository is clean and synchronized with its default branch.
- [ ] A disposable local Git checkout exists for a Rehearsal Run.
- [ ] The deterministic recipe scenario completes successfully.
- [ ] The attendee website is open at the prerequisites section.
- [ ] The frozen source, CLI, website, and Git tag all identify
      `workshop-v1.1.0`.
- [ ] Every attendee will create and own a separate repository. Rehearsal may
      stay local; Live uses GitHub. The facilitator uses a different repository.
- [ ] Peer-review pairs are assigned without sharing repository state.

A Live Run also requires:

- [ ] `gh auth status` succeeds.
- [ ] GitHub authentication includes the `project` scope.
- [ ] The repository owner can create issues, Projects, branches, and pull requests.
- [ ] The repository URL is saved in **Connect** and the repository card says **connected**.
- [ ] A current Claude or Codex planning CLI is authenticated.
- [ ] The selected supervision, implementation, QA, and code-review adapters are registered and their
      noninteractive commands have been smoke-tested. Claude is only the worked
      example; attendees may use their own agent.
- [ ] The selected supervisor adapter is registered and can return the required
      structured dispatch decision noninteractively.
- [ ] If the demo requires formal GitHub approval, `FACTORY_REVIEW_GH_TOKEN`
      belongs to a second account with repository review access.
- [ ] Network access to GitHub and the selected agent provider is stable.

## Prepare the dry run

Create a disposable rehearsal checkout:

```sh
./factory/new_workshop.sh ../software-refactory-rehearsal recipe-rebrand
cd ../software-refactory-rehearsal
```

Run the deterministic preflight and scenario once:

```sh
python3 --version
node --version
git --version
./factory/factory init
# Review factory.project.toml and factory.charter.toml.
./factory/factory approve-charter --yes
./factory/factory doctor
```

Prepare the live checkout only if you plan to demonstrate real agents:

```sh
./factory/new_workshop.sh ../software-refactory-live live
cd ../software-refactory-live
./setup_demo.sh --scenario recipe-rebrand
git push origin main
./factory/factory configure \
  --github-repository "$(gh repo view --json url --jq .url)" \
  --preset claude-workshop
./factory/factory doctor --full
```

Continue only when the doctor reports zero failures. A warning is acceptable
only for an optional adapter that won't be used or for the documented
single-account review-comment fallback.

If a colleague asks whether the factory only works for Pocket Cinema, show the
Project Contract card in Connect. The extension path is:

```sh
./factory/factory init --repo /path/to/existing-project
# Review factory.project.toml in that project.
./factory/factory control-center --repo /path/to/existing-project
```

Explain the boundary plainly: a Live Run accepts any PRD and repository;
Rehearsal is a deterministic TableStory teaching pack. Do not switch the core
exercise to an unfamiliar repository during the 100-minute session.

If the group uses another implementation or QA agent, register it under
`[agents]` in `factory/factory.toml`, then save the attendee defaults with
`factory configure`. Keep Claude or Codex as the structured planning adapter.
The exact contract and wrapper requirements are in `factory/CONFIGURATION.md`.

## Arrange the presentation workspace

Use two terminals:

| Terminal | Keep visible | Purpose |
| --- | --- | --- |
| A | `./factory/factory control-center --no-open` | Local factory server and fallback command output |
| B | Demo application | Pocket Cinema or TableStory |

Prepare these browser tabs:

1. attendee workshop website;
2. `http://127.0.0.1:5050`;
3. `http://localhost:5000`;
4. the disposable GitHub Project for the Live Run; and
5. one pull request for the merge-and-unlock explanation.

Don't start the application before running the live doctor. An occupied port is
reported as a warning.

The Control Center is the attendee path. Keep terminal commands below as a
facilitator recovery reference and to explain that the UI calls the same
versioned CLI. Do not tunnel or publicly expose port 5050.

## Timing and presenter cues

| Time | Attendee action | What to say or show |
| --- | --- | --- |
| 0–5 min | Pass readiness and pair | Confirm separate repositories and identify each peer reviewer. |
| 5–13 min | Define the factory and inspect Pocket Cinema | Teach Plan, Build, Verify, Review; ask what must change besides the logo. |
| 13–20 min | Read the PRD | Identify the user journey, system constraints, and shared-data risk. |
| 20–35 min | Revise Product Review | Reject vague R4 evidence, record feedback, and approve the objective revision. |
| 35–50 min | Trace R3 | Follow R3 across the four planning artifacts. |
| 50–58 min | Align and publish | Show PRD-derived tickets and dependencies in GitHub Projects. |
| 58–68 min | Review Acceptance Tests | Ask whether QA-owned assertions prove behavior before approving them. |
| 68–85 min | Observe the Factory Run | Follow a Supervisor checkpoint, then one ticket through Plan, Build, Verify, automated code review, human Review, and the deterministic retry. |
| 85–91 min | Verify the app | Verify TableStory and preview delivery evidence. |
| 91–98 min | Peer review the Canvas | Attendees review another repository's authority, capacity, evidence, and monitoring choices. |
| 98–100 min | Export and close | Export the Evidence Packet and name one bounded next experiment. |

The schedule is a teaching target, not a guarantee that live model work will
finish. Live agents have no presentation timeout. Narrate observable state
instead of terminating slow work to manufacture a result.

## Rehearsal command path

Run Product Review:

```sh
./factory/factory plan recipe-app-prd.md --mock
./factory/factory review product PLAN_ID
./factory/factory revise PLAN_ID product \
  --feedback "Require automated Escape and Backspace checks that preserve mode=tv and restore focus." \
  --mock
./factory/factory review product PLAN_ID
./factory/factory approve-product PLAN_ID
```

Run and inspect technical planning:

```sh
./factory/factory continue-plan PLAN_ID --mock
./factory/factory review alignment PLAN_ID
./factory/factory approve-rehearsal PLAN_ID --scenario recipe-rebrand
```

Pause after the first QA wave:

```sh
./factory/factory run --mock \
  --scenario recipe-rebrand \
  --review-qa-tests \
  --once
./factory/factory approve-tests 1 --yes
./factory/factory approve-tests 2 --yes
```

Finish the scenario:

```sh
./factory/factory run --mock --scenario recipe-rebrand --once
./factory/factory merge ISSUE_NUMBER --yes
./factory/factory monitor
```

## Live command path

The commands below use Claude as a coherent worked example. If an attendee uses
a different registered implementation or QA adapter, the remaining planning,
GitHub Project, worktree, QA-review, and verification steps stay the same.

```sh
./factory/factory plan recipe-app-prd.md
./factory/factory review product PLAN_ID
./factory/factory revise PLAN_ID product \
  --feedback "Require automated Escape and Backspace checks that preserve mode=tv and restore focus."
./factory/factory review product PLAN_ID
./factory/factory approve-product PLAN_ID
./factory/factory continue-plan PLAN_ID
./factory/factory review alignment PLAN_ID
./factory/factory approve PLAN_ID \
  --new-project-title "TableStory Workshop"
./factory/factory run
```

The approved Vertical Slices artifact is the ticket source. The approval command
creates the issues, adds them to the new Project, and saves its number locally.
Do not seed tickets during the normal path.

Approve a reviewed test set from another terminal:

```sh
./factory/factory approve-tests ISSUE_NUMBER
```

After a green pull request is merged, wait for **PR merged and synchronized**
before showing the next ticket move to Ready.

Demonstrate from the facilitator repository first. If its live run has not
reached the evidence you need, ask a consenting attendee whether you may show
their repository. If neither is ready, teach from the visible current state;
record missing evidence and complete it after the session.

## Evidence to show for one ticket

Don't click through every field. Use one ticket to show this sequence:

1. **Specification:** the authorized outcome and acceptance criteria.
2. **QA prompt and test diff:** independent evidence written before implementation.
3. **Protected test hashes:** the implementation agent can't weaken the evidence.
4. **Implementation prompt and log:** the current scope and activity.
5. **Changed files:** the code-review surface.
6. **Gate output:** the reason for pass, retry, or block.
7. **Supervisor decision:** the worker reports it read, the Ticket instruction
   it proposed, and the orchestrator's validated dispatch.
8. **Code review evidence:** the candidate commit, `APPROVE` or
   `REQUEST_CHANGES` decision, changed-path comments, and GitHub publication
   mode. On Ticket #1, show the first comment and the repaired second revision.
9. **Merge evidence:** the Supervisor's `MERGE` recommendation must name the
   same PR and commit that the Code Review Agent approved. In the Standard
   path, show the human exact-revision merge decision that follows it.
10. **Handoff Receipts:** the revisions, claim, verification, risks, and policy
   hashes behind each role transition.
11. **History:** merge synchronization and dependency unlock.

Use GitHub Projects for shared backlog ownership and dependencies. Use the
Control Center for local prompts, logs, worktree changes, protected tests,
gate results, and receipts. Do not describe the Control Center as a hosted
Project board.

Use the Supervisor screen to make authority explicit. Ticket agents report
results through Handoff Receipts. The Agent Supervisor recommends the next
bounded wave. The orchestrator validates and applies allowed commands. Humans
still approve Product Review, alignment, and Acceptance Tests when configured.
The Code Review Agent approves an exact candidate or requests changes but cannot
edit or merge. After approval, the Supervisor may recommend merge. The
orchestrator rechecks the PR revision, then Lean, Standard, and Assured wait for
a human decision. Only an explicitly opted-in Autonomous Demo executes the
Supervisor recommendation automatically.

GitHub does not allow the account that authored a PR to formally approve it.
With one workshop identity, point out the labelled Factory comment and explain
that it does not satisfy branch protection. A repository requiring formal
approval needs a distinct reviewer identity supplied through the uncommitted
`FACTORY_REVIEW_GH_TOKEN` environment variable.

## Recovery during the session

| Symptom | Response |
| --- | --- |
| GitHub, Wi-Fi, or a model is slow | Switch to the deterministic recipe scenario. |
| Product Review is blocked | Resolve the blocking question; don't continue to architecture. |
| A planning retry repeats the same error | Read the failed expert's recovery card. For validation, use the prefilled **Apply correction and continue** instruction. For a session or rate limit, select **Fix with Codex** (or another configured adapter). After the same process failure occurs twice, the Control Center disables same-agent retry and preserves completed upstream artifacts. If governance changed, use **Restart planning safely**. |
| QA Review takes too long | Review one test set, then finish without `--review-qa-tests`. |
| A ticket is blocked | Inspect the final log and gate output before using `factory retry`. |
| A port is occupied | Stop the old process or use a fresh checkout. |
| The state is stale | Use **Reset current run** in the Control Center after confirming demo changes can be discarded. |
| The agenda is late | Show one Acceptance Test approval and one dependency unlock, then verify the application. |

If GitHub works but live planning cannot finish, use
`./factory/factory seed recipe-rebrand` as a last-resort fixture. Tell attendees
that it bypasses PRD planning and both human alignment gates.

Reset a disposable rehearsal only when its demo changes can be discarded. The
Control Center offers two scopes: reset execution while keeping the approved
plan, or type `START OVER` to clear all workshop work while keeping attendee
configuration. The equivalent execution reset is:

```sh
./setup_demo.sh --scenario recipe-rebrand --force
```

The TV scenario remains available as an optional failure lab. Ticket 8 is
rejected because “It feels right” isn't an objective acceptance criterion.

## Dry-run acceptance criteria

The workshop is ready when a colleague can use the website without verbal help
to:

- select a path and verify its prerequisites;
- reach every checkpoint using the Control Center, with equivalent commands available;
- find the ticket board, ticket evidence, and troubleshooting section;
- explain the required Product Review and alignment approvals, any
  Charter-selected intermediate planning approvals, and the Acceptance Test
  approval;
- explain one dependency unlock;
- complete and peer review a Factory Canvas;
- export a sanitized Evidence Packet; and
- choose which Factory Profile addresses a concrete delivery risk.

## Freeze and publish the workshop

The repository remains private until the owner runs the complete rehearsal and
release audit. The day before delivery:

```sh
./factory/factory --version
python3 -m unittest discover -s factory/tests
npm --prefix workshop-guide test
npm --prefix workshop-guide run lint
./factory/factory release-check
./factory/factory release-check --rehearsal
```

The website suite includes structural accessibility checks; the release audit
checks participant links and possible secrets. The rehearsal release check
executes the complete Standard journey in a clean clone. Verify the deployed
website separately. In a dedicated disposable GitHub repository with Claude
authenticated, also run the golden-path smoke below. It creates a fresh
Project, uses Claude for planning, QA, implementation, and supervision,
deterministically sends one Code Review comment back to the same PR, and merges
the repaired Ticket:

```sh
./factory/factory release-check --live-smoke \
  --confirm-disposable-repo
```

After all checks pass, tag `workshop-v1.1.0`, make the repository public, and
enable GitHub template mode. Those external owner actions are intentionally not
automated by the factory.
