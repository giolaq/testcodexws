# Software (re)-Factory

Software (re)-Factory is a legible control layer for running several coding
agents against a dependency-mapped backlog. GitHub Issues are tickets, Projects
v2 is the audited board, Git worktrees isolate changes, and ordered gates decide
whether a ticket is retried, reviewed, or blocked. Two deterministic scenarios
make the factory visible: the main five-ticket exercise rebrands Pocket Cinema
as the TableStory recipe app, while an eight-ticket TV exercise demonstrates a
deliberately blocked requirement.

## One-minute mock quickstart

Mock mode needs Python 3.11+, Git, Node 20+, and no credentials or agent tokens.

```sh
./setup_demo.sh --scenario recipe-rebrand
./factory/factory run --mock --scenario recipe-rebrand --once
./factory/factory status
```

In another terminal, serve the live board:

```sh
python3 -m http.server 8000
```

Open <http://localhost:8000/factory/dashboard.html>. Mock mode now exercises the
same independent-QA commit and protected-test policy as real mode without using
credentials. The `recipe-rebrand` scenario runs five deterministic TableStory
tickets; the original `tv` scenario merges seven tickets and deliberately blocks
the vague eighth ticket.

To use the shorter `factory run` spelling during a workshop:

```sh
export PATH="$PWD/factory:$PATH"
factory run --mock --scenario recipe-rebrand --once
```

Reset between sessions with `./setup_demo.sh --scenario recipe-rebrand`. It
removes only rehearsal worktrees and `factory/*` branches, restores `demo-app/`
from the baseline tag, and clears runtime state. It refuses to overwrite
uncommitted `demo-app/` changes unless `--force` is supplied. A Blocked
worktree is otherwise preserved for review.

The `factory-baseline` tag must name the mobile workpiece — the
`chore: establish factory workshop baseline` commit. Setup repoints the tag
automatically and `factory doctor` fails if it drifts onto a finished
rehearsal, because a baseline carrying rehearsal-era tests grades fresh
tickets against a product they replaced and stalls every scenario. Push the
tag so clones inherit it:

```sh
git push origin factory-baseline
```

A checkout with no history for that commit (a downloaded archive rather than a
clone) cannot be repaired locally; clone from `origin` instead.

## Architecture tour

Start with `ARCHITECTURE.md`, which maps the runtime into a short reading path.
The orchestration flow is intentionally direct:

1. Load issues and parse `Depends-on: #…` plus `agent: …` from each body.
2. Move dependency-complete, `agent-ready` tickets to Ready.
3. Create `../wt-<issue>` on `factory/<issue>-<slug>` and ask the independent
   QA agent to add ticket-numbered acceptance tests only.
4. Commit and protect the QA tests; optionally pause for explicit human test approval.
5. Run the implementation agent. The factory rejects any implementation that
   modifies or deletes a protected test.
6. Execute configured gates in order; feed the last 3,000 failure characters
   back to the agent for up to two retries.
7. On green gates, push and open a PR. Humans merge; the factory fast-forwards
   the default branch and verifies the merge commit before unlocking dependants.
8. Mirror every transition and artifact path to `.factory/state.json` for the dashboard.

The ticket backend is isolated in `github_backend.py`; adapter commands and gates
are all in `factory.toml`. That makes swapping a CLI, model wrapper, remote
execution command, test suite, or lint policy a small workshop-2 exercise.

## Preflight every live session

Run the doctor before attendees create or execute tickets:

```sh
./factory/factory doctor --agent codex --qa-agent codex
./factory/factory doctor --full --agent codex --qa-agent codex
```

It checks repository safety and synchronization, GitHub authentication and
Projects scope, Python/Node and the virtual environment, agent CLIs, ports,
baseline data, configuration, and optionally the complete test suite.

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
dependencies, agent choices, explicit open questions, a Mermaid dependency
graph, and the parallel execution waves. Nothing is sent to GitHub and no
implementation agent starts during planning.

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

For a clean workshop board, create one during approval:

```sh
./factory/factory approve PLAN.json --new-project-title "TableStory Workshop"
```

Inspect the GitHub board, then deliberately start implementation:

```sh
./factory/factory run --agent codex --max-parallel 4
```

## Independent QA acceptance-test phase

Real factory runs use a dedicated QA agent before the implementation agent for
every ticket. The default is Codex and can be changed in `factory/factory.toml`:

```toml
[qa]
agent = "codex"
max_retries = 1
require_human_approval = false
test_roots = ["demo-app/tests", "demo-app/static/tests"]
```

You can select a different QA CLI for one run or disable the phase explicitly:

```sh
./factory/factory run --agent codex --qa-agent claude --max-parallel 4
./factory/factory run --agent codex --no-qa --max-parallel 4
./factory/factory run --agent codex --review-qa-tests
```

For each issue, QA receives the full spec and acceptance criteria. It may only
add new files named `test_ticket_ISSUE[_topic].py` or
`ticket-ISSUE[-topic].test.js` inside the configured test roots. The factory
commits those files before implementation and records their Git blob hashes.
The implementation agent sees the protected-file list in its prompt and may add
more tests, but changing, renaming, or deleting a QA test fails verification and
is fed back into the normal retry loop.

With `--review-qa-tests`, a ticket pauses in **QA Review**. Inspect its test diff
from the dashboard or terminal, then continue it explicitly:

```sh
./factory/factory approve-tests ISSUE
```

QA prompts and logs are separate from implementation artifacts:

```text
.factory/prompts/ISSUE-qa-attemptN.md
.factory/logs/ISSUE-qa-attemptN.log
```

Mock rehearsal uses `mock_qa_agent.py`, so QA commits and protected-test checks
remain credential-free and deterministic. Passing `--qa-agent` explicitly with
`--mock` opts into a real QA CLI instead.

## Disposable attendee checkout

Avoid resetting an attendee's working repository by creating a disposable clone:

```sh
./factory/new_workshop.sh ../software-refactory-attendee live
```

The command refuses an existing destination and clones `origin`. Use `live` for
a synchronized real-agent checkout, or `tv`/`recipe-rebrand` to prepare a local
mock rehearsal from the tagged baseline.

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
python3 factory/seed_github.py --agent codex --scenario recipe-rebrand
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

## Product payoff

The default recipe rehearsal finishes with a responsive, offline TableStory
app. Start it with:

```sh
.factory/venv/bin/python demo-app/app.py
```

Open <http://localhost:5000/> for the recipe browser and
<http://localhost:5000/?mode=tv> for its keyboard-driven TV presentation.

To rehearse the original Pocket Cinema TV story instead, reset and run:

```sh
./setup_demo.sh --scenario tv --force
./factory/factory run --mock --scenario tv --once
```

Before that run, the mobile baseline starts with:

```sh
.factory/venv/bin/python demo-app/app.py
```

After the seven successful mock merges, open <http://localhost:5000/?mode=tv>.
Use arrow keys and Enter on the home rails, then Escape or Backspace in film
details. The data and gradient poster artwork are bundled and fictional, so the
demo works offline.

## Operator reference

```text
factory run [--repo PATH] [--agent NAME] [--qa-agent NAME] [--no-qa]
            [--review-qa-tests] [--scenario tv|recipe-rebrand]
            [--max-parallel N]
            [--project-number N] [--once] [--dry-run] [--mock]
factory plan PRD.md [--output PLAN.json] [--default-agent NAME]
                    [--min-tickets N] [--max-tickets N]
factory approve PLAN.json [--project-number N] [--new-project-title TITLE] [--yes]
factory approve-tests ISSUE [--yes]
factory status [--repo PATH]
factory retry ISSUE [--repo PATH] [--project-number N] [--mock]
factory doctor [--repo PATH] [--full] [--agent NAME] [--qa-agent NAME]
```

Runtime artifacts are under `.factory/`: `state.json`, QA and implementation
prompts, and one log per phase attempt. Required gate failure blocks progress;
optional gate failure is recorded in the ticket's `warnings`. Killing and
restarting the loop replays an interrupted active ticket from a clean worktree
and reuses any already-open PR.

Click a dashboard card to inspect its full spec, acceptance criteria, prompt,
live log, protected tests, changed files, verification output, links, and status
history.

See `WORKSHOP_OUTLINE.md` for the colleague-facing teaching structure and
`FACILITATOR.md` for the live-demo sequence and recovery notes.
