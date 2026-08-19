# Software (re)-Factory workshop design

This document preserves the decisions reached during the workshop design
interview. It is the source for the implementation specification; it is not the
attendee-facing workshop outline.

## Promise and audience

- The primary promise is: attendees can design and control an AI software
  factory for their own codebase.
- The included factory is a reference implementation and starter kit, not a
  production platform or a product being sold.
- The hands-on path is optimized for experienced developers and technical leads
  who already understand Git, pull requests, tests, and command-line tools.
- Managers may follow the conceptual path, but beginner Git instruction does
  not consume the core workshop.
- The core lasts 100 minutes. Custom adapters, Assured operation, dependency
  recovery, and production hardening are optional modules.

## Evidence of learning

An attendee completes the workshop by showing:

1. a Product Review they deliberately revised;
2. PRD-derived tickets in a GitHub Project;
3. one QA-owned acceptance test they reviewed;
4. one ticket trace, using their run or the facilitator's live trace;
5. a sanitized evidence packet; and
6. a peer-reviewed Factory Canvas for their own use case.

The workshop claims that a factory makes decisions, ownership, dependencies,
evidence, and failures easier to inspect and control. It does not claim that a
single exercise proves better code, faster delivery, or lower cost.

## Participant topology

- Every attendee creates and owns a disposable repository before the session.
- Attendees work in pairs and review each other's product decisions, acceptance
  tests, evidence, and Factory Canvas; they do not share repository ownership.
- The facilitator uses a separate repository on screen.
- The factory creates and configures a GitHub Project only after alignment is
  approved, so attendees see approved slices become tickets.
- GitHub Projects is the human work-management view. The local dashboard is the
  engine-room view for prompts, attempts, gates, dependencies, receipts, and
  logs.
- The workshop repository remains private during preparation. The owner will
  make it public and enable GitHub template mode the day before the workshop.

## Delivery modes and agent choice

- The website offers two explicit paths: Instructor-led workshop and Self-paced
  rehearsal.
- The instructor-led path uses GitHub and live agents. The self-paced path uses
  deterministic artifacts and explains every checkpoint and recovery action.
- Agent work is never terminated because a presentation time box expired. An
  attendee whose run is still working follows the current checkpoint using the
  facilitator's repository and returns to their result when it completes.
- Claude is the golden-path example. Codex and custom adapters are documented
  substitutions behind the same role contracts.
- Live attendee repositories default to one implementation ticket at a time.
  Parallel execution is demonstrated separately and described as an operational
  policy, not the definition of a multi-agent factory.
- The lights-off control experiment is removed completely from code,
  documentation, fixtures, the website, and facilitator setup.

## Learning sequence

- Attendees use the prepared Pocket Cinema application and TableStory PRD for
  the core. They apply the model to their own use case in the final Canvas
  exercise rather than running the factory on an arbitrary repository.
- The four planning artifacts are taught through one question each. Requirement
  `R3`, the mobile recipe journey, is traced through all four artifacts.
- Product Review and Vertical Slices receive hands-on decisions. System
  Architecture and Program Design receive focused contract inspections.
- A Rehearsal Run includes one deliberately weak Product Review. Attendees reject
  it with written feedback, regenerate only the affected stage, and observe
  dependent approvals becoming stale.
- The mobile recipe journey is the narrative ticket. Its prerequisite tickets
  show dependency waiting and unlocks while unrelated work demonstrates the
  background factory.
- QA owns Acceptance Tests before implementation. Implementation adapters cannot
  modify protected Acceptance Tests.
- The narrative ticket fails one acceptance test on its first deterministic
  attempt, then succeeds after a visible, logged retry. Live runs are not
  artificially failed.
- The workshop teaches the macro phases Plan, Build, Verify, and Review before
  revealing all detailed Project and dashboard states.

## Factory controls

The factory offers three real profiles:

- **Lean**: product intent, small slices, one implementation role, existing
  tests, and human pull-request review.
- **Standard**: four planning roles, independent QA-owned acceptance tests,
  protected tests, implementation roles, verification gates, and human merge.
- **Assured**: Standard plus cleanup, architecture conformance, hardening, and
  final independent verification roles.

The core workshop runs Standard. Lean and Assured are used in the Factory Canvas
and optional modules.

Every role contract states what the role owns, what it does not own, its
verification responsibility, and its handoff output. Versioned engineering,
workflow, and repository policy is included in every applicable role input, and
the factory records the policy version with the run.

Every phase emits a structured handoff receipt containing the role, ticket,
input and output revisions, claimed result, verification performed, unresolved
risks, and artifact paths. The central orchestrator owns lifecycle state and
handoffs; agents do not coordinate through peer-to-peer queues.

## Attendee preparation

Pre-work is mandatory for the live path:

1. create a repository from the workshop template;
2. clone it locally;
3. authenticate GitHub and the selected agent;
4. select the agent preset; and
5. obtain a green full factory diagnostic.

The first five workshop minutes confirm readiness and form reviewer pairs. An
attendee without a green live diagnostic uses the self-paced rehearsal path.

The production-boundary material explicitly covers sandboxing, credential
isolation, spend and concurrency limits, audit retention, idempotent recovery,
branch protection, supply-chain controls, and organization-specific policy.

## Core schedule

| Time | Activity |
| --- | --- |
| 0–5 | Confirm readiness and pair attendees |
| 5–13 | Define an AI software factory and inspect Pocket Cinema |
| 13–20 | Read the PRD and identify success evidence |
| 20–35 | Review, reject, and revise Product Review |
| 35–50 | Trace `R3` through architecture, program design, and slices |
| 50–58 | Approve alignment and watch tickets appear in GitHub Projects |
| 58–68 | Inspect and approve independent acceptance tests |
| 68–85 | Run the factory and trace the mobile journey ticket |
| 85–91 | Verify TableStory and preview the evidence packet |
| 91–98 | Complete and peer-review the Factory Canvas |
| 98–100 | Export the final evidence packet and close |

The final question is: "Which controls does this use case need, and which would
only add ceremony?" The application is evidence, not the conclusion.

## Planned interfaces

- A plan-revision command accepts human feedback, reruns only the selected
  planning stage, records that feedback, and invalidates dependent approvals.
- An evidence command generates a sanitized local Markdown packet containing
  selected artifacts and GitHub links. Raw logs and secrets are excluded by
  default, and committing the packet is an explicit attendee decision.
- Named Lean, Standard, and Assured configurations select their role and gate
  topology without requiring long command lines.
- The dashboard presents macro phases first and links detailed state to role
  contracts, policy versions, and handoff receipts.

## Release and live-delivery defaults

- The public workshop is frozen on `main` and tagged `workshop-v1.0.0` before
  attendees create repositories. The website and CLI show the release identity.
  A replacement release is published only for a workshop-blocking defect.
- The facilitator demonstrates the factory live and does not terminate slow
  agents or maintain a prepared recovery Project. If the facilitator's run is
  incomplete, the room uses the first attendee's live repository that has
  reached the required stage, with permission. If none has, the facilitator
  teaches from the current state and the missing execution evidence is
  completed after the scheduled session.
