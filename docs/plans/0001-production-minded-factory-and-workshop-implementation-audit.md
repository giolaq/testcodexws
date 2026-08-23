# Production-minded Factory and Workshop Implementation Audit

**Roadmap:** `0001-production-minded-factory-and-workshop-roadmap.md`  
**Release identity:** `workshop-v1.1.0`  
**Branch:** `codex/agent-supervisor`  
**Audited implementation baseline:** `cff4397`  
**Audit date:** 2026-08-23

## Verdict

The roadmap's local implementation and credential-free Standard Rehearsal are
complete and verified. The release is not yet publishable because the
owner-authorized disposable Live GitHub smoke has not run. The public Vercel
site also still serves an older build, and the private repository has not yet
been tagged or enabled as a public template. These are release gates, not
silently accepted omissions.

| Scope | Verdict | Authoritative evidence |
| --- | --- | --- |
| Milestones 0–6 | PASS | Source contracts, operator surfaces, focused tests, full Python suite, website suite, and Standard Rehearsal |
| Milestone 7 local behavior | PASS | Compatibility/update tests, release audit, clean-clone Standard Rehearsal, link/secret/version checks |
| Disposable Live GitHub path | PENDING OWNER AUTHORIZATION | Implemented by `release_check.run_live_github_smoke`; execution creates a Project, Issue, PR, reviews, merge, claims, comments, and Claude usage |
| Deployed website identity | FAIL — old deployment | `https://software-refactory-workshop.vercel.app/` does not currently render `workshop-v1.1.0` or the new evidence/Monitor language |
| Tag and public-template settings | PENDING | Repository is private, `main` is the default branch, and `isTemplate` is false |

## Milestone evidence

### Milestone 0 — Policy and profile contracts: PASS

- ADR 0007 supersedes the automated-merge portion of ADR 0005 and makes Lean,
  Standard, and Assured human-merge profiles. Autonomous Demo is isolated as
  an explicit opt-in.
- `factory/factory_charter.py` defines the versioned, target-specific Charter,
  all required policy/limit/path fields, exact-hash approval, conservative
  draft generation, and fail-closed validation.
- `factory/planning_pipeline.py` binds one profile, Charter governance payload,
  Project Contract hash, policy hashes, and approvals to the Planning Run.
  `factory/orchestrator.py` rejects execution state that does not match those
  values.
- `factory/evidence_packet.py` requires and renders Charter schema, hash,
  profile, and merge authority.
- `factory/CONFIGURATION.md` defines the precedence of explicit CLI values,
  saved attendee settings, Project Contract, Factory Charter, role contracts,
  and policy.
- Migration behavior is documented in `factory/COMPATIBILITY.md` and enforced
  by the legacy-governance and causal-evidence migration tests.

Proof:

- `test_factory_charter.py`: all six Charter creation, approval, invariant, and
  fail-closed tests.
- `test_factory_runtime.py`:
  `test_execution_rejects_a_ticket_planned_under_different_governance`,
  `test_legacy_approved_tickets_fail_with_a_governance_migration_instruction`,
  `test_existing_run_cannot_silently_switch_to_a_new_charter_hash`,
  `test_code_review_rework_stops_at_human_merge_gate_then_exact_head_can_merge`,
  and `test_autonomous_demo_requires_opt_in_then_records_supervisor_merge`.
- `test_evidence_packet.py` validates the governed, sanitized packet.

### Milestone 1 — Causal Acceptance Test evidence: PASS

- `factory/acceptance_evidence.py` builds one bounded focused command and
  distinguishes a behavior assertion from pass, skip, collection error,
  command error, timeout, and unrelated failure.
- `factory/orchestrator.py` runs that command before implementation and after
  implementation, binds it to one hash, protects the QA revision and accepted
  test hashes, and records bounded RED/GREEN evidence in Handoff Receipts.
- The Assured negative-proof role uses a disposable detached worktree, removes
  or reverses only non-test candidate changes, reruns the accepted command, and
  proves the original candidate head/status were not changed.
- The Control Center and Evidence Packet display `RED PROVED`, `GREEN PROVED`,
  classifications, revisions, command hash, and actionable failures.

Proof:

- All four `test_acceptance_evidence.py` tests.
- `test_orchestrator_qa.py` tests for already-passing tests, collection and
  mapping failures, identical RED/GREEN command, new and existing test
  protection, and the Assured role sequence.
- `test_factory_runtime.py` exercises the deterministic QA/implementation path,
  a verifier retry, review rework, and all profile sequences.
- `factory release-check --rehearsal` proves five Standard Tickets each carry
  valid causal evidence and required role receipts without model credentials.

### Milestone 2 — Back-pressure and distributed claims: PASS

- Charter limits include maximum review work, maximum human-blocked work, and
  an oldest-wait threshold.
- `Factory.human_attention_snapshot` counts QA Review, PR review/merge, and
  answerable human blocks. Product and alignment remain serial prerequisites,
  so ticket dispatch cannot overlap them. Dispatch stops at any configured
  queue/age limit while already-running work may publish its evidence.
- The Control Center puts `NEEDS YOU`, the queue/limit reason, and oldest human
  action at the top of the journey.
- `factory/github_backend.py` claims a deterministic remote ref with a
  non-force push, records sanitized ownership remotely, recognizes same-run
  recovery, rejects losers before worktree/agent creation, and releases only
  through an explicit audited operator action.
- Local reset does not delete or release remote evidence.

Proof:

- `test_github_backend.py::test_remote_claim_is_atomic_resumable_and_explicitly_released`.
- `test_factory_runtime.py::test_losing_remote_claim_never_creates_a_worktree_or_starts_an_agent`.
- `test_factory_runtime.py::test_dispatch_pauses_when_human_review_capacity_is_full`.
- Fresh-state and reset tests in `test_factory_runtime.py` and release-claim
  action tests in `test_control_center.py`.

### Milestone 3 — Risk-proportional triage and gates: PASS

- `factory/triage.py` returns exactly `READY_TO_IMPLEMENT`, `READY_TO_PLAN`,
  `NEEDS_INFORMATION`, or `WAIT`, and records its reason.
- Charter consequence, declared paths, load-bearing paths, review-required
  paths, and profile select fast/full/deep gates. A load-bearing path selects
  deep gates and architecture/program approvals; Lean fails closed if it cannot
  satisfy that planning depth.
- Required skipped/unavailable gates are `MISCONFIGURED`, never PASS.
- Assured adds read-only cleanup, architecture conformance, hardening, critic,
  negative proof, and final verifier roles without conflating their findings
  with deterministic gate results.
- Evidence records triage, risk, selected level/reason, stage/agent/gate/human
  time, retries, verifier rejection, and peak review queue. No cost value is
  invented.

Proof:

- Both `test_triage.py` tests.
- `test_factory_runtime.py::test_required_skipped_gate_is_misconfigured_not_green`.
- Lean/Assured role-sequence tests in `test_factory_runtime.py` and
  `test_orchestrator_qa.py`.
- Planning tests for Charter-selected approvals, path-selected approvals, and
  unsupported Lean governance.

### Milestone 4 — Durable evidence and Monitor: PASS

- `factory/run_summary.py` defines bounded `factory-run:v1` remote evidence
  containing governed revisions, adapters/roles, claim, verdicts, decisions,
  metrics, risks, and links. It excludes raw prompts, logs, environment values,
  and credentials.
- Live state reconstruction in `factory/orchestrator.py` reads remote claims,
  Issues, PR heads, merge/review state, and run-summary comments before trusting
  local state.
- `factory/monitor.py` is read-only by default, scopes CI health to the
  configured default branch, detects advisories, stale claims/Tickets, review
  waits, repeated findings, hotspots, and governance drift, and updates one
  stable remote finding only under explicit publication.
- Control Center evidence separates stage time, agent time, gate overhead, and
  human wait.

Proof:

- Both `test_run_summary.py` tests, including seeded secret exclusion.
- All four `test_monitor.py` tests, including idempotent publication and stale
  remote claims.
- Fresh-checkout recovery and stale-head tests in `test_factory_runtime.py`.
- Remote summary recovery tests in `test_github_backend.py`.

### Milestone 5 — Execution boundaries: PASS

- `factory/adapter_capabilities.py` validates filesystem mode, allowed roots,
  network expectation, environment allowlist, credential names, timeout, and
  local/container/hosted execution type for every configured adapter.
- Agent roles receive allowlisted environment values. Planning and supported
  review roles use read-only adapter modes; Git status/head checks discard a
  read-only role that mutates its worktree.
- Charter paths separate `never_modify` from
  `requires_human_approval`. Conservative defaults cover Charter/policy,
  instructions, CI, migrations, auth/security, secret/config surfaces, and
  existing tests.
- `factory/LIMITS.md` accurately states loopback API, trusted shell, worktree,
  identity, provider-log, permission, timeout, cost, and concurrency boundaries.
  Container and hosted values are adapter interfaces, not claimed local
  isolation.

Proof:

- Both `test_adapter_capabilities.py` tests, including unrelated credential
  exclusion.
- `test_factory_runtime.py::test_read_only_role_mutation_is_discarded_and_fails_closed`.
- Existing-test protection tests in `test_orchestrator_qa.py` and Charter path
  tests in `test_factory_charter.py`.

### Milestone 6 — Capability-ladder workshop: PASS

- `workshop-guide/app/page.tsx` starts with the minimum responsible loop,
  introduces concrete failure modes, and then teaches PRD planning, human
  revision/alignment, causal QA, claims/worktrees/receipts, review rework,
  Supervisor recommendation, exact-revision human merge, Monitor, and Factory
  Canvas. Autonomous Demo is outside the 100-minute core.
- Every exercise uses the same four operator questions: what is happening, why
  it stopped, what evidence to inspect, and what the human decides.
- Live and Rehearsal are side by side but each step names the active route.
  Live includes the GitHub Project checkpoint; Rehearsal requires no model or
  GitHub credentials.
- Nine annotated Control Center/GitHub screenshots and three narrative
  illustrations are tracked. Facilitator, outline, CLI docs, Control Center,
  and website use Plan/Build/Verify/Review and the same role vocabulary.
- The Factory Canvas includes consequence tier, merge authority, review
  capacity, load-bearing paths, gate budget, durable remote record, and Monitor
  owner.

Proof:

- Eight website tests pass. The rendered-story test covers both tracks,
  screenshots, causal evidence, `NEEDS YOU`, claims, human merge, Autonomous
  Demo warnings, Monitor, custom adapters, and troubleshooting.
- Structural tests require `lang=en`, one `h1`, a labeled navigation region,
  `main`, and useful alt text on every instructional image.
- Visible copy remains below the 3,200-word budget, and the documented timeline
  remains 100 minutes.

### Milestone 7 — Release and adoption hardening: LOCAL PASS, LIVE PENDING

- `factory/COMPATIBILITY.md` documents migration and reset behavior.
- `factory/workshop_update.py` provides a versioned preview/apply path, records
  managed hashes/modes, reports drift, refuses silent overwrite, and never
  manages attendee product source.
- `factory/control_center.py` routes operator mutations through one validated,
  allowlisted action registry.
- `factory/release_check.py` performs local secret, generated-state, obsolete
  language, link/asset, clean-tree, and version checks; its clean-clone Standard
  Rehearsal covers planning revision, approvals, five Tickets, QA red/green,
  review rework, human merge, Monitor, Canvas, and Evidence Packet.
- The Live smoke implementation covers Charter approval/preflight, Project and
  Issue publication, remote claim, Claude QA/implementation/supervision,
  deterministic review request/repair/approval, exact-revision human merge,
  remote summary, Monitor, Evidence Packet, local reset, and fresh recovery.
- CI installs the test runtime dependencies before the full unit suite. Release
  documentation uses the setup-created `.factory/venv`, preventing missing
  `pytest` from masquerading as causal-evidence failures.

Proof:

- All four `test_workshop_update.py` tests and the repository release-command
  contract test.
- Local release audit: PASS for `workshop-v1.1.0`.
- Clean Standard Rehearsal: PASS for plan `410326debec4`, five Tickets, Evidence
  Packet, and healthy Monitor.
- Disposable Live smoke: not executed; see Remaining release gates.

## Required end-to-end scenario matrix

| Roadmap scenario | Evidence | Verdict |
| --- | --- | --- |
| Two runners race; one owns and one agent starts | Atomic remote-ref test plus losing-run pre-worktree test | PASS |
| QA test already passes | Acceptance classification and QA rejection tests | PASS |
| QA test does not collect | Acceptance classification and QA retry/block tests | PASS |
| Human queue fills and later permits dispatch | Runtime capacity snapshot/dispatch test; limits recompute on each scheduling cycle | PASS |
| Review comments return to the same branch | Standard runtime review-rework test and clean Rehearsal attempt history | PASS |
| Standard cannot auto-merge | Human exact-head runtime test | PASS |
| Autonomous Demo needs opt-in and exact head | Autonomous Demo runtime and Control Center tests | PASS |
| Local reset preserves remote evidence | Reset scope tests and Live recovery implementation | PASS locally; remote proof pending Live smoke |
| Fresh checkout reconstructs shared state | Three runtime recovery tests plus remote summary parsing tests | PASS with fakes; remote proof pending Live smoke |
| Monitor publishes at most one unchanged finding | Monitor idempotence test | PASS |

## Verification record

Run from the repository root on 2026-08-23:

```text
.factory/venv/bin/python -m unittest discover -s factory/tests -p 'test_*.py'
206 tests · PASS · 34.568s

npm --prefix workshop-guide test
8 tests · PASS

npm --prefix workshop-guide run lint
PASS

npm --prefix workshop-guide run build
PASS

./factory/factory release-check
Local release audit: PASS (workshop-v1.1.0)

./factory/factory release-check --rehearsal
Standard Rehearsal PASS (410326debec4, 5 tickets, Evidence Packet, Monitor healthy)

./factory/factory --version
factory workshop-v1.1.0
```

The first full-suite attempt used the host Python 3.14 interpreter and failed
eight integration tests because that interpreter lacked `pytest`. The supported
`.factory/venv` invocation above passed all 206 tests. Commit `cff4397` also
made CI install `demo-app/requirements.txt` and changed the release runbooks to
use the prepared virtual environment, so this dependency error is now explicit
and reproducible.

## Remaining release gates

1. Confirm a dedicated GitHub repository is disposable and authorize external
   mutations and Claude usage.
2. From that repository, run:

   ```sh
   ./factory/factory release-check --live-smoke \
     --confirm-disposable-repo
   ```

3. Inspect the created Project, Issue, PR review/rework, human merge, remote
   claim/run summary, Monitor output, reset, and fresh recovery.
4. Merge the release candidate to `main` only after the Live smoke passes.
5. Deploy the new website and verify the rendered footer contains
   `workshop-v1.1.0` plus the RED/GREEN, `NEEDS YOU`, Autonomous Demo, and
   Monitor sections.
6. Create and verify tag `workshop-v1.1.0`; make the repository public and
   enable template mode on the owner-approved schedule.

The roadmap must remain **implementation in progress** until these external
gates are complete. Do not tag or publish the new workshop before the Live
smoke passes.
