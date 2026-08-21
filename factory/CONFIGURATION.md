# Configure the factory for your project

The workshop uses Claude as its live worked example, but the factory is not
tied to one coding agent, model, or execution environment. Use a built-in
adapter, combine different adapters by role, or register a noninteractive
command that invokes your own agent.

Configuration has two layers:

| File | Commit it? | Use it for |
| --- | --- | --- |
| `factory/factory.toml` | Yes | Agent commands, QA policy, retries, timeouts, test roots, and verification gates shared by the project. |
| `.factory/local.toml` | No | Each attendee's Factory Profile, selected Agent Adapters, GitHub Project number, QA-review choice, and parallelism. |

Command-line options override both layers for one command. A ticket body can
also select a registered implementation adapter with `agent: adapter-name`.

## Choose built-in adapters

Save the standard Claude workshop setup:

```sh
./factory/factory configure --preset claude-workshop
```

Or use Codex for planning, QA, and implementation:

```sh
./factory/factory configure --preset codex-workshop
```

Both presets select the Standard Factory Profile, require human review of
Acceptance Tests, and run one ticket at a time. Compare executable role sets or
change profile explicitly:

```sh
./factory/factory profiles
./factory/factory configure --profile standard
```

You can also assign different built-in adapters to each role:

```sh
./factory/factory configure \
  --planning-agent claude \
  --agent cursor \
  --qa-agent codex \
  --review-qa-tests \
  --max-parallel 1
```

Only the planning role is limited to Claude or Codex. Those integrations
provide the structured JSON output required by the four planning schemas.
Implementation and independent QA can use any adapter registered in
`factory/factory.toml`.

`factory/roles.json` defines each Agent Role's ownership, exclusions,
verification responsibility, and Handoff Receipt. `factory/policy.json`
defines versioned repository rules. An Agent Adapter fills a role; changing its
CLI or model does not change the role contract.

## Register your own agent

Add a lowercase adapter name and command template to the committed `[agents]`
table. For example:

```toml
[agents]
my-agent = './tools/run-my-agent.sh {prompt}'
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
  --agent my-agent \
  --qa-agent my-agent \
  --review-qa-tests \
  --max-parallel 1
```

The planning experts will write `agent: my-agent` into the generated vertical
slices. The scheduler validates that name against `[agents]` before dispatch.
You can use separate wrappers for QA and implementation when you want different
models, instructions, or execution permissions.

## Configure project policy

Edit `factory/factory.toml` to match the repository rather than copying the
demo defaults unchanged.

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
test_roots = ["tests/acceptance", "web/tests"]

[[gate]]
name = "unit-tests"
cmd = '{python} -m pytest -q'
required = true

[[gate]]
name = "lint"
cmd = 'npm run lint'
required = true
```

`agent_timeout` prevents a broken deterministic rehearsal adapter from hanging
the exercise. Live Claude, Codex, Cursor, and custom adapters have no
presentation timeout; their process remains observable until it exits or the
operator intervenes. Gate timeouts still apply in both modes.

Set `test_roots` to directories where QA may add ticket-numbered acceptance
tests. Add gates in the order they should run. A required gate blocks the
ticket after retries; an optional gate records a warning. Commands run from the
ticket worktree, so use repository-relative paths.

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
