# Evidence-driven Software (re)-Factory workshop

## Problem Statement

The workshop demonstrates a capable factory, but its learning path currently
competes with a lights-off control experiment, treats approval as mostly
passive, exposes operational detail before attendees have a simple mental
model, and does not leave attendees with a complete, portable design for their
own use case. Its configuration is flexible, but it does not yet express
change-risk profiles, durable role contracts, repository policy, or structured
handoff evidence. A live session can therefore look like an impressive agent
demo instead of teaching developers how to plan, supervise, verify, and adapt a
software factory.

Attendee setup also needs a single reliable contract. Every attendee must work
in an independently owned repository, use GitHub Projects as the human view,
and understand how the local dashboard differs from that board. The material
must remain usable without a facilitator while still supporting a genuinely
live instructor-led session whose agent processes are never terminated merely
to satisfy presentation timing.

## Solution

Reframe the workshop around one coherent progression: PRD, four expert planning
artifacts, human revision, approved Vertical Slices, GitHub tickets, QA-owned
Acceptance Tests, isolated implementation, verification, evidence export, and
a Factory Canvas for the attendee's own use case. Remove the lights-off control
experiment completely.

Add real Lean, Standard, and Assured Factory Profiles; explicit Agent Role
contracts and versioned project policy; structured Handoff Receipts controlled
by the orchestrator; guided Product Review revision; a deliberately visible
rehearsal retry; and a sanitized Evidence Packet. Teach four macro phases before
showing the detailed ticket states. Update the instructor-led and self-paced
website paths, prerequisites, facilitator material, and release process to use
the same vocabulary and observable completion rubric.

Separate the bundled Pocket Cinema Rehearsal pack from generic repository
behavior. A committed Project Contract defines the target checkout's source and
test roots, tools, setup, gates, default branch, protected paths, and reset
adapter. Live planning accepts any PRD and records that contract with the plan.

## User Stories

1. As an attendee, I want a concise definition of a Software Factory, so that I understand that the workshop is about supervised engineering rather than autonomous code generation.
2. As an attendee, I want to understand why agent capability makes orchestration important now, so that the workshop feels timely without relying on hype.
3. As an attendee, I want the advantages and costs of a Software Factory stated together, so that I can judge whether its controls fit my work.
4. As an attendee, I want a visible 100-minute learning path, so that I know where I am and what outcome each section should produce.
5. As an attendee, I want to choose an instructor-led Live Run or a Self-paced Rehearsal Run, so that I can complete the material with or without external services.
6. As an attendee, I want complete pre-work requirements before the session, so that repository creation, authentication, and tool installation do not consume workshop time.
7. As an attendee, I want to create and own a repository from the public workshop template, so that my GitHub issues, Project, branches, and pull requests remain isolated from other attendees.
8. As an attendee, I want a full diagnostic to tell me whether my Live Run is ready, so that I can switch to Rehearsal Run before a setup problem blocks the class.
9. As an attendee, I want Claude to be a clear golden path while Codex and custom Agent Adapters remain supported, so that vendor choice does not obscure the factory model.
10. As an attendee, I want to work with a peer reviewer who owns a separate repository, so that both of us practice human judgment without sharing repository state.
11. As an attendee, I want to inspect Pocket Cinema before reading the PRD, so that I recognize TableStory as a domain conversion rather than a cosmetic rebrand.
12. As an attendee, I want to identify user outcomes, constraints, and evidence in the TableStory PRD, so that planning begins from a shared product contract.
13. As an attendee, I want each planning artifact introduced through one concrete question, so that I can understand its purpose without studying its entire schema.
14. As an attendee, I want to trace requirement R3 through Product Review, System Architecture, Program Design, and Vertical Slices, so that traceability becomes tangible.
15. As an attendee, I want the initial rehearsal Product Review to contain a discoverable evidence weakness, so that approval requires judgment rather than confirmation.
16. As an attendee, I want to reject a Product Review with written feedback, so that the factory records why it must change.
17. As an attendee, I want revision to rerun only the affected planning stage, so that human feedback does not discard unrelated valid work.
18. As an attendee, I want dependent approvals and artifacts to become stale after an upstream revision, so that the factory cannot silently publish inconsistent tickets.
19. As an attendee, I want to see approved Vertical Slices become GitHub Issues and Project items, so that tickets visibly originate from the PRD rather than seeding.
20. As an attendee, I want dependencies represented on the Project and dashboard, so that waiting and safe execution order are explainable.
21. As an attendee, I want the mobile recipe journey to remain the narrative Ticket, so that one user-visible outcome can be followed throughout the workshop.
22. As an attendee, I want an independent QA Agent Role to create Acceptance Tests before implementation, so that completion evidence is not authored only by the code-producing role.
23. As a peer reviewer, I want to inspect and approve an Acceptance Test, so that I practice deciding whether it proves behavior rather than merely whether it runs.
24. As an attendee, I want implementation roles prevented from changing QA-owned protected Acceptance Tests, so that failed requirements cannot be hidden by weakening evidence.
25. As an attendee, I want implementation to run in isolated Git worktrees, so that concurrent or failed work does not contaminate the main checkout.
26. As an attendee, I want the narrative Ticket to fail its first deterministic attempt and pass after a logged retry, so that the verification loop is observable even when a Live Run happens to be perfect.
27. As an attendee, I want each factory phase to emit a Handoff Receipt, so that I can see what the role received, claimed, verified, produced, and left unresolved.
28. As an attendee, I want GitHub Projects to be the human work-management view, so that ticket status remains understandable in a familiar collaboration tool.
29. As an attendee, I want the Factory Dashboard to be the engine-room view, so that prompts, attempts, policy, receipts, gates, and logs do not overload the Project board.
30. As an attendee, I want Plan, Build, Verify, and Review introduced before the detailed lifecycle states, so that I have a stable mental model for the board.
31. As an attendee, I want a Lean Factory Profile, so that low-risk work can avoid controls whose cost is not justified.
32. As an attendee, I want a Standard Factory Profile, so that the workshop can demonstrate planning, independent QA, protected evidence, verification, review rework, a Supervisor recommendation, and human exact-revision merge as one coherent path.
33. As an attendee, I want an Assured Factory Profile, so that I can see how cleanup, architecture conformance, hardening, and final verification extend the same model for higher-risk work.
34. As an operator, I want every Agent Role to declare what it owns, must not change, verifies, and hands off, so that swapping Agent Adapters does not change responsibility boundaries.
35. As an operator, I want engineering, workflow, and repository policy included in applicable role inputs, so that agents follow project constraints rather than generic preferences.
36. As an operator, I want the policy version recorded with each run, so that later reviewers know which rules governed a change.
37. As an attendee, I want one short configuration command to select the Standard workshop path, so that the live exercise does not depend on long option lists.
38. As an attendee, I want a sanitized Evidence Packet, so that I can retain planning, ticket, QA, execution, and review evidence without copying secrets or raw logs.
39. As an attendee, I want the Factory Canvas included in the final Evidence Packet, so that the artifact records both what I observed and how I would apply it.
40. As an attendee, I want to peer-review a Factory Canvas containing use case, risk, roles, gates, environment, evidence, recovery, and first Vertical Slice, so that I leave with a concrete next step.
41. As a facilitator, I want a readiness checklist and synchronized presenter cues, so that I can protect the learning sequence without narrating every command from memory.
42. As a facilitator, I want all demonstrations to be genuinely live, so that the room sees real agent and GitHub behavior rather than a pre-completed Project.
43. As a facilitator, I want a live evidence fallback using a consenting attendee repository, so that a slow facilitator agent does not have to be terminated.
44. As a facilitator, I want the material to state that the schedule is a target when all live results are incomplete, so that I do not misrepresent nondeterministic execution as guaranteed.
45. As a self-paced attendee, I want deterministic planning, QA, implementation, retry, verification, and code-review behavior, so that I can complete the same conceptual checkpoints without credentials.
46. As a prospective adopter, I want explicit production boundaries, so that I do not confuse a workshop starter kit with a secured production orchestration platform.
47. As a prospective adopter, I want custom Agent Adapter instructions separated from the golden path, so that I can extend the factory after learning the core model.
48. As a workshop owner, I want the source, website, CLI, and release to show one version identity, so that attendee instructions can be reproduced against the intended revision.
49. As a workshop owner, I want the repository audited before it becomes public and a template, so that no local credentials, generated state, or obsolete control material are published.
50. As a workshop owner, I want the website and all documentation to use the project glossary, so that terms such as Agent Role, Agent Adapter, Live Run, Rehearsal Run, GitHub Project, and Factory Dashboard are not conflated.
51. As an operator, I want an Agent Supervisor to coordinate dependency-ready Ticket agents from their Handoff Receipts, so that parallel work receives one coherent dispatch decision.
52. As an operator, I want supervisor commands validated by the orchestrator, so that a coordinating agent cannot change scope, dependencies, gates, approvals, or lifecycle state.
53. As an attendee, I want to inspect supervisor inputs, Ticket instructions, blocks, logs, and decision history, so that multi-agent synchronization is understandable rather than hidden.
54. As an operator, I want a separate read-only Code Review Agent to inspect the exact candidate PR diff and return `APPROVE` or `REQUEST_CHANGES`, so that technical approval remains independent of implementation.
55. As an operator, I want every code-review comment to return through the bounded implementation retry loop on the same branch and PR, so that the repaired revision reruns gates and review before it can merge.
56. As an operator, I want the Agent Supervisor to recommend merge only for the exact approved PR head with passing gates and a published review decision, so that a human can make the final merge decision from validated evidence.
57. As an attendee, I want the workshop to distinguish a formal GitHub review from the single-account Factory-comment fallback, so that I do not mistake audit evidence for a branch-protection approval.
58. As a Live Run attendee, I want to paste the URL of a GitHub repository I control, so that the factory targets it explicitly instead of depending on an unrelated GitHub CLI default.
59. As a Live Run attendee, I want reset to clear only local factory state without rewriting source or GitHub, so that I can recover the control panel without mistaking local cleanup for remote deletion.
60. As an operator, I want to initialize a reviewable Project Contract for any Git repository, so that planning, QA, verification, and reset do not inherit Pocket Cinema assumptions.
61. As an operator, I want setup detection separated from setup execution, so that no generated repository command runs before a human reviews and explicitly approves it.
62. As an operator, I want a Live local-state reset to preserve source files, the selected mode, and all GitHub artifacts, so that recovery cannot invoke a project-specific destructive adapter accidentally.

## Implementation Decisions

- The lights-off control is removed in full: launcher, tests, scenario prompts,
  reports, documentation sections, website steps, comparison language,
  troubleshooting, and facilitator setup. No replacement benchmark is added.
- The 100-minute core follows the accepted schedule: readiness and pairing;
  factory concept and starting app; PRD; Product Review revision; architecture,
  program, and slice trace; alignment publication; Acceptance Test review;
  Factory Run; app verification; Canvas review; final Evidence Packet export.
- The website has separate instructor-led and self-paced paths. Both use the
  same concepts and checkpoints; the self-paced path defaults to deterministic
  behavior and contains complete recovery instructions. Existing local progress
  persistence remains.
- Every attendee creates a repository from the public GitHub template. The
  factory creates the GitHub Project during approved publication. The
  facilitator uses a different repository, and peers review one another's work.
- Live configuration validates and saves the attendee-provided GitHub repository
  URL, aligns `origin`, and uses that explicit identity for issues, branches,
  Projects, pull requests, and preflight checks.
- A reset started from Live mode is explicitly local-only, keeps the Control
  Center in Live mode, preserves tracked source, and preserves all remote GitHub artifacts. A genuinely
  fresh Live Run still uses a fresh repository.
- The release is frozen on the default branch and tagged `workshop-v1.1.0`
  before repository creation opens. The CLI and website expose that identity.
  Only workshop-blocking fixes justify a replacement release.
- Live agents have no presentation timeout. The facilitator first shows their
  own live repository, then a consenting attendee's live repository if it has
  reached the needed stage. If neither is ready, teaching continues from the
  observable current state and missing evidence becomes post-session work.
- The Product Review revision interface accepts a plan identifier, a product
  stage, and human feedback supplied inline or from a file. It stores feedback
  and revision history, regenerates Product Review through the original
  Planning Agent Role, invalidates product and alignment approvals, deletes or
  marks downstream artifacts stale, and returns the run to product review.
- Rehearsal Run starts with a deliberately vague claim that TV back-navigation
  “works” without objective keyboard and mode-preservation evidence. Applying
  the documented feedback produces the deterministic corrected Product Review.
- Factory Profiles are executable configuration, not documentation aliases.
  Lean uses product intent, Vertical Slices, one implementation role, existing
  tests, and human PR review. Standard uses all four planning roles,
  QA-authored protected Acceptance Tests, implementation, required gates,
  read-only code-review rework, a Supervisor recommendation, and human
  exact-revision merge. Assured adds cleanup, architecture
  conformance, hardening, and a read-only final verifier after implementation.
- Assured modifying roles cannot edit protected Acceptance Tests. Architecture
  conformance and final verification are read-only and may block progression.
  A failed post-implementation review returns work to the relevant modifying
  role within the orchestrator's bounded retry policy.
- Agent Role contracts have four required sections: ownership, exclusions,
  verification responsibility, and Handoff Receipt output. Agent Adapters fill
  roles but cannot redefine these contracts.
- Versioned policy is divided into engineering rules, workflow rules, and
  repository constraints. Applicable policy content and hashes are injected
  into role inputs and retained in run evidence.
- Handoff Receipts use one versioned schema across planning and execution. A
  receipt records run, role, phase, optional Ticket, attempt, input revisions,
  output revisions, claimed result, verification, unresolved risks, artifact
  references, policy hashes, and timestamp. The central orchestrator is the
  only lifecycle authority.
- After required gates pass, the factory opens or updates the PR. The Code Review
  Agent receives its exact candidate base and head revisions, Ticket contract,
  changed paths, and gate summary. Its output has a versioned `APPROVE` or
  `REQUEST_CHANGES` schema. Comments are bounded, restricted to changed paths,
  and classified as blocking, warning, or note. The orchestrator rejects malformed
  output and any worktree mutation. `REQUEST_CHANGES` returns every comment to
  implementation within the existing retry budget; gates and review rerun on
  the new commit. `APPROVE` requires an empty comments list.
- The Supervisor has a separate post-review `MERGE` or `BLOCK` contract. The
  orchestrator accepts `MERGE` only when the Code Review Agent approved the same
  candidate head, required gates pass, and the decision was published. It
  rechecks the live GitHub PR head and executes the merge; stale heads and branch
  protection failures block the Ticket. With a single GitHub identity, formal
  self-approval falls back to an explicit Factory comment that does not satisfy
  branch-protection approval requirements.
- Standard and Assured profiles run an Agent Supervisor at each ready-ticket
  dispatch checkpoint; Lean retains direct scheduler dispatch. The Supervisor
  reads current dependency state and recent worker Handoff Receipts, then
  proposes Ticket-specific dispatch instructions or evidence-backed blocks.
  The orchestrator validates readiness, uniqueness, concurrency, output schema,
  and non-stalling behavior before applying any command. Supervisor execution
  uses a disposable read-only-to-the-run worktree, and every prompt, log,
  decision, and supervisor Handoff Receipt is retained for inspection.
- The detailed Project lifecycle remains Backlog, Ready, In Progress, QA Review,
  Verifying, In Review, Done, and Blocked. The website and dashboard group the
  ordinary flow as Plan, Build, Verify, and Review; Blocked is an exception that
  retains the phase in which it occurred.
- The Evidence Packet interface accepts a Planning Run identifier and an
  optional Ticket selection. It produces sanitized Markdown plus a small
  machine-readable manifest, includes the four planning artifacts, approval
  history, dependency map, selected Acceptance Test metadata, Handoff Receipts,
  gate results, GitHub links, and the completed Factory Canvas, and reports
  missing evidence without fabricating it. Raw prompts, raw logs, environment
  values, tokens, and credential material are excluded by default.
- The Factory Canvas is a versioned Markdown template completed in the attendee
  repository. It records use case, chosen Factory Profile, Agent Roles, Human
  Gates, execution environment, required evidence, recovery policy, and first
  Vertical Slice. Final Evidence Packet export requires the completed Canvas.
- Live attendee configuration defaults to one implementation Ticket at a time.
  The facilitator may demonstrate greater parallelism, and optional material
  explains capacity, cost, provider, and risk considerations.
- Production-boundary material covers untrusted-code sandboxing, credentials,
  spend and concurrency, audit retention, idempotent recovery, branch
  protection, supply-chain controls, observability, and organization policy.
- The repository glossary is authoritative for participant-facing language.
  Existing CLI flags may retain compatibility terminology, but documentation
  uses Live Run and Rehearsal Run rather than production and mock mode.

## Testing Decisions

- Tests assert external workflow behavior and durable artifacts rather than
  private helper calls. The primary seams are the factory CLI, a deterministic
  end-to-end Rehearsal Run, and server-rendered workshop HTML.
- Planning CLI tests cover revision feedback, deterministic corrected output,
  revision history, upstream hash changes, invalidated approvals, stale
  downstream artifacts, and refusal to publish until reapproval.
- Profile tests exercise the complete observable role and gate sequence for
  Lean, Standard, and Assured, including protected Acceptance Test enforcement
  and blocking read-only Assured reviews.
- Policy tests prove that applicable policy and its hashes reach each role input
  and that Handoff Receipts retain the same hashes.
- Handoff Receipt contract tests validate required fields, planning receipts,
  execution receipts, retries, blocking risks, revision references, and
  dashboard-readable serialization.
- Runtime tests extend the existing temporary Git repository and worktree
  patterns to cover the narrative Ticket's deterministic first failure,
  bounded retry, protected Acceptance Tests, successful gates, merge, and
  dependency unlock.
- Supervisor tests cover receipt input, bounded dispatch, explicit blocks,
  invalid or conflicting commands, silent-stall rejection, durable decision
  history, deterministic rehearsal behavior, and Control Center rendering.
- Evidence Packet tests use synthetic planning and execution state containing
  secret-like values. They assert complete traceability, stable links, explicit
  missing-evidence warnings, Canvas inclusion, and exclusion of prompts, logs,
  environment values, and credentials.
- Configuration tests cover profile selection, one-ticket live concurrency,
  custom Agent Adapter compatibility, ignored attendee defaults, and explicit
  command-line overrides.
- Website tests build and server-render the guide, verify both paths, new
  prerequisites, revised schedule, profile definitions, role boundaries,
  production limitations, Canvas and completion rubric, and assert that no
  control-experiment language remains.
- Accessibility verification covers semantic headings, keyboard operation,
  visible focus, path and progress controls, code-copy controls, responsive
  layout, and readable status communication without color alone.
- A repository-wide regression check rejects remaining references to the
  deleted control launcher, prompt, report, tests, or comparison sections.
- A clean-checkout rehearsal validates the complete Standard path from PRD
  through revised planning, deterministic retry, final Canvas, and sanitized
  Evidence Packet without GitHub or model credentials.
- A disposable live GitHub smoke test validates repository preflight, Project
  creation, ticket publication, QA approval, one implementation Ticket, PR
  creation, Handoff Receipts, and Evidence Packet links using the Claude golden
  path.
- Before public/template release, run the full Python and website suites, the
  clean rehearsal, secret and generated-state audit, link check, and deployed
  website verification against the frozen release identity.

## Out of Scope

- Proving that a Software Factory always produces better code, lowers cost, or
  delivers faster than a direct coding agent.
- Retaining any live or simulated lights-off control experiment.
- Running the core workshop against arbitrary attendee codebases.
- Teaching introductory Git, GitHub, terminal, Python, or Node.js skills.
- Making the reference factory a production-grade multi-tenant orchestration
  service.
- Adding peer-to-peer agent messaging, terminal multiplexing, or a distributed
  agent inbox protocol.
- Automatically committing or publishing raw prompts, logs, credentials, or
  Evidence Packets.
- Automatically making the source repository public, enabling GitHub template
  mode, or changing external organization policy; those remain owner actions.
- Guaranteeing completion of live model work within the 100-minute schedule.
- Giving cleanup, architecture review, hardening, or final verification equal
  hands-on time in the Standard core; those belong to Assured optional material.

## Further Notes

- The specification follows the repository glossary and the accepted ADRs for
  risk-calibrated Factory Profiles and centralized lifecycle handoffs.
- The current repository is private and not yet a GitHub template. The owner
  intends to make it public and enable template mode the day before delivery.
- The repository's existing ready-to-dispatch label is `agent-ready`; it is the
  local equivalent of the flow's `ready-for-agent` vocabulary.
- The 100-minute schedule is a teaching target. Live-only execution, no forced
  agent timeout, and no prepared recovery Project intentionally trade schedule
  certainty for authenticity.
