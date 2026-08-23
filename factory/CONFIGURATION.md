# Configure the factory for your project

The workshop uses Claude as its live worked example, but the factory is not
tied to one coding agent, model, or execution environment. Use a built-in
adapter, combine different adapters by role, or register a noninteractive
command that invokes your own agent.

Configuration has four layers:

| File | Commit it? | Use it for |
| --- | --- | --- |
| `factory.charter.toml` | Yes, in the target repository | Human-owned consequence tier, merge authority, gate level, budgets, review capacity, stop conditions, and path policy. Agents may read it but never modify it. |
| `factory.project.toml` | Yes, in the target repository | Source and test roots, tools, reviewed setup commands, verification gates, protected paths, default branch, and optional reset adapter. |
| `factory/factory.toml` | Yes, with the factory | Agent commands, role defaults, retries, and timeouts. |
| `.factory/local.toml` | No | Each attendee's GitHub repository URL, Factory Profile, selected Agent Adapters, GitHub Project number, QA-review choice, and parallelism. |

Command-line options select adapters and operational settings for one command;
they cannot override an approved Factory Charter. A ticket body can
also select a registered implementation adapter with `agent: adapter-name`.

## Configuration precedence

Use this order whenever two inputs appear to conflict:

1. **Factory Charter** — human-owned authority, risk, budgets, required
   approvals, path policy, stop conditions, and merge authority. Nothing below
   may weaken it.
2. **Project Contract** — repository mechanics: roots, tools, setup, test
   placement, gates, default branch, and reset behavior. It may add stricter
   repository constraints but cannot relax the Charter.
3. **Factory Profile** — the executable planning and delivery topology. Its
   merge authority and controls must match the approved Charter; a mismatch
   fails before planning or execution.
4. **Agent Role contract** — the responsibility and exclusions of one role.
   A role can narrow its work but cannot acquire authority from the profile or
   Charter.
5. **Versioned factory policy** — general engineering, workflow, and repository
   rules applied inside those higher-level boundaries.

The approved Ticket then bounds the requested change, and the Agent Adapter is
only the replaceable executable that fulfils a role. A CLI flag can choose an
adapter or profile, but it cannot waive a gate, protected path, human decision,
or merge boundary.

## Connect the Live repository

Use any GitHub repository that you own or can write to. It can be the workshop
checkout or a separate existing project. Paste the full URL; the factory verifies access, saves the
target locally, and adds or updates `origin`. All Live issues, branches, Project
items, and pull requests then use that repository explicitly instead of the
GitHub CLI's current default.

```sh
./factory/factory configure \
  --github-repository https://github.com/YOUR-NAME/YOUR-REPOSITORY \
  --preset claude-workshop
```

Create a repository from the workshop template for the guided TableStory
exercise. For your own project, initialize its Project Contract as described
below. An empty new repository also works after it has an initial commit. Run
`./factory/factory doctor --full` before planning; it verifies that the saved
target, `origin`, and local default branch agree.

## Describe an existing repository

The factory accepts any PRD in Live mode. Repository mechanics do not come from
the PRD; they come from one small, reviewable Project Contract. From the factory
checkout, point the commands at the target Git checkout:

```sh
./factory/factory init --repo /path/to/your-project
```

The detector recognizes common Python, Node.js, Go, and Rust layouts and always
provides an integrity gate for an unknown stack. Review the generated
`/path/to/your-project/factory.project.toml` before running anything. In
particular, verify the source roots, test roots, ticket-numbered QA filename
patterns, required tools, setup commands, gates, and default branch.
Initialization also creates a conservative `factory.charter.toml` draft and
adds `.factory/` to `.gitignore` so local configuration, prompts, logs, and
runtime evidence do not become repository changes.

Review the Charter separately, then bind approval to its exact policy hash:

```sh
./factory/factory approve-charter --repo /path/to/your-project --yes
```

Any policy edit invalidates that approval. Planning and execution fail closed
until a person approves the new exact hash.

```toml
schema_version = 1

[project]
name = "example-service"
default_branch = "main"
source_roots = ["src"]
protected_paths = [".github/workflows"]

[environment]
required_tools = ["git", "python3"]
setup = ["{python} -m pip install -r requirements.txt"]
ports = [8000]

[qa]
test_roots = ["tests"]
test_file_patterns = ["test_ticket_{ticket}*.py"]

[[gate]]
name = "tests"
cmd = "{python} -m pytest -q"
required = true
```

Setup commands are never run by `init`. Read the file, then opt in explicitly:

```sh
git -C /path/to/your-project add factory.project.toml factory.charter.toml .gitignore
git -C /path/to/your-project commit -m "chore: configure software factory"
./factory/factory prepare --repo /path/to/your-project
./factory/factory control-center --repo /path/to/your-project
```

If setup intentionally updates a lockfile, review and commit that change before
full preflight. Live runs require a clean default-branch checkout synchronized
with GitHub.

The Control Center shows the same detected or committed contract on Connect.
If the repository changes shape, edit the committed contract and run planning
again. A planning run records its contract hash and refuses publication after
the contract becomes stale.

Rehearsal mode is intentionally narrower. Its deterministic agents implement
only the bundled Pocket Cinema scenarios, so use Live mode for an arbitrary PRD.

## Choose built-in adapters

Save the standard Claude workshop setup:

```sh
./factory/factory configure --preset claude-workshop
```

Or use Codex for planning, supervision, QA, implementation, and code review:

```sh
./factory/factory configure --preset codex-workshop
```

Both presets select the Standard Factory Profile, require human review of
Acceptance Tests, and run one ticket at a time. Standard also uses the Code
Review Agent and Supervisor recommendation loop described below. Compare executable role sets or
change profile explicitly:

```sh
./factory/factory profiles
./factory/factory configure --profile standard
```

You can also assign different built-in adapters to each role:

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

Only the planning role is limited to Claude or Codex. Those integrations
provide the structured JSON output required by the four planning schemas.
The supervisor, implementation, independent QA, and code-review roles can use any adapter registered in
`factory/factory.toml`.

`factory/roles.json` defines each Agent Role's ownership, exclusions,
verification responsibility, and Handoff Receipt. `factory/policy.json`
defines versioned repository rules. An Agent Adapter fills a role; changing its
CLI or model does not change the role contract.

Standard and Assured profiles use an Agent Supervisor before each ready-ticket
wave. Lean deliberately omits it. The supervisor reads recent worker Handoff
Receipts, proposes a bounded dispatch or block decision, and supplies a concise
instruction to each selected Ticket. It cannot edit code, change Ticket scope
or dependencies, override gates, approve code, or mutate lifecycle state. After
an independent Code Review Agent approves an exact revision, it may separately
recommend `MERGE` or `BLOCK`. For Standard and Assured, `MERGE` is only a
recommendation: the run stops at the human exact-revision merge gate. The
orchestrator validates and records the recommendation without executing it.

The supervisor prompt requires exactly one JSON object:

```json
{
  "schema_version": 1,
  "summary": "Dispatch the independent UI slice while the data slice waits.",
  "dispatch": [{"ticket": 4, "instruction": "Preserve the approved navigation contract."}],
  "block": []
}
```

The adapter must not wrap this object in Markdown. A nonzero exit, malformed
response, unavailable Ticket, conflicting command, excess parallelism, or
decision that silently dispatches nothing fails the checkpoint with ready work
preserved. Inspect `.factory/supervisor/state.json`, the referenced prompt and
log, or the Control Center's **Supervisor** screen.

Standard and Assured profiles also run a separate Code Review Agent after all
required verification gates pass and the candidate PR is open. It reviews the
exact base-to-head candidate diff without modifying the worktree. Its JSON
decision is schema-validated and may contain blocking, warning, or note comments
only for changed paths. `REQUEST_CHANGES` returns every comment to implementation
through the existing retry loop on the same branch and PR. The gates and reviewer
then run again. `APPROVE` is valid only when no comments remain.

In Live mode, the factory submits that decision as a GitHub PR review. GitHub
does not allow an account to approve its own PR, which is common when one workshop
login creates both the PR and the review. In that case the factory posts a clearly
labelled Factory comment instead. That comment preserves the audit evidence but
does not satisfy a branch-protection approval rule. Use a separate reviewer
identity when the repository requires a formal GitHub approval.

To use that second identity, provide its token only in the process environment:

```sh
# First inject FACTORY_REVIEW_GH_TOKEN with your local secret manager.
./factory/factory doctor --full
./factory/factory run
```

The token must belong to an account that can review the repository and differs
from the account reported by your normal `gh auth status`. Do not save it in
`factory.toml`, `.factory/local.toml`, shell history, or workshop artifacts.

After approval, the Supervisor returns a separate revision-bound command:

```json
{
  "schema_version": 1,
  "summary": "Approval and required gates match this candidate.",
  "action": "MERGE",
  "ticket": 4,
  "pull_request": "https://github.com/example/repository/pull/12",
  "candidate_head": "0123456789abcdef"
}
```

The Supervisor does not call GitHub. The orchestrator validates the approval,
published review, gates, PR URL, and exact candidate head, then presents the
human merge action. `./factory/factory merge ISSUE --yes` rechecks that exact
head and records the person's decision. A stale head, malformed recommendation,
or branch-protection failure blocks the Ticket. Lean keeps direct human diff
review and does not run the Code Review Agent.

`Autonomous Demo` is a workshop-only contrast. It requires an approved Charter
with `merge_authority = "supervisor"` and the transient
`--allow-autonomous-merge` flag on both planning and execution. The Control
Center shows the same warning and never saves the opt-in. Only that profile lets
the orchestrator execute a validated Supervisor merge recommendation.

## Register your own agent

Add a lowercase adapter name and command template to the committed `[agents]`
table. For example:

```toml
[agents]
my-agent = './tools/run-my-agent.sh {prompt}'

[supervisor]
agent = "my-agent"

[review]
agent = "my-agent"
```

The adapter command runs with the ticket worktree as its current directory.
It must:

- run without an interactive prompt;
- read the generated assignment from the supplied prompt file;
- edit only the current worktree;
- write useful progress and errors to standard output; and
- return a nonzero exit status when it cannot complete the assignment.

A wrapper script is usually the clearest place to select a model, container,
remote runner, permission mode, or provider-specific flags. Keep credentials in
the agent's normal credential store or environment; don't commit them to TOML.

Command templates can use these placeholders:

| Placeholder | Value |
| --- | --- |
| `{prompt}` | Absolute path to the generated implementation or QA prompt. |
| `{ticket}` | GitHub issue number. |
| `{worktree}` | Absolute path to the isolated ticket worktree. |
| `{repo}` | Absolute path to the main checkout. |
| `{python}` | Python interpreter used by the factory. |
| `{codex}` | Current authenticated Codex executable, for the built-in Codex adapter. |
| `{scenario}` | Selected deterministic rehearsal scenario. |
| `{attempt}` | Current bounded implementation attempt. |
| `{factory_dir}` | Absolute path to the factory's bundled adapter scripts. |

The factory shell-quotes placeholder values before inserting them. If the
agent requires stronger isolation than a Git worktree, make the adapter invoke
your container or remote execution wrapper and map the worktree into that
environment.

Assured cleanup, architecture-conformance, hardening, and final-verifier
assignments end with a structured output contract. The Agent Adapter must
preserve one final line from the model: `FACTORY_ROLE_VERDICT: PASS` or
`FACTORY_ROLE_VERDICT: BLOCK: <reason>`. Missing or blocking verdicts stop the
transition; a failed final verification is routed through hardening and the
required gates before the verifier runs again.

After registering the adapter, save it as the attendee default:

```sh
./factory/factory configure \
  --planning-agent claude \
  --supervisor-agent my-agent \
  --agent my-agent \
  --qa-agent my-agent \
  --review-qa-tests \
  --max-parallel 1
```

The planning experts will write `agent: my-agent` into the generated vertical
slices. The scheduler validates that name against `[agents]` before dispatch.
You can use separate wrappers for supervision, QA, implementation, and code review when you want different
models, instructions, or execution permissions.

## Configure runtime policy

Edit `factory/factory.toml` to tune orchestration and adapter defaults. Keep
repository-specific paths and commands in `factory.project.toml`.

```toml
[factory]
max_retries = 2
poll_interval = 20
agent_timeout = 900 # deterministic Rehearsal Run only
gate_timeout = 300

[qa]
agent = "my-agent"
max_retries = 1
require_human_approval = true
```

`agent_timeout` prevents a broken deterministic rehearsal adapter from hanging
the exercise. Live Claude, Codex, Cursor, and custom adapters have no
presentation timeout; their process remains observable until it exits or the
operator intervenes. Gate timeouts still apply in both modes.

Set test roots and filename patterns in the Project Contract to the directories
where QA may add ticket-numbered acceptance tests. Add gates there in the order
they should run. A required gate blocks the ticket after retries; an optional
gate records a warning. Commands run from the ticket worktree, so use
repository-relative paths.

This workshop uses Git worktrees for change isolation, not security isolation.
Production execution also needs untrusted-code sandboxing, credential
isolation, spend and concurrency limits, audit retention, idempotent recovery,
branch protection, supply-chain controls, observability, and organization
policy enforcement.

If you already have a GitHub Project, save its number locally:

```sh
./factory/factory configure --project-number PROJECT_NUMBER
```

Otherwise, create a Project when you approve the PRD-derived plan. The factory
will remember its number automatically:

```sh
./factory/factory approve PLAN_ID --new-project-title "My workshop"
```

## Verify the configuration

Run preflight before dispatching tickets:

```sh
./factory/factory doctor         # Rehearsal Run
./factory/factory doctor --full  # Live Run
./factory/factory run --dry-run
```

`doctor` checks the local repository and workshop prerequisites without calling
an agent CLI. Use `doctor --full` for a Live Run: it verifies built-in CLI
authentication, checks custom adapter registration, and runs the configured
verification gates. Run a custom wrapper once yourself to confirm its provider
authentication and noninteractive behavior. The dry run reads the GitHub
Project and prints dependency waves without creating worktrees or running
agents.
