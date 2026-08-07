# Software (re)-Factory

Software (re)-Factory is a legible control layer for running several coding
agents against a dependency-mapped backlog. GitHub Issues are tickets, Projects
v2 is the audited board, Git worktrees isolate changes, and ordered gates decide
whether a ticket is retried, reviewed, or blocked. The included Pocket Cinema
app makes the refactor visible: eight tickets turn a mobile film browser into a
keyboard-driven TV experience.

## One-minute mock quickstart

Mock mode needs Python 3.11+, Git, Node 20+, and no credentials or agent tokens.

```sh
./setup_demo.sh
./factory/factory run --mock --once
./factory/factory status
```

In another terminal, serve the live board:

```sh
python3 -m http.server 8000
```

Open <http://localhost:8000/factory/dashboard.html>. The rehearsal runs tickets
in dependency waves, performs real Git worktree isolation and real verification,
merges seven tickets locally, exercises the merge-conflict handling story, and
blocks only the deliberately vague ticket #8 after its retries.

To use the shorter `factory run` spelling during a workshop:

```sh
export PATH="$PWD/factory:$PATH"
factory run --mock --once
```

Reset between sessions with `./setup_demo.sh`. It removes only rehearsal
worktrees and `factory/*` branches, restores `demo-app/` from the baseline tag,
and clears runtime state. A Blocked worktree is otherwise preserved for review.

## What attendees can read in one sitting

`orchestrator.py` is the complete pipeline and stays close to 400 lines. Its
flow is intentionally direct:

1. Load issues and parse `Depends-on: #…` plus `agent: …` from each body.
2. Move dependency-complete, `agent-ready` tickets to Ready.
3. Create `../wt-<issue>` on `factory/<issue>-<slug>` and run its agent adapter.
4. Execute configured gates in order; feed the last 3,000 failure characters
   back to the agent for up to two retries.
5. On green gates, push and open a PR. Humans merge; the next poll marks Done.
6. Mirror every transition to `.factory/state.json` for the two-second dashboard.

The ticket backend is isolated in `github_backend.py`; adapter commands and gates
are all in `factory.toml`. That makes swapping a CLI, model wrapper, remote
execution command, test suite, or lint policy a small workshop-2 exercise.

## Start from an attendee PRD

Copy `factory/PRD_TEMPLATE.md`, fill it in, then ask the read-only planning agent
to turn it into a dependency-mapped proposal:

```sh
cp factory/PRD_TEMPLATE.md workshop-prd.md
# Edit workshop-prd.md
./factory/factory plan workshop-prd.md
```

The command uses the authenticated Codex CLI but gives it a read-only sandbox.
It creates two local files under `.factory/plans/`:

- JSON is the editable source of truth.
- Markdown is the readable review sheet for the attendee and facilitator.

The plan contains stable ticket keys, specs, testable acceptance criteria,
dependencies, agent choices, and explicit open questions. Nothing is sent to
GitHub and no implementation agent starts during planning.

Review both files. Edit the JSON to split, combine, rewrite, or reorder tickets.
Resolve and remove every `open_questions` entry, then approve the JSON plan:

```sh
./factory/factory approve .factory/plans/workshop-prd-PLAN_ID.json
```

The factory validates references and cycles, prints the complete plan, and asks
the human to type `APPROVE`. Only then does it create or update GitHub Issues,
translate plan dependencies into real issue numbers, add them to the Projects
board, and set dependency-free tickets Ready. Approval is idempotent: rerunning
the same plan updates its marked issues instead of duplicating them.

Inspect the GitHub board, then deliberately start implementation:

```sh
./factory/factory run --agent codex --max-parallel 4
```

## Real GitHub and agent mode

Use a clean GitHub repository. If this checkout is not connected to GitHub yet,
create and attach a private repository first (choose your own repository name):

```sh
gh repo create software-refactory-workshop --private --source=. --remote=origin --push
```

Then authenticate the GitHub CLI with Projects permission and seed the backlog:

```sh
gh auth login
gh auth refresh -s project
python3 factory/seed_github.py --agent codex
./factory/factory run --agent codex --max-parallel 4
```

You can seed an existing repository before attaching a remote by identifying it
explicitly:

```sh
python3 factory/seed_github.py --agent codex --github-repo OWNER/REPOSITORY
```

The factory itself pushes ticket branches, so attach that repository as `origin`
before `factory run`:

```sh
git remote add origin https://github.com/OWNER/REPOSITORY.git
./factory/factory run --agent codex
```

The first run creates or reuses a **Software (re)-Factory** Projects v2 project,
normalizes its Status options, adds the issues, mirrors state labels, and opens
PRs after required gates pass. Supply `--project-number N` to use an existing
project. Use `--once` for one scheduler sweep; without it, the factory polls for
newly merged PRs every 20 seconds.

Run a no-write dependency preview before dispatch:

```sh
./factory/factory run --dry-run --agent codex
```

When a ticket is Blocked, edit its issue spec or acceptance criteria and then:

```sh
./factory/factory retry 8
```

Per-ticket `agent: claude`, `agent: codex`, or `agent: cursor` overrides the
default. Before a live session, smoke-test each installed CLI because flags can
change; update only its template in `factory.toml` if needed.

For Codex, the factory selects a current CLI with a valid saved ChatGPT login
and skips legacy `codex` executables that only support `OPENAI_API_KEY`. On
macOS it also checks the CLI bundled with the ChatGPT app. Override discovery
when needed:

```sh
export FACTORY_CODEX_BIN=/path/to/current/codex
"$FACTORY_CODEX_BIN" login status
```

## Pocket Cinema payoff

Before the run, start the mobile baseline with:

```sh
.factory/venv/bin/python demo-app/app.py
```

After the seven successful mock merges, open <http://localhost:5000/?mode=tv>.
Use arrow keys and Enter on the home rails, then Escape or Backspace in film
details. The data and gradient poster artwork are bundled and fictional, so the
demo works offline.

## Operator reference

```text
factory run [--repo PATH] [--agent NAME] [--max-parallel N]
            [--project-number N] [--once] [--dry-run] [--mock]
factory plan PRD.md [--output PLAN.json] [--default-agent NAME]
                    [--min-tickets N] [--max-tickets N]
factory approve PLAN.json [--project-number N] [--yes]
factory status [--repo PATH]
factory retry ISSUE [--repo PATH] [--project-number N] [--mock]
```

Runtime artifacts are under `.factory/`: `state.json`, prompts, and one log per
ticket attempt. Required gate failure blocks progress; optional gate failure is
recorded in the ticket's `warnings`. Killing and restarting the loop replays an
interrupted active ticket from a clean worktree and reuses any already-open PR.

See `FACILITATOR.md` for the live-demo sequence and recovery notes.
