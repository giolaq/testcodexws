# Software (re)-Factory Workshop

Release: `workshop-v1.1.0`

This repository contains the reference factory orchestrator and the Pocket
Cinema refactoring workpiece. A four-expert planning pipeline turns each PRD
into Product Review, System Architecture, Program Design, and Vertical Slices
contracts before a human can publish tickets.

Pocket Cinema is the deterministic workshop pack. In Live mode, the same
factory can target a separate existing Git repository and any PRD after
`factory init --repo /path/to/project` creates its reviewable Project Contract.

- Start the self-guided experience with the [workshop website](workshop-guide/README.md).
- Use the [factory quickstart](factory/README.md) for the operator reference.
- Use the [configuration guide](factory/CONFIGURATION.md) to select Claude,
  Codex, Cursor, or register your own supervisor, implementation, QA, and code-review agent,
  model wrapper, and execution environment.
- Use the [Control Center guide](factory/CONTROL_CENTER.md) to inspect how worker
  Handoff Receipts become validated supervisor dispatch commands and how a
  separate Code Review Agent requests repairs or approves an exact candidate
  before the Supervisor recommends that exact revision for a human merge.
- Read the [planning pipeline guide](factory/PLANNING.md) for prompts, artifacts,
approvals, traceability, and stale-plan behavior.
- Compare the executable [Factory Profiles and role topology](factory/README.md#choose-a-factory-profile).
- Use the [facilitator runbook](factory/FACILITATOR.md) for the 100-minute
  schedule, live fallback, and release checklist.
