# Production-minded Factory and Workshop Roadmap

**Status:** Release candidate — Live delivery/recovery and CI passed; packet rerun pending
**Owner:** Workshop lead
**Created:** 2026-08-23
**Scope:** Factory engine, Control Center, GitHub integration, workshop website,
facilitator material, and release validation

Implementation evidence: [roadmap audit](0001-production-minded-factory-and-workshop-implementation-audit.md)

## Inputs

- [Human judgment doesn't leave the software factory. It relocates.](/Users/glaquidara/.codex/attachments/3fa70d3f-f894-4a38-993a-9dffab55e4da/pasted-text.txt)
- [Competitive analysis: Addy Osmani's Factory and Software (re)-Factory](../research/addyosmani-factory-competitive-analysis.md)
- [Current workshop specification](../specs/0001-evidence-driven-factory-workshop.md)
- [Current architecture](../../factory/ARCHITECTURE.md)

## Outcome

Evolve Software (re)-Factory into a visual, executable workshop that retains
its strong PRD planning, multi-agent coordination, independent QA, and Control
Center while adopting production-minded controls:

- a person owns the policy and normal shipping decision;
- tests prove causality, not only chain of custody;
- human attention is a bounded factory resource;
- distributed workers cannot claim the same Ticket;
- verification effort is proportional to change risk;
- compact, sanitized evidence survives the local process; and
- monitoring continues after a pull request is delivered.

The project remains a reference implementation and teaching environment, not a
claim of secure unattended production orchestration.

## Product position

Software (re)-Factory is the **visual orchestration and learning layer** used
when a PRD must become coordinated work, several agents need isolated
execution, or a person needs one place to inspect decisions and evidence.

The minimum production baseline remains repository instructions, protected
branches, real tests, reviewable pull requests, and accountable human merge.
The factory adds machinery only where it answers a demonstrated coordination,
verification, recovery, or comprehension problem.

## Design principles

1. **Human judgment moves; it does not disappear.** Product intent, policy,
   material design decisions, accepted evidence, and normal merge authority
   have named human owners.
2. **Green must mean the requested behavior was detected.** A test that never
   failed for the missing behavior is not sufficient acceptance evidence.
3. **Human attention is capacity.** The scheduler must stop producing review
   work when the configured human queue is full.
4. **GitHub owns shared coordination state.** Local state may enrich the UI but
   cannot be the only record of claims, revisions, verdicts, and decisions.
5. **Controls are risk-proportional.** Small changes do not need the same
   planning and verification topology as load-bearing changes.
6. **Roles are stable; adapters are replaceable.** Claude, Codex, Cursor, and
   custom adapters operate behind the same authority boundaries.
7. **Recovery is explicit and auditable.** Reset, retry, claim release, and
   override actions identify what they change and never silently rewrite remote
   work.
8. **Evidence is durable but bounded.** Publish verdicts, revisions, timing,
   and unresolved risk; keep credentials, unrestricted logs, and hidden model
   reasoning out of remote records.

## Target operating model

The normal lifecycle becomes:

```text
Triage
  -> Plan when required
  -> Human alignment
  -> Remote Ticket claim
  -> QA proves red
  -> Implementation
  -> Required gates prove green
  -> Independent code review and bounded rework
  -> Supervisor merge recommendation
  -> Human exact-revision merge
  -> Monitor
```

The Agent Supervisor coordinates dependency-ready workers, reads Handoff
Receipts, pauses unsafe dispatch, and recommends the next action. It does not
own product intent, edit code, waive gates, change the Factory Charter, or
replace the normal human shipping decision.

### Authority boundaries

| Actor | Owns | Cannot do |
| --- | --- | --- |
| Human operator | Factory Charter, material approvals, exceptions, normal merge | Silently waive required evidence |
| Orchestrator | State transitions, validation, retries, exact-revision enforcement | Invent agent results or policy exceptions |
| Agent Supervisor | Dispatch proposals, synchronization, evidence-backed blocks, merge recommendation | Edit code, change scope, waive gates, merge by itself |
| Planning experts | Product, architecture, design, and slice proposals | Approve their own proposals or edit the Charter |
| QA Agent | New Ticket Acceptance Tests and focused test command | Implement product behavior or weaken existing tests |
| Implementation Agent | Ticket-scoped source changes | Modify accepted QA evidence or protected policy |
| Code Review Agent | Exact-revision technical verdict and actionable comments | Modify the worktree, merge, or approve a different head |
| Monitor Agent | Health findings and proposed follow-up Tickets | Repair findings in the same monitoring run |

### Factory Profiles after this roadmap

| Profile | Intended use | Planning | Verification | Merge authority |
| --- | --- | --- | --- | --- |
| Lean | Small, low-risk, bounded change | Triage, intent, small slice | Existing tests and human diff review | Human |
| Standard | Normal workshop and shared product work | Four experts, Product Review and final alignment | Independent QA red/green proof, required gates, code review | Human |
| Assured | Load-bearing or higher-consequence work | Four experts with Charter-selected stage approvals | Standard plus deep gates, critic, architecture conformance, and negative proof | Human |
| Autonomous Demo | Explicit workshop demonstration only | Standard | Standard, exact-head checks, visible warnings | Supervisor recommendation executed by orchestrator |

`Autonomous Demo` preserves the current complete automation loop without
presenting it as the default production accountability model.

## Work plan

### Milestone 0 — Align policy and profile contracts

**Goal:** establish the human accountability boundary before adding more
automation.

Deliverables:

- Add an ADR that supersedes the merge-authority portion of ADR 0005:
  Standard and Assured stop at an exact-revision human merge gate; Autonomous
  Demo retains Supervisor-authorized merge.
- Add a versioned, target-specific `factory.charter.toml` separate from
  `factory.project.toml`.
- Define Charter fields for consequence tier, load-bearing paths, editable and
  review-required areas, existing-test policy, required planning approvals,
  gate level, retry/diff budgets, review capacity, stop conditions, and merge
  authority.
- Make the Charter human-owned and protected from every modifying Agent Role.
- Make `factory init` generate a conservative draft that must be reviewed and
  explicitly accepted before a Live Run.
- Store the authoritative profile and Charter hash once per run; planning and
  execution must read the same selection.
- Add schema migration for existing local runs and clear diagnostics for old
  configurations.

Acceptance criteria:

- Standard and Assured cannot automatically merge.
- Autonomous Demo requires an explicit opt-in and displays its delegated
  accountability before the run starts.
- A missing, invalid, unapproved, or agent-modified Charter fails closed.
- The Evidence Packet names the Charter version, hash, profile, and merge
  authority.
- Project Contract, Charter, profile, roles, and policy have one documented
  precedence order.

### Milestone 1 — Make acceptance evidence causal

**Goal:** prove that a QA-authored Acceptance Test detects the requested missing
behavior and passes because of the implementation.

Deliverables:

- Extend the QA contract and Handoff Receipt with the focused test command,
  expected failure classification, test revision, and bounded output.
- Run the focused test against the pre-implementation revision and require a
  behavior assertion failure. Collection errors, missing dependencies, command
  errors, timeouts, and unrelated failures do not count as red evidence.
- Run the identical focused command after implementation and require green.
- Protect both new QA files and pre-existing tests according to the Charter.
- For Assured, add a disposable negative-proof verifier that reverses non-test
  candidate changes, reruns the focused test, confirms the expected failure,
  and always restores the worktree.
- Display `RED PROVED`, `GREEN PROVED`, or an actionable failure reason in the
  Ticket evidence view.

Acceptance criteria:

- Every Standard and Assured Ticket with new Acceptance Tests records a valid
  red and green result against named revisions.
- An already-passing, irrelevant, uncollectable, or silently skipped test is
  rejected.
- Implementation cannot change the accepted command or protected test hashes.
- Negative proof cannot alter the candidate branch or leak a temporary reverse
  patch into another worktree.
- Rehearsal mode demonstrates one deterministic red-to-green path without
  credentials.

### Milestone 2 — Add back-pressure and distributed claims

**Goal:** prevent duplicate ownership and stop the factory when people cannot
keep up with the decisions it produces.

Deliverables:

- Add `max_awaiting_human_review`, `max_blocked_for_human`, and optional oldest
  wait thresholds to the Charter/profile runtime configuration.
- Count Product Review, alignment, QA review, PR review/merge, and answerable
  blocked questions as human-attention work.
- Stop new dispatch when a configured limit is reached. Running work may finish
  and publish evidence, but must not create more review work.
- Put `NEEDS YOU`, the oldest required decision, and `queue N / limit` at the
  top of the Control Center.
- Claim a Ticket through a deterministic remote Git ref before creating the
  implementation worktree. The first non-force push wins; other runners report
  the existing owner and do not start an agent.
- Record the run ID, Ticket, base revision, and claim time in a sanitized GitHub
  comment or other durable remote record.
- Support same-run recovery and an explicit, audited operator action to release
  an abandoned claim. Reset must not release remote claims implicitly.

Acceptance criteria:

- In a two-runner race, exactly one runner owns the Ticket and only one agent is
  started.
- Restarting the winning run recognizes and resumes its claim.
- Dispatch pauses at the configured human queue limit and resumes after a
  decision reduces the queue.
- The Control Center explains why dispatch is paused and links to the required
  human action.
- A local reset cannot make a remotely claimed Ticket appear unowned.

### Milestone 3 — Add risk-proportional triage and verification

**Goal:** avoid running the full factory topology for every change while making
high-risk verification stricter.

Deliverables:

- Add a deterministic Triage result:
  `READY_TO_IMPLEMENT`, `READY_TO_PLAN`, `NEEDS_INFORMATION`, or `WAIT`.
- Allow the Charter and touched-path classification to select planning
  approvals and `fast`, `full`, or `deep` gate levels.
- Define gate behavior:
  - `fast`: formatting, lint, and types where configured;
  - `full`: fast plus focused/full tests and build;
  - `deep`: full plus Charter-selected security, mutation, architecture, or
    other expensive checks.
- Treat a missing required tool or skipped required gate as `MISCONFIGURED`,
  never green.
- Add an independent adversarial critic only for Charter-selected higher-risk
  changes. It identifies propagated assumptions, untested behavior, scope
  drift, dead code, and maintainability risks; deterministic gates remain
  separate.
- Record the reason for the selected path and actual verification duration.

Acceptance criteria:

- A trivial bounded issue can proceed without four unnecessary planning agents.
- A load-bearing path cannot select a weaker gate level than its Charter rule.
- Required skipped or unavailable checks fail closed with a repair instruction.
- The UI distinguishes deterministic gate failures from agent review findings.
- The Evidence Packet records triage, risk classification, selected controls,
  durations, and any human override.

### Milestone 4 — Make evidence durable and add monitoring

**Goal:** preserve a compact operational history and continue learning after
delivery.

Deliverables:

- Define a versioned, sanitized `factory-run:v1` summary for GitHub Issue/PR
  comments or Checks. Include input hashes, role/adapters, revisions, claims,
  verdicts, gate durations, retries, unresolved risks, human decisions, and
  Evidence Packet location.
- Keep raw prompts, unrestricted logs, environment values, credentials, and
  hidden model reasoning local and out of remote summaries.
- Reconcile restart state from GitHub claims, Tickets, PR heads, comments, and
  merge state before trusting local `.factory` state.
- Add a read-only `factory monitor` command for default-branch CI health,
  dependency advisories, stale claims/Tickets, review wait, repeated verifier
  findings, changed hotspots, and Charter/Project Contract drift.
- Make publishing monitor findings an explicit option. Published monitoring
  may open or update a Ticket but never repairs the finding in the same run.
- Track stage time, agent time, gate time, retry count, verifier rejection,
  human wait, and peak review queue. Do not invent cost data when an adapter
  cannot report it.

Acceptance criteria:

- A fresh checkout can reconstruct shared Ticket ownership and PR state without
  copying another machine's `.factory` directory.
- Remote records contain enough information to identify the governed revision
  and decision without containing seeded secret-like values.
- Re-running Monitor is idempotent and does not duplicate unchanged findings.
- The Control Center shows useful delay separately from verification overhead
  and human wait.
- Monitor cannot mutate product code or merge a PR.

### Milestone 5 — Strengthen execution boundaries

**Goal:** make local execution limitations explicit and reduce avoidable
credential and mutation exposure.

Deliverables:

- Give every Agent Adapter a declared capability profile: filesystem mode,
  allowed working roots, network expectation, environment allowlist, timeout,
  and credential names.
- Run planning, QA review, code review, architecture conformance, critic, and
  monitoring roles read-only wherever the adapter can enforce it.
- Pass only role-required environment variables rather than inheriting the
  complete Control Center environment.
- Expand default protected categories to include factory policy, agent
  instructions, CI, migrations, authentication/security configuration,
  secrets/config surfaces, and pre-existing tests.
- Separate `never_modify` from `requires_human_approval`; do not overload one
  protected-path list.
- Add an optional container or hosted-runner adapter interface. Continue to
  state that Git worktrees isolate Git state, not processes, networks, or
  credentials.
- Add a concise `LIMITS.md` covering trusted shell commands, local API scope,
  sandbox limitations, identity requirements, model-log exposure, GitHub
  permissions, and cost/concurrency responsibility.

Acceptance criteria:

- A read-only role modifying its worktree fails closed and its result is
  discarded.
- Seeded unrelated credentials are absent from a role process and all exported
  evidence.
- Unsupported adapter controls appear as explicit limitations, not implied
  guarantees.
- Existing tests and policy cannot be changed unattended.
- Production-boundary documentation matches enforceable behavior.

### Milestone 6 — Reframe the workshop as a capability ladder

**Goal:** teach why each factory component exists before asking attendees to
operate the complete system.

Do not restore the retired unattended comparison exercise. Use one coherent,
guided story:

1. Start with the minimum responsible loop: clear issue, one agent, one real
   test, one PR, and a human merge.
2. Introduce the failure modes: ambiguous intent, colliding workers, weak tests,
   excessive review work, lost decisions, and stale evidence.
3. Turn the PRD into Product Review, System Architecture, Program Design, and
   Vertical Slices only when the work requires them.
4. Show a person revising Product Review and approving alignment.
5. Show QA proving red before implementation and green afterward.
6. Show remote claim, isolated worker, Handoff Receipt, and Supervisor dispatch.
7. Show code review comments returning to the same development branch.
8. End the normal path at a named human exact-revision merge decision.
9. Show Autonomous Demo as an optional contrast, with its delegated
   accountability made explicit.
10. Finish with Monitor findings and a Factory Canvas for the attendee's use
    case.

Website and documentation changes:

- Lead with a concise definition, the human-attention bottleneck, and the
  promise: make decisions, ownership, evidence, and failure easier to inspect.
- Show CLI and Control Center routes together, but make one the active path at
  each exercise.
- Add annotated screenshots for opening the Control Center, reading `NEEDS
  YOU`, inspecting red/green proof, reviewing a Supervisor decision, opening
  the GitHub Project, and performing the final human merge.
- Put `What is happening`, `Why it stopped`, `What evidence to inspect`, and
  `What you decide` on every hands-on step.
- Keep the Live Run generic-repository path and the credential-free Rehearsal
  path behaviorally aligned.
- Update the Factory Canvas with consequence tier, merge authority, review
  capacity, load-bearing paths, gate budget, remote record, and monitoring
  owner.
- Teach that more agents and more checks are costs, not measures of quality.
- Keep production limitations beside the relevant step rather than in a large
  disclaimer at the end.

Acceptance criteria:

- A self-paced attendee can open the Control Center, identify the current
  phase, explain why it is waiting, complete the required human action, inspect
  evidence, recover locally, and reach a human-reviewed PR using only the site.
- The website, CLI help, Control Center, GitHub Project instructions,
  facilitator guide, and outline use the same lifecycle and role vocabulary.
- The normal story never implies that an agent's approval transfers human
  accountability invisibly.
- Website tests cover Live and Rehearsal paths, screenshots, red/green proof,
  back-pressure, claims, human merge, Autonomous Demo warnings, and monitoring.
- The 100-minute core remains achievable by keeping Assured, hosted sandboxing,
  and monitoring implementation details optional.

### Milestone 7 — Release and adoption hardening

**Goal:** ship the new operating model without invalidating existing workshop
runs or increasing setup confusion.

Deliverables:

- Add state/config migrations and an explicit compatibility policy.
- Package a versioned install/update path that does not overwrite target files
  silently and reports drift.
- Consolidate repeated Control Center action wiring behind one validated action
  registry before adding the new actions.
- Add a clean-checkout Standard Rehearsal acceptance test from PRD through human
  merge-ready evidence and Monitor preview.
- Add a disposable Live GitHub smoke test covering Charter approval, Project
  publication, remote claim, red/green proof, PR review/rework, human merge,
  remote run summary, and reset/recovery.
- Run secret scanning, documentation link checks, accessibility checks, Python
  tests, website tests, and a public-template audit before tagging the release.
- Publish migration notes that name changed merge behavior and explain how to
  opt into Autonomous Demo.

Acceptance criteria:

- Existing runs fail with a useful migration instruction rather than corrupting
  state.
- A clean attendee repository can complete Rehearsal without model or GitHub
  credentials.
- A disposable Live repository completes the golden path using only documented
  setup.
- Reset changes only the scope named in its confirmation and never implicitly
  deletes remote GitHub evidence.
- Source, website, CLI, and release tag show one version identity.

## Suggested Ticket breakdown

| ID | Ticket | Depends on |
| --- | --- | --- |
| F-01 | Record merge-accountability ADR and profile changes | — |
| F-02 | Implement and validate the human-owned Factory Charter | F-01 |
| F-03 | Make one profile/Charter selection authoritative per run | F-02 |
| F-04 | Add human exact-head merge gate and Autonomous Demo opt-in | F-01, F-03 |
| F-05 | Extend QA receipts with focused red/green proof | F-02 |
| F-06 | Add Assured negative-proof verifier | F-05 |
| F-07 | Enforce existing-test and policy protection categories | F-02 |
| F-08 | Add human-review capacity and scheduler back-pressure | F-02 |
| F-09 | Add atomic remote Ticket claim and audited release | F-03 |
| F-10 | Add risk triage and fast/full/deep gate selection | F-02 |
| F-11 | Publish sanitized remote run summaries and reconcile state | F-09 |
| F-12 | Add metrics and idempotent Monitor Agent | F-10, F-11 |
| F-13 | Add adapter capability and environment allowlist contracts | F-02 |
| F-14 | Consolidate Control Center action/state presentation | F-04, F-08, F-11 |
| W-01 | Rewrite workshop narrative as a capability ladder | F-01, F-05, F-08 |
| W-02 | Add human-decision and evidence instructions/screenshots | F-14, W-01 |
| W-03 | Update Factory Canvas, facilitator guide, and production limits | F-02, F-12, W-01 |
| R-01 | Add migration, rehearsal, Live smoke, security, and release checks | All required F/W Tickets |

Tickets should be vertical slices where possible. For example, F-08 should
include configuration, scheduler behavior, Control Center explanation,
receipts, deterministic rehearsal behavior, and tests rather than creating
separate backend and frontend Tickets with no observable outcome.

## Verification strategy

Every implementation Ticket must include:

1. a failing behavior-level test or explicit non-code documentation assertion;
2. the smallest implementation that makes it pass;
3. regression coverage for fail-closed behavior;
4. a Control Center or CLI contract test where the behavior is operator-facing;
5. Rehearsal coverage for workshop-critical behavior; and
6. a check that exported/remote evidence excludes seeded secrets.

Required end-to-end scenarios:

- Two runners race for one Ticket; exactly one starts.
- A QA test already passes before implementation; the Ticket is blocked.
- A QA test fails to collect; the Ticket is blocked with a different reason.
- Human review capacity is full; new dispatch stops and later resumes.
- Code review requests changes; implementation repairs the same PR and all
  evidence is regenerated for the new head.
- Standard reaches a human merge gate and cannot auto-merge.
- Autonomous Demo merges only after explicit opt-in and exact-head validation.
- A local reset preserves remote claims, Issues, Project items, PRs, and run
  summaries.
- A fresh checkout reconstructs shared state and identifies the next human
  action.
- Monitor detects a seeded stale claim and publishes at most one finding.

## Success measures

The roadmap is successful when:

- 100% of new Standard/Assured Acceptance Tests have valid red and green proof;
- 0 Standard/Assured PRs merge without a human exact-revision action;
- exactly one owner wins every tested distributed Ticket race;
- no new work starts above the configured human-review capacity;
- every stopped run names the owner, reason, evidence, and recovery action;
- a fresh checkout can recover shared GitHub state without another machine's
  local files;
- remote records and Evidence Packets pass seeded-secret tests;
- attendees can identify where product, QA, review, and shipping judgment
  belong; and
- the core workshop still fits its 100-minute target without presenting omitted
  production controls as already implemented.

Avoid throughput or agent-count vanity metrics. Track useful stage time,
verification overhead, human waiting time, retries, verifier rejection, escaped
defects, and false gate failures. Use those measurements to propose Charter
changes; require a person to approve every policy change.

## Explicit non-goals

- Replacing the Control Center with a text-only workflow.
- Replacing executable validation with prose-only agent instructions.
- Making Claude the only supported adapter.
- Treating Git worktrees as security sandboxes.
- Capturing or publishing hidden model chain-of-thought.
- Automatically repairing findings discovered by Monitor.
- Automatically editing the Factory Charter from run metrics.
- Running all four planning experts for every bounded maintenance issue.
- Reintroducing the retired unattended comparison exercise.
- Claiming that one successful workshop run proves higher quality or lower cost.

## Implementation order and release gates

Implement in this order:

1. Milestone 0: authority and Charter contracts.
2. Milestone 1: causal evidence.
3. Milestones 2 and 3: capacity, claims, triage, and verification budget.
4. Milestones 4 and 5: durability, monitoring, and execution boundaries.
5. Milestone 6: rewrite the workshop against implemented behavior.
6. Milestone 7: migrations, full-story verification, and release.

Do not teach a control as available before its behavior and fail-closed tests are
merged. Do not enable Autonomous Demo by default. Do not publish the new
workshop version until the clean Rehearsal and disposable Live smoke scenarios
both pass.
