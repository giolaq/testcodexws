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

The original `factory/dashboard.html` remains available as a read-only static
view. Use the Control Center for the workshop path because it includes setup,
human approvals, execution controls, and evidence export.
