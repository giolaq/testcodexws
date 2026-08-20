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
| Connect | Select a preset or role adapters; run preflight | Saves `.factory/local.toml` and checks the repository |
| PRD | Review or edit the requirement; start Product Review | Saves a local PRD and runs the first planning expert |
| Planning | Read four expert artifacts; approve the two human gates | Creates PRD-derived rehearsal tickets or GitHub issues |
| Tickets | Run the scheduler; inspect prompts, logs, diffs, tests, gates, and history | Operates isolated worktrees and shows live state |
| Evidence | Complete the Factory Canvas; export the packet | Produces a sanitized review bundle |

Every operation shows the exact equivalent CLI command and streams its output.
The interface runs one command at a time, so two buttons cannot start competing
factory processes.

## Read the overview

The first panel is the operating summary:

- **Current phase** names the active workshop phase and, during execution, the
  ticket and role doing the work—for example independent QA, implementation,
  or verification gates.
- **Next checkpoint** names the next human action and opens the relevant screen.
- **Workshop progress** separates completed, current, and pending phases.
- **Waiting for you** lists approvals and blockers that pause automation.
- **Operation** shows the exact command and its live output. It explains a
  failure until the next command runs.

When the scheduler remains open while waiting for QA approval or a pull-request
merge, the required human decision takes priority over the generic “running”
state.

## Rehearsal and live modes

Choose **Rehearsal** to use deterministic local planning, QA, and implementation.
It requires no model credentials and makes no GitHub Project writes.

Choose **Live** to use the configured agent CLIs and GitHub. In this mode,
GitHub Issues and Projects remain the shared source of truth. The Control Center
is the detailed operator view for the local prompts, worktrees, tests, and logs
that GitHub does not contain.

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

Use **Reset or start again** from the Overview or sidebar for a Rehearsal:

- **Reset current run** restores Pocket Cinema and clears ticket execution,
  worktrees, branches, test approvals, implementation evidence, and run state.
  It keeps the PRD, approved expert plan, Factory Canvas, agents, and Project
  choice, so you can demonstrate the same tickets again.
- **Start workshop over** also clears the saved PRD, expert artifacts, human
  approvals, rehearsal tickets, Canvas, and Evidence Packets. It keeps only the
  attendee's agent and GitHub Project configuration.

Both reset options refuse to overwrite uncommitted `demo-app` changes. Reset is
disabled for Live mode because local cleanup cannot safely undo GitHub issues,
branches, pull requests, or another person's work. Use a fresh repository for a
new Live run.

The original `factory/dashboard.html` remains available as a read-only static
view. Use the Control Center for the workshop path because it includes setup,
human approvals, execution controls, and evidence export.
