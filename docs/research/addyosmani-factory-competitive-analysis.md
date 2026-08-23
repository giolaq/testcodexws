# Competitive analysis: Addy Osmani's Factory and Software (re)-Factory

**Research date:** 2026-08-23
**Competitor snapshot:** [`addyosmani/factory` commit `8af1165`](https://github.com/addyosmani/factory/commit/8af116567166a0a16588b7ab1b9934ece0b775bc)
**Our snapshot:** local branch `codex/agent-supervisor`, including uncommitted work as inspected on 2026-08-23

## Executive verdict

These projects share the same core idea—move human judgment to explicit boundaries and require evidence before software progresses—but optimize for different jobs.

Addy's Factory is a **small-team, repository-local operating protocol**. GitHub labels are its durable queue, stock Claude Code routines provide the clock and workers, Markdown skills define procedures, shell scripts produce deterministic verdicts, and a human merges every pull request. It deliberately has no custom orchestrator or graphical dashboard ([README, lines 1–35](https://github.com/addyosmani/factory/blob/8af116567166a0a16588b7ab1b9934ece0b775bc/README.md#L1-L35), [Architecture, lines 66–99](https://github.com/addyosmani/factory/blob/8af116567166a0a16588b7ab1b9934ece0b775bc/ARCHITECTURE.md#L66-L99)).

Software (re)-Factory is an **executable orchestration and teaching product**. It turns a PRD into four schema-validated planning artifacts, publishes dependency-mapped tickets to GitHub Projects, runs tickets concurrently in Git worktrees, coordinates them through a Supervisor, protects independently authored acceptance tests, reviews exact PR revisions, and exposes all of that in a local Control Center (`factory/ARCHITECTURE.md`, lines 8–49 and 82–125; `factory/PLANNING.md`, lines 23–51 and 119–149).

Our project is better at **PRD-to-plan traceability, multi-ticket coordination, adapter portability, visual observability, and workshop pedagogy**. Addy's is better at **operational simplicity, distributed queue durability, risk policy, review back-pressure, causal test proof, ongoing maintenance, and preserving human merge accountability**.

The best direction is not to replace our orchestrator with Addy's model. It is to import its strongest controls into our richer system: a target-specific human charter, red-before-green test proof, remote ticket claims, a hard review-capacity limit, immutable remote run summaries, an ongoing monitor loop, and a human-merge default for production-oriented profiles.

## Side-by-side scorecard

| Area | Addy's Factory | Software (re)-Factory | Advantage |
| --- | --- | --- | --- |
| Architecture | Repository files + stock routines; no service or orchestrator | Python lifecycle engine, GitHub backend, Supervisor, Control Center | Addy's for simplicity; ours for deterministic coordination |
| Intake | Ongoing issue triage and monitoring | PRD-first project planning | Addy's for maintenance; ours for coherent product change |
| Planning | Four interactive human-approved Markdown gates | Four separate expert agents, JSON schemas, stable IDs, hashes, invalidation, two human gates | Ours for rigor and automation; Addy's for human scrutiny at every design boundary |
| Queue | GitHub labels and structured issue comments are authoritative | GitHub Projects + local `.factory/state.json` | Addy's for restartability across machines; ours for richer dependency visualization |
| Concurrency | One issue per fresh run; deterministic remote branch is a compare-and-swap claim | Dependency DAG, bounded parallel workers, one Git worktree per ticket | Ours locally; Addy's across independent runners |
| Acceptance evidence | Implementer writes test first; verifier removes fix to prove the test fails | Independent QA writes new tests first; hashes prevent implementer tampering | Split: ours separates authorship, Addy's proves causality |
| Review | Fresh verifier plus optional adversarial critic; PR-level verification | Read-only Code Review Agent, comment-to-rework loop, exact-head approval, Supervisor merge | Ours for closed-loop repair; Addy's for stronger skeptical verification |
| Human gates | Product, architecture, design, slices, load-bearing/test edits, every merge | Product, final alignment, optional QA-test review; Standard/Assured can merge after agent approval | Addy's for accountability; ours for flow and demonstration |
| Observability | Terse `/factory` status backed by GitHub and immutable run files | Visual Control Center with phase, prompts, logs, diffs, tests, receipts, decisions, reset | Ours for comprehension; Addy's for durable remote history |
| Security posture | Default-deny charter, self-modification ban, existing-test rule, merge hook, branch protection | Allowlisted loopback API, path validation, protected test hashes, credential redaction, exact-head merge check | Addy's safer by default; ours has stronger artifact integrity in selected areas |
| Portability | Installs files into any repo; Claude-first automation, thin Codex adapters | Generic Project Contract; arbitrary execution adapters; Claude/Codex structured planning | Ours across agents; Addy's across clean clones and cloud sessions |
| Workshop | Separate demo/workshop; excellent conceptual advice | Dedicated website, deterministic rehearsal, screenshots, Control Center, evidence packet | Ours, but Addy's story is easier to absorb |

## Detailed findings

### 1. Architecture and workflow

Addy's design treats GitHub and the repository as the platform. Each run is intentionally short, stateless in memory, and restartable from labels, handoff comments, and committed run records. The explicit rationale is that stock routines already supply scheduling and managed execution, so a custom orchestrator adds operational surface before it adds value ([README, lines 39–59](https://github.com/addyosmani/factory/blob/8af116567166a0a16588b7ab1b9934ece0b775bc/README.md#L39-L59), [Architecture, lines 66–83](https://github.com/addyosmani/factory/blob/8af116567166a0a16588b7ab1b9934ece0b775bc/ARCHITECTURE.md#L66-L83)).

Our lifecycle engine owns far more semantics: dependency validation, readiness, worktree creation, QA, bounded retry, verification, PR review, rework, exact-revision approval, merge, default-branch synchronization, and dependent-ticket unlock (`factory/orchestrator.py`, lines 1510–1718 and 1720–1783). Its explicit separation between agent proposals and orchestrator authority is a real strength (`factory/ARCHITECTURE.md`, lines 93–110; `factory/roles.json`, lines 28–32 and 82–86).

**Where ours is better:** a multi-ticket PRD can be executed as a coordinated delivery graph, not a collection of independent issue routines. Dependencies and parallel file ownership are validated before publication (`factory/PLANNING.md`, lines 132–149), and a Supervisor can coordinate safe waves without receiving mutation authority.

**Where ours is worse:** the custom control plane is much larger and more failure-prone. The inspected core, UI, and tests exceed 12,000 lines, while the competitor repository is about 4,500 lines including all documentation and templates. Our local process and `.factory` state create recovery modes that do not exist when GitHub is the sole operational source of truth. This is the cost of capability, but it should be explicit.

### 2. Planning and human judgment

Both projects use Product, Architecture, Program Design, and Vertical Slices. Addy's version pauses for a separate human approval after every stage. Product explicitly includes a shipped announcement, HTML mockups, and non-goals; Program Design exposes the three least-confident decisions; Slices begin with a tracer bullet ([factory-spec, lines 17–82](https://github.com/addyosmani/factory/blob/8af116567166a0a16588b7ab1b9934ece0b775bc/template/.claude/skills/factory-spec/SKILL.md#L17-L82)).

Our version gives every stage to a fresh expert, requires schema-valid JSON, preserves stable requirement/contract/design IDs, records prompt and input hashes, invalidates stale downstream artifacts, validates complete traceability, and provides UI recovery for blocking questions (`factory/PLANNING.md`, lines 23–51, 75–95, and 132–149; `factory/CONTROL_CENTER.md`, lines 31–37).

**Where ours is better:** its planning artifacts are machine-checkable contracts, not only good documents. It can prove that every requirement reaches architecture, program design, a vertical slice, and QA evidence, and that ticket dependencies are acyclic and safe to parallelize.

**Where ours is worse:** only Product Review and final Alignment are mandatory human gates. Architecture and Program Design may proceed without an explicit human acceptance unless an expert blocks. For load-bearing systems, Addy's four separate approvals are the safer interpretation of “judgment relocates upstream.” Our JSON schemas also risk making the plan look precise before the underlying decisions are actually sound.

### 3. Execution isolation and concurrency

Addy's worker claims one issue by pushing a deterministic remote branch. Two runners create different claim commits, and Git's non-fast-forward rejection makes only the first owner valid ([factory-implement, lines 12–50](https://github.com/addyosmani/factory/blob/8af116567166a0a16588b7ab1b9934ece0b775bc/template/.claude/skills/factory-implement/SKILL.md#L12-L50)). When run in Claude cloud, each worker also gets a fresh VM; the project itself correctly documents that this automation is Claude-first ([README, lines 132–153](https://github.com/addyosmani/factory/blob/8af116567166a0a16588b7ab1b9934ece0b775bc/README.md#L132-L153)).

Our scheduler creates a sibling worktree per ticket, runs dependency-ready tickets in a bounded thread pool, serializes integration, detects cycles and deadlocks, and verifies merged dependencies before unlocking downstream work (`factory/orchestrator.py`, lines 102–109, 690–720, 1665–1718, and 1748–1783).

**Where ours is better:** it provides visible, deterministic local isolation and coordinated parallelism across a planned delivery graph.

**Where ours is worse:** a worktree is not a security sandbox, as our own architecture notes (`factory/ARCHITECTURE.md`, lines 113–115). More importantly, the Control Center prevents two local button operations, but the GitHub backend has no equivalent of Addy's remote compare-and-swap claim. Two independent CLI or hosted runners can observe the same Ready ticket before either updates the Project. Local orchestration is stronger; distributed ownership is weaker.

### 4. Verification and code review

Addy's strongest technical control is its negative test proof. A separate verifier reads the diff cold, reruns gates, reverses non-test changes, and requires the focused new test to fail without the implementation. It also rejects unattended changes to existing tests and rejects scope drift ([factory-verifier, lines 24–90](https://github.com/addyosmani/factory/blob/8af116567166a0a16588b7ab1b9934ece0b775bc/template/.claude/agents/factory-verifier.md#L24-L90)). Required checks fail closed as `MISCONFIGURED`, not green, and a second PR-level verifier reproduces the evidence ([README, lines 206–245](https://github.com/addyosmani/factory/blob/8af116567166a0a16588b7ab1b9934ece0b775bc/README.md#L206-L245), [factory-verify, lines 12–29](https://github.com/addyosmani/factory/blob/8af116567166a0a16588b7ab1b9934ece0b775bc/template/.claude/skills/factory-verify/SKILL.md#L12-L29)).

Our QA role is independently authored before implementation, may only add ticket-numbered files in configured test roots, and records their Git hashes. Every later phase checks those hashes, so the implementation or reviewer cannot weaken the accepted evidence (`factory/orchestrator.py`, lines 1192–1284 and 1510–1524). Required gates then run, a read-only reviewer inspects the exact candidate, `REQUEST_CHANGES` returns structured comments to implementation, and only an `APPROVE` with no comments can reach an exact-head merge decision (`factory/orchestrator.py`, lines 1599–1663; `factory/ARCHITECTURE.md`, lines 99–110).

**Where ours is better:** it separates test authorship from implementation and closes the entire review-repair-reverify loop. The approval is revision-specific, and stale heads fail closed.

**Where ours is worse:** the factory records that QA created validly placed tests, but it does not prove those tests fail on the pre-implementation behavior. A syntactically valid, irrelevant, or already-green acceptance test can be hash-protected forever. Addy's causal proof is stronger than our chain of custody. Our generic policy also protects only the QA-owned files, whereas Addy's unattended policy prohibits modifying any pre-existing test file.

### 5. Human gates and merge authority

Addy's non-negotiable rule is that no agent or routine ever merges. Humans own every merge, while GitHub branch rules are the actual enforcement boundary; hooks are only defense in depth ([Contract, lines 1–32](https://github.com/addyosmani/factory/blob/8af116567166a0a16588b7ab1b9934ece0b775bc/template/docs/factory/CONTRACT.md#L1-L32), [GitHub setup, lines 14–27](https://github.com/addyosmani/factory/blob/8af116567166a0a16588b7ab1b9934ece0b775bc/template/docs/factory/GITHUB.md#L14-L27)).

Our Lean profile retains a human merge boundary, but Standard and Assured allow the Code Review Agent to approve and the Supervisor to authorize merge. The orchestrator rechecks the PR head and calls GitHub (`factory/factory_contracts.py`, lines 13–57; `factory/orchestrator.py`, lines 1365–1437). This is sophisticated automated merge safety, but it is still automated merge. In a one-login workshop, GitHub may record the agent decision only as a comment rather than a formal approval (`factory/github_backend.py`, lines 204–235).

**Where ours is better:** it demonstrates a complete autonomous feedback and integration loop, including exact-revision safety and branch-protection failure handling.

**Where ours is worse:** it makes the accountability boundary harder to explain. “The reviewer agent approved, the Supervisor authorized, and the orchestrator merged” is technically careful but leaves no human accountable for the final change. This conflicts with the article's thesis unless the workshop explicitly presents automated merge as an optional, higher-autonomy choice rather than the production default.

### 6. Observability, durability, and maintenance

Our Control Center is a major product advantage. It guides the attendee through Connect, PRD, Planning, Tickets, Supervisor, and Evidence; shows exact CLI equivalents; streams output; surfaces blocked questions; and exposes prompts, logs, diffs, tests, gates, reviews, and receipts (`factory/CONTROL_CENTER.md`, lines 1–44 and 46–64). GitHub Projects provides a shared visual dependency/status board (`factory/github_backend.py`, lines 14–16 and 80–176).

Addy's `/factory` control room is intentionally textual and read-only, but it leads with “Needs you,” the review queue and its capacity, gate health, stale monitoring, verifier rejection rate, and review wait ([factory command, lines 6–71](https://github.com/addyosmani/factory/blob/8af116567166a0a16588b7ab1b9934ece0b775bc/template/.claude/commands/factory.md#L6-L71)). Every run writes an immutable repository record, and a weekly monitor checks CI, gate health, advisories, stale claims, review latency, comprehension drift, and charter gaps, then files issues without fixing them ([factory-monitor, lines 6–99](https://github.com/addyosmani/factory/blob/8af116567166a0a16588b7ab1b9934ece0b775bc/template/.claude/skills/factory-monitor/SKILL.md#L6-L99)).

**Where ours is better:** an attendee can understand a live multi-agent run in one screen and recover blocked planning without learning the CLI.

**Where ours is worse:** most rich evidence lives under ignored local `.factory` state. The Evidence Packet is useful and redacted, but it is an explicit export rather than a durable operational history (`factory/evidence_packet.py`, lines 121–136 and 239–288). We have no equivalent ongoing monitor or evidence-driven constraint-tuning loop. Addy's simple status survives a laptop restart because GitHub and committed run records are authoritative; ours provides more detail but has weaker cross-machine continuity.

### 7. Security and policy

Addy's charter is target-specific and default-deny: it defines consequence-based autonomy tiers, load-bearing paths, automatable and never-automate classes, definition of done, gate level, explicit stop conditions, and a review queue cap. Silence means stop. Factory policy files and existing tests are load-bearing, issue text is treated as untrusted data, and branch protection is the ultimate merge boundary ([Charter, lines 1–172](https://github.com/addyosmani/factory/blob/8af116567166a0a16588b7ab1b9934ece0b775bc/template/docs/factory/CHARTER.md#L1-L172), [factory-triage, lines 86–103](https://github.com/addyosmani/factory/blob/8af116567166a0a16588b7ab1b9934ece0b775bc/template/.claude/skills/factory-triage/SKILL.md#L86-L103)).

Our system has several strong mechanical controls: relative-path and placeholder validation in the Project Contract, configured protected paths plus an always-protected contract, an allowlisted loopback Control Center API, shell-quoted adapter placeholders, credential redaction in exported evidence, protected QA hashes, and stale-head checks (`factory/project_contract.py`, lines 42–50, 147–218, and 396–400; `factory/orchestrator.py`, lines 150–211 and 1272–1295; `factory/control_center.py`, lines 1–5 and 577–748; `factory/sensitive_data.py`, lines 8–28).

**Where ours is better:** selected invariants are enforced in executable Python rather than depending on an agent following Markdown. Structured outputs and exact hashes make evidence tampering visible.

**Where ours is worse:** `workshop-policy-v1` is global and generic, not a human-owned risk charter for each target (`factory/policy.json`, lines 1–23). Auto-detection protects only `.github/workflows` by default (`factory/project_contract.py`, lines 310–323). It does not automatically protect agent instructions, factory configuration, CI, migrations, security-sensitive areas, or all existing tests. Adapter and gate commands ultimately execute locally through a shell. The current system validates many violations after execution rather than constraining filesystem or network capability before execution.

### 8. Portability and pedagogy

Addy's installer copies a pinned policy and workflow template into any repository without overwriting existing files, after which stock Claude Code or Codex can read it in a normal clone ([README, lines 155–202](https://github.com/addyosmani/factory/blob/8af116567166a0a16588b7ab1b9934ece0b775bc/README.md#L155-L202)). Its unattended schedule remains Claude-first and it openly documents this limitation.

Our `factory init --repo PATH` detects Node, Python, Go, and Rust structure and writes a reviewed Project Contract for source roots, tools, setup, tests, gates, and reset (`factory/project_contract.py`, lines 220–361). Supervision, QA, implementation, and review accept arbitrary registered adapters, while structured planning currently supports Claude and Codex (`factory/ARCHITECTURE.md`, lines 121–125; `factory/CONFIGURATION.md`, lines 221–291).

**Where ours is better:** it is substantially more agent- and execution-environment-neutral, and the deterministic Rehearsal plus website gives every attendee the same observable story (`factory/WORKSHOP_OUTLINE.md`, lines 20–24, 57–79, and 89–216).

**Where ours is worse:** configuration and runtime concepts are heavier. An attendee must understand a Project Contract, local configuration, profiles, five or more roles, GitHub Projects, a local server, a scheduler, and evidence artifacts. Addy's “start with one issue and one explicit prompt; add machinery only after observing a real failure” progression is clearer ([Advice, lines 36–81](https://github.com/addyosmani/factory/blob/8af116567166a0a16588b7ab1b9934ece0b775bc/ADVICE.md#L36-L81), [lines 150–168](https://github.com/addyosmani/factory/blob/8af116567166a0a16588b7ab1b9934ece0b775bc/ADVICE.md#L150-L168)).

## Prioritized improvements

### P0 — Add before presenting the factory as production-capable

1. **Prove every acceptance test is red before implementation and green after it.** Extend the QA handoff with the exact focused command. At the QA commit, require that command to fail for the expected assertion; after implementation, require the same command to pass. Store both bounded outputs and revision hashes in the Handoff Receipt. This combines our independent test author with Addy's causal proof.

2. **Introduce a target-specific, human-owned Factory Charter.** Keep `factory.project.toml` as the technical repository interface, but add a separate policy artifact for consequence tier, load-bearing paths, existing-test rules, automatable work, never-automate work, diff/retry budgets, stop conditions, merge authority, and review capacity. Default to stop when the charter is silent. Do not let planning or implementation agents edit it.

3. **Make human merge the default outside the autonomous demo.** Preserve Supervisor-authorized merge as an explicit `autonomous` capability or opt-in profile because it is valuable to demonstrate. Make Standard produce a reviewed PR and stop for a person; require the UI to name who owns the next decision. If the workshop keeps automatic merge, say plainly that this is the moment where human accountability has been delegated.

4. **Add a remote compare-and-swap ticket claim.** Before a worker creates or edits its worktree, push a deterministic claim ref or create an atomic GitHub-owned claim tied to the run ID. Treat conflicts as “already owned.” The local one-operation lock is not sufficient once users run CLI, Control Center, or hosted workers concurrently.

### P1 — High-value product improvements

5. **Add review back-pressure as a number.** Configure `max_awaiting_human_review` and stop new dispatch when full. Show `NEEDS YOU` and `review queue N / limit` at the top of the Control Center. For autonomous profiles, also cap blocked tickets and repeated review-rework loops.

6. **Protect all existing tests and factory policy by default.** A new target's detected contract should include agent instructions, factory configuration, GitHub workflows, migrations, secrets/config surfaces, and existing tests in a review-required category. Separate “never modify” from “may modify only with human approval”; the current single `protected_paths` list cannot express that nuance.

7. **Persist compact immutable run summaries remotely.** Keep detailed local logs, but publish a sanitized run summary or GitHub check/comment containing inputs, revisions, verdicts, unresolved risk, and evidence links. Do not make an ignored laptop directory the only complete history.

8. **Close the maintenance loop.** Add an optional monitor role that observes default-branch CI, gate baseline, dependency advisories, stale tickets, repeated hotspots, and planning/policy gaps. It should file or update issues and never repair in the same run.

9. **Add an adversarial critic for high-risk design and code.** Assured already has architecture conformance and hardening. Give it a distinct critic that asks what assumptions propagated, what behavior is untested, what dead code remains, and whether a stranger can maintain the result. Keep that separate from deterministic gates and correctness review.

### P2 — Workshop and adoption improvements

10. **Teach the capability ladder progressively.** Start with one issue, one agent, one test, one PR, and one human merge. Then add PRD planning, independent QA, parallel worktrees, supervision, and finally optional automated integration. This makes every added component answer a failure attendees have just observed.

11. **Add a concise `LIMITS.md`.** State that worktrees are not sandboxes, local state is not a remote ledger, planning supports only Claude/Codex, GitHub Projects scopes are required, agent logs may expose repository data, setup/gate commands are trusted shell, and formal PR approval may require a second identity.

12. **Add evidence-driven tuning and a decision log.** Track median implementation time, verification reruns, reviewer rejection rate, human wait time, escaped defects, and false gate failures. Let a tuning screen propose policy changes, but require a person to record the evidence and risk accepted.

13. **Package a stable installer or standalone CLI.** `factory init` creates the Project Contract, but the operator still depends on the workshop control-plane checkout. Provide a versioned installation/update path that can safely pin the engine, never overwrite target files silently, and report drift.

## What not to copy

- **Do not replace executable validation with prose-only skills.** Addy's Markdown contracts are elegant, but our schema, path, hash, state-transition, and exact-head validators provide stronger enforcement.
- **Do not make Claude routines the universal scheduler.** Their simplicity is attractive, but our workshop promise is cross-agent and cross-environment. Keep adapters and make hosted execution one option.
- **Do not remove the graphical Control Center or GitHub Projects.** They are our clearest workshop advantage and make multi-ticket evidence legible to attendees.
- **Do not discard the PRD-wide dependency graph.** Addy's one-item runs are excellent for maintenance; they do not replace coherent planning for a product rebrand or multi-slice feature.
- **Do not copy an absolute policy without naming the intended risk model.** “Never automate merge” is a strong safe default, not a law of software. If we offer automated merge, the profile, identity, evidence, and accountability tradeoff must be unmistakable.

## Recommended positioning

Position Software (re)-Factory as **the visual, executable lab for learning how planning contracts, isolated workers, independent QA, supervision, review feedback, and evidence fit together**. Position Addy's approach as a strong reference for the smallest production operating model.

A credible message is:

> Start with repository instructions, real tests, a protected branch, and human merge. Add the Software (re)-Factory control plane when a PRD must become coordinated tickets, multiple agents need isolated execution, or people need one place to inspect the evidence. Keep the controls proportional, and add autonomy only after the verification budget earns it.

That framing makes the competitor evidence for our workshop story rather than a competing claim that we need more machinery everywhere.

## Method and source quality

The competitor repository was cloned at `8af116567166a0a16588b7ab1b9934ece0b775bc`. I inspected its README, architecture, limits, advice, installer, charter, contract, workflow skills, agents, gates, hooks, doctor, and tests. Its own `bash tests/run.sh` completed successfully: claim, documentation, doctor, gates, hook, install, and negative-test proof all passed. Claims above link to commit-pinned first-party source files.

The local comparison used the current `codex/agent-supervisor` worktree, including its uncommitted Supervisor, review-loop, Control Center, Project Contract, and generic-repository changes. No runtime claims here should be read as an audit of production security; this is an architecture and workflow comparison based on source and passing project tests already reported for this branch.
