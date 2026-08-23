# Software (re)-Factory

Release: `workshop-v1.1.0`

Software (re)-Factory is a legible control layer for running several coding
agents against a dependency-mapped backlog. GitHub Issues are tickets, Projects
v2 is the audited board, Git worktrees isolate changes, and ordered gates decide
whether a ticket is retried, reviewed, or blocked. Two deterministic scenarios
make the factory visible: the main five-ticket exercise rebrands Pocket Cinema
as the TableStory recipe app, while an eight-ticket TV exercise demonstrates a
deliberately blocked requirement.

Those deterministic scenarios are a workshop pack, not a product constraint.
A Live Run accepts any PRD and any Git repository through a committed Project
Contract.

## One-minute rehearsal quickstart

A Rehearsal Run needs Python 3.11+, Git, Node 20+, and no credentials or agent tokens.

```sh
./setup_demo.sh --scenario recipe-rebrand
./factory/factory control-center
```

Open <http://127.0.0.1:5050>. The Control Center guides the complete workflow,
shows the exact CLI command behind every action, and streams its output. Choose
**Rehearsal** to use deterministic agents without credentials or GitHub writes.

The equivalent CLI-only smoke run is:

```sh
./factory/factory run --mock --scenario recipe-rebrand --once
./factory/factory status
```

For versioned installation, drift-safe updates, and migration behavior, see
[COMPATIBILITY.md](COMPATIBILITY.md). An update is preview-only until
`factory/update_workshop.sh --apply` is supplied, and local drift fails closed.

The Rehearsal Run exercises the
same independent-QA commit and protected-test policy as a Live Run without using
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

## Use any repository and PRD

Keep this factory checkout as the control plane. In the Control Center, select
**Live** and paste any accessible GitHub repository URL. The factory clones or
reuses it under the ignored `.factory/repositories/` workspace and operates on
that checkout without changing the factory repository's `origin`. The target
does not need to contain Pocket Cinema or the factory source.

To use an existing local checkout instead:

```sh
./factory/factory init --repo /path/to/your-project
# Review factory.project.toml and factory.charter.toml.
./factory/factory approve-charter --repo /path/to/your-project
./factory/factory publish-setup --repo /path/to/your-project
./factory/factory prepare --repo /path/to/your-project
./factory/factory control-center --repo /path/to/your-project
```

On Connect, select **Live**, paste that project's GitHub URL, choose the role
adapters, save, and run full preflight. In PRD, paste or write the actual
product requirement. The four planning experts use the PRD for scope and the
Project Contract plus repository inventory for technical context. The approved
Vertical Slices become GitHub Issues and Project items; no scenario seed is
involved.

`factory init` detects common repository conventions and writes a Project
Contract plus a conservative Factory Charter draft. Review and approve the
exact Charter hash before publishing setup. `publish-setup` commits and pushes
only `.gitignore`, `factory.project.toml`, and `factory.charter.toml`, and refuses
unrelated changes. Review the Project Contract before `factory prepare`: that explicit command
runs only the setup commands recorded in the contract. The same contract
defines source and test roots, ticket-numbered QA filenames, tools, ports,
ordered gates, protected paths, default branch, and an optional
repository-specific reset adapter. Planning records its hash and must be
repeated if the contract changes. Review and commit any setup-generated lockfile
change before Live preflight; the default-branch checkout must be clean.

Arbitrary PRDs require Live agents. Rehearsal remains deterministic by design
and therefore supports only its bundled Pocket Cinema scenarios.

## Architecture tour

Start with `ARCHITECTURE.md`, which maps the runtime into a short reading path.
The orchestration flow is intentionally direct:

1. Load issues and parse `Depends-on: #…` plus `agent: …` from each body.
2. Move dependency-complete, `agent-ready` tickets to Ready.
3. In Standard and Assured profiles, give ready Tickets and recent worker
   Handoff Receipts to the Agent Supervisor. The orchestrator validates its
   dispatch, defer, or block decision and remains the lifecycle authority.
4. Create `../<repository>-wt-<issue>` on `factory/<issue>-<slug>` and ask the independent
   QA agent to add ticket-numbered acceptance tests only.
5. Commit and protect the Acceptance Tests; optionally pause for explicit human approval.
6. Run the implementation agent with the supervisor's Ticket instruction. The factory rejects any implementation that
   modifies or deletes a protected test.
7. Execute configured gates in order; feed the last 3,000 failure characters
   back to the agent for up to two retries.
8. On green gates, push or update the PR and give its exact candidate revision
   to the read-only Code Review Agent. Review comments return to the same
   implementation agent and consume the bounded retry budget; gates and review rerun.
9. After an `APPROVE` decision with no comments, the Supervisor may recommend
   a revision-bound `MERGE`. The orchestrator rechecks the live PR head. Lean,
   Standard, and Assured then stop for the human exact-revision merge action;
   only an explicitly opted-in Autonomous Demo executes the recommendation.
10. Reconcile the merge, unlock dependants, and mirror each transition and
    artifact path to `.factory/state.json` for the Control Center.

The Control Center teaches four macro phases—**Plan, Build, Verify, Review**—before
showing detailed ticket states. Every orchestrated role writes a Handoff Receipt
with input and output revisions, its claim, verification, unresolved risks,
artifacts, and policy hashes. Worker roles communicate results to the Agent
Supervisor through those receipts; the Supervisor screen shows its validated
commands and decision history.

## Choose a Factory Profile

Profiles are executable role topologies, not presentation labels:

```sh
./factory/factory profiles
./factory/factory configure --profile standard
```

- **Lean** runs Product Review and Vertical Slices, then implementation,
  verification, and human review.
- **Standard** runs all four planning roles, supervised dispatch, independent
  QA, protected Acceptance Tests, implementation, verification, independent
  code review, review-comment rework, a Supervisor recommendation, and a human
  exact-revision merge.
- **Assured** adds cleanup, architecture conformance, hardening, and a read-only
  final verifier before independent code review and the same human merge gate.
- **Autonomous Demo** keeps the end-to-end automated merge demonstration. It is
  workshop-only and requires a fresh, visible opt-in for every run. A Charter
  `requires_human_approval` path still requires a human merge.

Agent Role contracts are versioned in `roles.json`; ownership, exclusions,
verification responsibility, and receipt requirements remain stable when an
Agent Adapter changes. Project policy is versioned in `policy.json`, and its
section hashes are recorded in plans and receipts.

The ticket backend is isolated in `github_backend.py`; adapter commands and gates
are all in `factory.toml`. You can keep the workflow and swap the CLI, model
wrapper, execution environment, test suite, or lint policy. See
`CONFIGURATION.md` for the complete project configuration contract.

## Preflight every live session

Choose the workshop agents once. The ignored `.factory/local.toml` file stores
attendee-specific defaults; repository policy remains in `factory.toml`. Claude
is the worked example, not a factory requirement.

```sh
curl -fsSL https://claude.ai/install.sh | bash  # omit when already installed
claude auth login
./factory/factory configure --preset claude-workshop
./factory/factory doctor --full
```

For a Live Run, connect the attendee's repository explicitly. This removes any
dependency on the current `gh` default repository:

```sh
./factory/factory configure \
  --github-repository https://github.com/YOUR-NAME/YOUR-REPOSITORY \
  --preset claude-workshop
./factory/factory doctor --full
```

The preset selects Claude for planning, supervision, independent QA,
implementation, and code review,
requires human QA-test approval, selects the Standard profile, and limits
execution to one ticket at a time for a legible workshop trace.
Use `codex-workshop` to make the same choices with Codex. Explicit command-line
flags still override saved defaults for one invocation. You can also combine
built-in adapters or register your own supervision, implementation, QA, and code-review command:

```sh
./factory/factory configure \
  --planning-agent claude \
  --supervisor-agent claude \
  --agent cursor \
  --qa-agent codex \
  --review-agent claude \
  --review-qa-tests \
  --max-parallel 1
```

Planning currently uses Claude or Codex because those integrations enforce the
four structured planning schemas. Supervision, implementation, QA, and code review can use any lowercase
adapter registered in `factory.toml`. Follow `CONFIGURATION.md` to connect a
different CLI, model wrapper, container, or remote runner.

If the GitHub Project already exists, save its number at the same time:

```sh
./factory/factory configure \
  --preset claude-workshop \
  --project-number "$PROJECT_NUMBER"
```

It checks repository safety and synchronization, GitHub authentication and
Projects scope, Python/Node and the virtual environment, agent CLIs, ports,
baseline data, configuration, and optionally the complete test suite.
For Standard and Assured runs it also reports whether
`FACTORY_REVIEW_GH_TOKEN` provides a distinct GitHub reviewer identity. Without
one, the validated review is posted as a labelled Factory comment instead of a
formal self-approval.

## Start from an attendee PRD

Copy `factory/PRD_TEMPLATE.md`, fill it in, then start the four-expert alignment
pipeline. Each expert is a fresh, read-only invocation of the planning CLI
selected by the workshop preset. Each stage has a distinct role, prompt, strict
JSON schema, Markdown review artifact, prompt, and log.

```sh
cp factory/PRD_TEMPLATE.md workshop-prd.md
# Edit workshop-prd.md
./factory/factory plan workshop-prd.md
```

The first command runs only **Product Review**. Inspect the product behavior,
users, journeys, scope, evidence, assumptions, mockup needs, and blocking
questions. Nothing technical runs until a human approves this contract:

```sh
./factory/factory review product PLAN_ID
./factory/factory revise PLAN_ID product \
  --feedback "Describe the objective evidence this requirement must produce"
./factory/factory review product PLAN_ID
./factory/factory approve-product PLAN_ID
```

Approval launches nothing. Continue explicitly to run **System Architecture**,
**Program Design**, and **Vertical Slices**, in that order:

```sh
./factory/factory continue-plan PLAN_ID
./factory/factory review alignment PLAN_ID
```

If the approved Charter also names `system_architecture` or `program_design` in
`policy.planning_approvals`, `continue-plan` pauses after that expert. Use the
Control Center approval, or review and approve the exact artifact from the CLI:

```sh
./factory/factory review architecture PLAN_ID
./factory/factory approve-stage architecture PLAN_ID
./factory/factory continue-plan PLAN_ID
```

Vertical Slice file ownership strengthens these gates automatically when it
intersects a Charter load-bearing path.

The run lives at `.factory/plans/PLAN_ID/` and contains:

- `source-prd.md` and a hash-tracked `manifest.json`.
- `01-product-review.{json,md}`.
- `02-system-architecture.{json,md}`.
- `03-program-design.{json,md}`.
- `04-vertical-slices.{json,md}`.
- `traceability.json` and `alignment-review.md`.

The generated traceability matrix connects each product requirement to
architecture contracts, program elements, vertical slices, and QA evidence.
Validation rejects unresolved questions, orphan requirements or program
elements, dependency cycles, missing evidence, and overlapping file ownership
between parallel tickets. Editing an approved upstream artifact invalidates its
approval and every downstream artifact; the factory never silently reuses stale
planning output.

Use `factory revise` rather than editing a generated artifact. It records human
feedback and revision history, reruns only the selected expert, clears affected
approvals, and marks downstream stages stale. The accepted stage names are
`product`, `architecture`, `program`, and `slices`. In the Control Center, a
blocked expert displays one answer field per question; submitting every decision
revises that artifact and resumes downstream planning without a JSON edit or CLI
command. If an expert instead fails deterministic validation, the rejected JSON
and validator message are preserved. Enter a specific repair instruction in the
failed expert card and select **Apply correction and continue**. The factory
uses the rejected JSON as the revision source, records the instruction, reuses
valid upstream work, and resumes only after the replacement validates.

After the alignment review, approve and publish the final slices:

```sh
./factory/factory approve PLAN_ID
```

The human types `APPROVE ALIGNMENT`; only then does the factory create or update
GitHub Issues, translate dependencies into issue numbers, add them to Projects,
and set dependency-free tickets Ready. Publication remains idempotent.

For a credential-free Rehearsal Run, record the same alignment approval and
materialize local tickets directly from the reviewed Vertical Slices:

```sh
./factory/factory approve-rehearsal PLAN_ID
./factory/factory run --mock --scenario recipe-rebrand --dry-run
```

Type `APPROVE ALIGNMENT`. This path writes only local rehearsal state and does
not contact GitHub.

The deterministic scenario supplies execution actions, but ticket titles,
specifications, criteria, dependencies, and plan provenance come from the PRD.

For a clean workshop board, create one during approval:

```sh
./factory/factory approve PLAN_ID --new-project-title "TableStory Workshop"
```

The approval command stores the selected Project number in `.factory/local.toml`.
Inspect the GitHub board, then deliberately start implementation:

```sh
./factory/factory run
```

## Independent QA acceptance-test phase

Real factory runs use a dedicated QA agent before the implementation agent for
every ticket. The committed repository default is Codex; an attendee preset
overrides it locally. The QA adapter can be different from the implementation
adapter, including a project-specific adapter registered in `factory.toml`:

```toml
[qa]
agent = "codex"
max_retries = 1
require_human_approval = false
```

Test placement stays in `factory.project.toml`:

```toml
[qa]
test_roots = ["tests"]
test_file_patterns = ["test_ticket_{ticket}*.py"]
```

You can select a different QA CLI for one run. To omit independent QA, select
the Lean profile; Standard and Assured reject `--no-qa`:

```sh
./factory/factory run --agent codex --qa-agent claude --max-parallel 4
./factory/factory run --profile lean --agent codex --max-parallel 1
./factory/factory run --agent codex --review-qa-tests
```

For each issue, QA receives the full spec and acceptance criteria. It may only
add new files that match the Project Contract's ticket-numbered patterns inside
its configured test roots. The factory
commits those files before implementation and records their Git blob hashes.
The implementation agent sees the protected-file list in its prompt and may add
more tests, but changing, renaming, or deleting an Acceptance Test fails verification and
is fed back into the normal retry loop.

With `--review-qa-tests`, a ticket pauses in **QA Review**. Inspect its test diff
from the Control Center or terminal, then continue it explicitly:

```sh
./factory/factory approve-tests ISSUE
```

QA prompts and logs are separate from implementation artifacts:

```text
.factory/prompts/ISSUE-qa-attemptN.md
.factory/logs/ISSUE-qa-attemptN.log
```

The Rehearsal Run uses `mock_qa_agent.py`, so QA commits and protected-test checks
remain credential-free and deterministic. Passing `--qa-agent` explicitly with
`--mock` opts into a real QA CLI instead.

## Disposable attendee checkout

Avoid resetting an attendee's working repository by creating a disposable clone:

```sh
./factory/new_workshop.sh ../software-refactory-attendee live
```

The command refuses an existing destination and clones `origin`. Use `live` for
a synchronized Live Run checkout, or `tv`/`recipe-rebrand` to prepare a local
Rehearsal Run from the tagged baseline.

## Instructor-led Live Run

Create and clone a private repository from the public workshop template (choose
your own repository name):

```sh
gh repo create software-refactory-workshop \
  --private \
  --template giolaq/software-refactory-workshop \
  --clone
cd software-refactory-workshop
```

Authenticate the GitHub CLI with Projects permission, configure the selected
agents, and start with a PRD. This example uses Claude; select a built-in or
custom setup from `CONFIGURATION.md` if your team uses another CLI or model:

```sh
gh auth login
gh auth refresh -s project
./factory/factory configure \
  --github-repository "$(gh repo view --json url --jq .url)" \
  --preset claude-workshop
./factory/factory plan recipe-app-prd.md
```

Follow the two human planning gates described above. `factory approve` converts
the approved Vertical Slices artifact into GitHub Issues and adds them to the
selected Project. The tickets therefore come from the PRD; they are not a
separate prepared backlog.

Use deterministic tickets only when model access, latency, or workshop timing
prevents the planning exercise from completing:

```sh
./factory/factory seed recipe-rebrand
```

The seed command explicitly reports that it bypasses PRD planning and both human
alignment gates. It is a recovery fixture, not the normal product workflow. An
advanced operator can still target another repository explicitly:

```sh
./factory/factory seed recipe-rebrand --github-repo OWNER/REPOSITORY
```

The first run creates or reuses a **Software (re)-Factory** Projects v2 project,
normalizes its Status options, adds the issues, mirrors state labels, and opens
PRs after required gates pass. Configure `--project-number N` once to use an
existing project; approval also remembers a newly created Project automatically.
Use `--once` for one scheduler sweep; without it, the factory polls for QA
approvals and newly merged PRs every 20 seconds.

Run a no-write dependency preview before dispatch:

```sh
./factory/factory run --dry-run
```

When a ticket is Blocked, edit its issue spec or acceptance criteria and then:

```sh
./factory/factory retry 8
```

Per-ticket `agent: adapter-name` overrides the default when that lowercase name
is registered under `[agents]` in `factory.toml`. Before a live session,
smoke-test each installed CLI or wrapper because provider flags can change;
update only its adapter template when needed.

Claude planning uses Claude Code structured output with the stage JSON schema.
It runs in plan mode with read-only repository tools. Authenticate it with:

```sh
claude auth login
claude auth status --text
```

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

After the seven successful Rehearsal Run merges, open <http://localhost:5000/?mode=tv>.
Use arrow keys and Enter on the home rails, then Escape or Backspace in film
details. The data and gradient poster artwork are bundled and fictional, so the
demo works offline.

## Export review evidence

Generate the 16-section Factory Canvas, complete it, and ask a peer to review
it before export:

```sh
./factory/factory canvas --output factory-canvas.md
./factory/factory evidence PLAN_ID --canvas factory-canvas.md
```

The packet includes reviewed planning, approvals, traceability, selected ticket
and pull-request links, protected-test metadata, gate results, Handoff Receipts,
the Canvas, missing-evidence warnings, and a hash manifest. Raw prompts, raw
logs, command output, environment values, tokens, and credentials are excluded.

Before a public/template release, freeze a clean tree and run:

```sh
./factory/factory --version
.factory/venv/bin/python -m unittest discover -s factory/tests
npm --prefix workshop-guide test
npm --prefix workshop-guide run lint
./factory/factory release-check
./factory/factory release-check --rehearsal
```

The local audit checks release identity, tracked generated state, possible
credentials, obsolete participant-facing language, and a clean worktree. The
`--rehearsal` check clones committed HEAD and executes the complete Standard
planning, approval, execution-role, and retry path. Maintainers can additionally
validate GitHub Issue, Project, PR, merge, and dashboard synchronization from a
disposable repository. This opt-in check runs Claude planning and delivery with
a deterministic review adapter, creates a fresh Project, approves independent
Acceptance Tests, returns one review comment to the same implementation branch,
merges the repaired Ticket, and verifies its Evidence Packet links:

```sh
./factory/factory release-check --live-smoke \
  --confirm-disposable-repo
```

## Operator reference

```text
factory configure [--preset claude-workshop|codex-workshop]
                  [--profile lean|standard|assured|autonomous-demo]
                  [--agent NAME] [--qa-agent NAME]
                  [--planning-agent claude|codex]
                  [--review-qa-tests|--no-review-qa-tests]
                  [--max-parallel N] [--project-number N]
factory control-center [--port N] [--no-open]
factory init [--repo PATH] [--name NAME] [--force]
factory prepare [--repo PATH] [--yes]
factory seed [recipe-rebrand|tv] [--github-repo OWNER/REPOSITORY] [--agent NAME]
factory run [--repo PATH] [--profile lean|standard|assured|autonomous-demo]
            [--agent NAME] [--qa-agent NAME] [--supervisor-agent NAME]
            [--review-agent NAME] [--allow-autonomous-merge]
            [--review-qa-tests|--no-review-qa-tests] [--scenario tv|recipe-rebrand]
            [--max-parallel N]
            [--project-number N] [--once] [--dry-run] [--mock]
factory plan PRD.md [--output RUN_DIRECTORY] [--default-agent NAME]
                    [--profile lean|standard|assured|autonomous-demo]
                    [--planning-agent claude|codex]
                    [--min-tickets N] [--max-tickets N] [--mock]
factory review product|architecture|program|alignment PLAN_ID
factory approve-product PLAN_ID [--yes]
factory approve-stage architecture|program PLAN_ID [--yes]
factory continue-plan PLAN_ID [--mock]
factory revise PLAN_ID product|architecture|program|slices
               (--feedback TEXT|--feedback-file PATH) [--mock]
factory approve PLAN_ID [--project-number N] [--new-project-title TITLE] [--yes]
factory approve-rehearsal PLAN_ID [--scenario recipe-rebrand|tv] [--yes]
factory approve-tests ISSUE [--yes]
factory status [--repo PATH]
factory retry ISSUE [--repo PATH] [--project-number N] [--mock]
factory reset [--repo PATH] [--start-over] [--local-state-only]
factory profiles [--json]
factory canvas [--output PATH] [--force]
factory evidence PLAN_ID --canvas PATH [--ticket ISSUE] [--output DIRECTORY]
factory release-check [--repo PATH] [--rehearsal]
                      [--live-smoke --confirm-disposable-repo]
factory doctor [--repo PATH] [--full] [--agent NAME] [--qa-agent NAME]
               [--planning-agent claude|codex]
```

Runtime artifacts are under `.factory/`: `planning-state.json`, planning runs,
`state.json`, QA, implementation, and code-review prompts, structured review
artifacts, and one log per phase attempt.
Required gate failure blocks progress;
optional gate failure is recorded in the ticket's `warnings`. Killing and
restarting the loop replays an interrupted active ticket from a clean worktree
and reuses any already-open PR.

The Control Center shows the four planning contracts, human gates, ticket board,
live operations, and evidence. See `CONTROL_CENTER.md` for its workflow and
local security boundary. The original static dashboard remains a read-only
compatibility view.

See `WORKSHOP_OUTLINE.md` for the colleague-facing teaching structure and
`FACILITATOR.md` for the live-demo sequence and recovery notes. See
`CONFIGURATION.md` before adapting the workshop to another repository or agent.
