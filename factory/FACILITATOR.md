# Facilitator runbook

Use this runbook to prepare and deliver the 100-minute Software (re)-Factory
workshop. The attendee website contains the full instructions. Your job is to
keep time, make the control points visible, and stop the group when evidence is
weak.

For the first dry run, use rehearsal mode. It exercises the complete workflow
without GitHub writes or model latency. Demonstrate live mode only after the
rehearsal path works from a clean checkout.

## Readiness checklist

Complete this checklist before attendees arrive:

- [ ] macOS, Linux, or WSL 2 is available.
- [ ] Python 3.11 or later includes the `venv` module.
- [ ] Node.js 20 or later and Git are on `PATH`.
- [ ] Ports 5000, 5050, and 8000 are free.
- [ ] The presentation browser can open localhost pages.
- [ ] The workshop repository is clean and synchronized with its default branch.
- [ ] A disposable checkout exists for rehearsal mode.
- [ ] A second checkout or the sample report is ready for the lights-off control.
- [ ] The deterministic recipe scenario completes successfully.
- [ ] The attendee website is open at the prerequisites section.

Live mode also requires:

- [ ] `gh auth status` succeeds.
- [ ] GitHub authentication includes the `project` scope.
- [ ] The repository owner can create issues, Projects, branches, and pull requests.
- [ ] A current Claude Code CLI is authenticated. No API key is required.
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
./factory/factory run --mock --scenario recipe-rebrand --dry-run
```

Prepare the live checkout only if you plan to demonstrate real agents:

```sh
./factory/new_workshop.sh ../software-refactory-live live
cd ../software-refactory-live
./setup_demo.sh --scenario recipe-rebrand
git push origin main
./factory/factory configure --preset claude-workshop
./factory/factory doctor --full
```

Continue only when the doctor reports zero failures. A warning is acceptable
only for an optional adapter that won't be used.

Prepare a separate control checkout:

```sh
./factory/new_workshop.sh ../software-refactory-control recipe-rebrand
cd ../software-refactory-control
git switch -c experiment/lights-off
```

If a live control isn't practical, keep
`factory/scenarios/recipe-rebrand/lights-off-sample-report.md` open. Always call
it a discussion fixture, not a benchmark.

## Arrange the presentation workspace

Use four terminals:

| Terminal | Keep visible | Purpose |
| --- | --- | --- |
| A | Factory checkout | Planning and factory commands |
| B | `python3 -m http.server 8000` | Dashboard server |
| C | Control checkout | One autonomous agent |
| D | Demo application | Pocket Cinema or TableStory |

Prepare these browser tabs:

1. attendee workshop website;
2. `http://localhost:8000/factory/dashboard.html`;
3. `http://localhost:5000`;
4. the disposable GitHub Project for live mode; and
5. one pull request for the merge-and-unlock explanation.

Don't start the application before running the live doctor. An occupied port is
reported as a warning.

## Timing and presenter cues

| Time | Attendee action | What to say or show |
| --- | --- | --- |
| 0–8 min | Set up the selected mode | Point to the prerequisite list and required readiness result. |
| 8–13 min | Inspect Pocket Cinema | Ask what must change besides the logo, then stop the server. |
| 13–20 min | Read the PRD | Identify the user journey, system constraints, and shared-data risk. |
| 20–32 min | Start the control | Explain that the model and task stay fixed; only the workflow changes. |
| 32–44 min | Review Product Review | Reject ambiguous behavior before technical planning begins. |
| 44–59 min | Review technical alignment | Trace one requirement through architecture, program design, slice, and QA evidence. |
| 59–69 min | Review QA tests | Ask whether the assertions prove behavior before approving them. |
| 69–89 min | Observe implementation | Follow one ticket through prompt, log, diff, gate, merge, and dependency unlock. |
| 89–100 min | Compare both results | Compare review effort and evidence, not just whether the app works. |

## Rehearsal command path

Run Product Review:

```sh
./factory/factory plan recipe-app-prd.md --mock
./factory/factory review product PLAN_ID
./factory/factory approve-product PLAN_ID
```

Run and inspect technical planning:

```sh
./factory/factory continue-plan PLAN_ID --mock
./factory/factory review alignment PLAN_ID
./factory/factory run --mock --scenario recipe-rebrand --dry-run
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
```

## Live command path

Start the control in Terminal C and don't intervene:

```sh
python3 factory/run_lights_off.py --agent claude
```

Return to Terminal A:

```sh
./factory/factory plan recipe-app-prd.md
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

## Evidence to show for one ticket

Don't click through every field. Use one ticket to show this sequence:

1. **Specification:** the authorized outcome and acceptance criteria.
2. **QA prompt and test diff:** independent evidence written before implementation.
3. **Protected test hashes:** the implementation agent can't weaken the evidence.
4. **Implementation prompt and log:** the current scope and activity.
5. **Changed files:** the code-review surface.
6. **Gate output:** the reason for pass, retry, or block.
7. **History:** merge synchronization and dependency unlock.

## Recovery during the session

| Symptom | Response |
| --- | --- |
| GitHub, Wi-Fi, or a model is slow | Switch to the deterministic recipe scenario. |
| Product Review is blocked | Resolve the blocking question; don't continue to architecture. |
| QA Review takes too long | Review one test set, then finish without `--review-qa-tests`. |
| A ticket is blocked | Inspect the final log and gate output before using `factory retry`. |
| A port is occupied | Stop the old process or use a fresh checkout. |
| The state is stale | Reset only after confirming demo changes can be discarded. |
| The agenda is late | Show one QA approval and one dependency unlock, then move to comparison. |

If GitHub works but live planning cannot finish, use
`./factory/factory seed recipe-rebrand` as a last-resort fixture. Tell attendees
that it bypasses PRD planning and both human alignment gates.

Reset a disposable rehearsal only when its demo changes can be discarded:

```sh
./setup_demo.sh --scenario recipe-rebrand --force
```

The TV scenario remains available as an optional failure lab. Ticket 8 is
rejected because “It feels right” isn't an objective acceptance criterion.

## Dry-run acceptance criteria

The workshop is ready when a colleague can use the website without verbal help
to:

- select a mode and verify its prerequisites;
- reach every checkpoint using the displayed commands;
- find the dashboard, ticket evidence, and troubleshooting section;
- explain the two human planning approvals and the QA approval;
- explain one dependency unlock; and
- compare the control and factory without assuming the control must fail.
