# Factory Control Center

The Control Center is the local operator interface for the Software
(re)-Factory. It turns the normal PRD-to-evidence workflow into a guided web
experience while keeping the CLI as the execution layer.

Start it from the workshop repository:

```sh
./factory/factory control-center
```

It opens <http://127.0.0.1:5050>. Keep that terminal running during the
workshop. Press `Ctrl+C` to close the server.

## What attendees do

| Screen | Attendee action | Factory result |
| --- | --- | --- |
| Connect | Inspect or create the Project Contract and Factory Charter; select role adapters; run setup and preflight | Saves repository behavior, records human-owned policy approval, and checks the target |
| PRD | Review or edit the requirement; start Product Review | Saves a local PRD and runs the first planning expert |
| Planning | Read four expert artifacts; approve the two human gates | Creates PRD-derived rehearsal tickets or GitHub issues |
| Tickets | Run the scheduler; inspect prompts, logs, diffs, tests, gates, code review, and history | Operates isolated worktrees and shows live state |
| Supervisor | Inspect worker reports, dispatch instructions, blocks, merge recommendations, and prior decisions | Explains how the next safe Ticket wave and approved revision were coordinated |
| Evidence | Complete the Factory Canvas; export the packet | Produces a sanitized review bundle |
| Monitor | Preview read-only health findings; publish only by explicit Live action | Finds stale claims, waits, drift, CI, and advisories without repairing code |

Every operation shows the exact equivalent CLI command and streams its output.
The interface runs one command at a time, so two buttons cannot start competing
factory processes.

If a planning expert cannot make a product or technical decision safely, its
card shows each blocking question with an answer field. Answer every question
and select **Submit decisions**. For System Architecture, Program Design, and
Vertical Slices, the Control Center records the answers, preserves the previous
artifact, reruns only that expert, and resumes downstream planning. Product
Review returns to its human approval gate after revision. A blind retry remains
available only for operational failures that did not produce blocking questions.

If an expert returns schema-valid JSON that fails deterministic cross-artifact
validation, the failed expert card shows the exact validator message and the
preserved rejected artifact. Enter a concrete correction, then select **Apply
correction and continue**. The rejected artifact becomes the revision source;
the factory records the human instruction, reuses every approved upstream
artifact, validates the replacement, and resumes only after it passes. The
correction field starts with the exact validator failure, so the attendee can
apply or refine a concrete repair without reconstructing the error. Each failed
replacement remains available as evidence.

Agent-process failures are classified separately. A session or rate limit does
not expose a same-adapter retry because that would repeat the same failure;
choose another configured Claude or Codex adapter, or wait for the provider to
become available. Authentication and missing-tool failures point to preflight.
Only an unclassified, potentially transient process failure offers **Retry same
adapter**. Adapter changes are recorded in the manifest, valid upstream
artifacts remain unchanged, and only the failed and downstream stages rerun.

Use the three recovery actions deliberately:

- **Retry same adapter** is available only for an otherwise-unclassified,
  potentially transient process failure.
- **Switch adapter and continue** recovers from provider capacity or
  availability without discarding approved upstream artifacts.
- **Apply correction and continue** revises a rejected artifact with a recorded
  human instruction when deterministic validation would otherwise repeat.
- **Restart planning safely** creates a governed run from the saved PRD when
  the PRD, Project Contract, or Factory Charter changed. The old run remains
  evidence and no GitHub Ticket is rewritten silently.

After verification, open the Ticket's **Code review** tab. It shows the
reviewer adapter, candidate commit, `APPROVE` or `REQUEST_CHANGES` decision,
file-and-line comments, publication mode, and structured review artifact.
`REQUEST_CHANGES` returns the comments to implementation; the same PR is updated,
gates rerun, and the new revision is reviewed. `APPROVE` enables a revision-bound
Supervisor recommendation. In Lean, Standard, and Assured, a person must inspect
that exact revision and choose whether to merge it. The Code Review Agent does
not edit or merge.

## Inspect the Agent Supervisor

Standard and Assured Factory Profiles use a supervisor before each dispatch
wave. Ticket roles do not message one another or change the board directly.
They finish their assignment, and the orchestrator records the result as a
Handoff Receipt. At the next checkpoint the supervisor receives:

- every dependency-ready Ticket and the configured parallel limit;
- the current Ticket and dependency state; and
- recent QA, implementation, verification, and review Handoff Receipts.

At a dispatch checkpoint, the supervisor can propose only two commands: dispatch
a ready Ticket with a short coordination instruction, or block it with an
explicit reason. After code-review approval, it has a separate `MERGE` or `BLOCK`
contract tied to the PR and candidate head. The
orchestrator rejects unavailable Tickets, duplicate or conflicting commands,
excess parallelism, malformed output, and silent stalls. It then applies valid
commands and remains the lifecycle authority. Before merge, it also confirms
that gates pass, the decision was published, and the live PR head still matches.

Open **Supervisor** while a run is active. Read the latest summary from top to
bottom: worker reports, dispatch/block/defer decisions, Ticket instructions,
and the prompt and log used for that checkpoint. Open a Ticket's **Supervisor**
tab to connect its instruction with its later worker receipts. The deterministic
Rehearsal Supervisor makes the same contract visible without credentials.

## Read the overview

The first panel is the operating summary:

- **Current phase** names the active workshop phase and, during execution, the
  ticket and role doing the work—for example independent QA, implementation,
  verification gates, code review, or merge synchronization.
- **Next checkpoint** names the next action or inspection point and opens the relevant screen.
- **Workshop progress** separates completed, current, and pending phases.
- **Waiting for you** lists approvals and blockers that pause automation.
- **Operation** shows the exact command and its live output. It explains a
  failure until the next command runs.

When the scheduler remains open while waiting for QA approval, that required
human decision takes priority over the generic “running” state. During an
Autonomous Demo merge, the exact review and Supervisor evidence remains
inspectable. Other profiles stop at a visible human merge decision.

## Rehearsal and live modes

Choose **Rehearsal** to use deterministic local planning, supervision, QA,
implementation, verification, and code review.
It requires no model credentials and makes no GitHub Project writes.
Its preflight checks the local repository and workshop tools without calling an
agent CLI.

Choose **Live** to use the configured agent CLIs and GitHub. In this mode,
GitHub Issues and Projects remain the shared source of truth. The Control Center
is the detailed operator view for the local prompts, worktrees, tests, and logs
that GitHub does not contain. Live preflight also verifies agent authentication
and runs the configured gates.

In **Connect**, paste the attendee's GitHub repository URL before saving Live
configuration. Saving verifies access, clones or reuses that repository under
the Control Center's ignored `.factory/repositories/` workspace, and switches
the interface to that checkout. The repository card must show **connected**
before preflight. The factory never rewrites the factory source checkout's
`origin`, and it uses the saved target explicitly even if `gh` has a different
default repository.

### Open an existing local checkout

The URL workflow above is the normal path. To use an existing local checkout
instead, pass it when starting the Control Center:

```sh
./factory/factory control-center --repo /path/to/your-project
```

The Project Contract card shows detected source roots, test roots, and gates.
Select **Create contract and Charter**, review `factory.project.toml` and the
exact `factory.charter.toml` policy, then select **Approve exact Charter**.
**Commit and push setup** publishes only those two governance files and
`.gitignore`; it refuses unrelated working-tree changes. Then select **Run
setup** only if its commands are correct; review and commit any intentional
lockfile change. Full
preflight verifies the committed contract, tools, GitHub target, default branch,
agent authentication, and gates before a Live run.

The PRD editor accepts any product requirement. Live planning combines its
scope with this contract and a bounded repository inventory. Rehearsal planning
uses the bundled TableStory fixture and is not a generic implementation mode.

## Safety boundary

The Control Center is intentionally local and unauthenticated:

- It binds only to `127.0.0.1` or `localhost`.
- It accepts only same-machine browser requests.
- It exposes a fixed list of factory actions, never arbitrary shell commands.
- It passes arguments directly to the existing CLI without a shell.
- It opens only allowlisted files under `.factory`; configuration and
  credentials are not readable through the browser.
- Agent credentials stay in the selected CLI's normal credential store.

Do not expose port 5050 through a tunnel, reverse proxy, container port, or
public deployment. The hosted workshop guide explains the exercise; the
Control Center operates a local repository and therefore stays on the attendee's
machine.

## Recovery

If an action fails, read the operation output first. The same command is shown
above it, so you can copy it into a terminal when deeper diagnosis is useful.

If an agent is still running, select **Stop operation**. A later Factory Run
recovers interrupted ticket work through the normal orchestrator logic. Use the
ticket History and Live log tabs to find the recorded blocker, then use
**Retry ticket** after the cause is fixed.

Use **Reset or start again** from the Overview or sidebar:

- **Reset current run** restores Pocket Cinema and clears ticket execution,
  worktrees, branches, test approvals, implementation evidence, and run state.
  It keeps the PRD, approved expert plan, Factory Canvas, agents, and Project
  choice, so you can demonstrate the same tickets again.
- **Start workshop over** also clears the saved PRD, expert artifacts, human
  approvals, rehearsal tickets, Canvas, and Evidence Packets. It keeps only the
  attendee's agent and GitHub Project configuration.

The workshop Project Contract delegates Rehearsal reset to its reviewed Pocket
Cinema adapter, which refuses to overwrite uncommitted `demo-app` changes. For
a Live Run, reset bypasses every repository adapter and clears only `.factory`
runtime state and factory-owned worktrees. It does not change tracked source,
switch modes, or delete GitHub issues, Projects, branches, or pull requests.

The Control Center is the supported workshop dashboard. Compatibility and
migration behavior are documented in `COMPATIBILITY.md`.
