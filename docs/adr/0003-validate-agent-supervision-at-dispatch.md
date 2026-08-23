---
status: accepted
---

# Validate agent supervision at the dispatch seam

## Context

Ticket agents need a way to report results to one coordinating agent, and that
agent needs to synchronize the next safe wave. Direct agent-to-agent messaging
would duplicate lifecycle state, obscure recovery, and let an agent bypass
dependency, concurrency, test, gate, or human-approval controls.

## Decision

Standard and Assured Factory Profiles run an Agent Supervisor at the scheduler's
dispatch checkpoint. The orchestrator supplies dependency-ready Tickets,
current state, configured parallelism, and recent worker Handoff Receipts. The
Supervisor returns one versioned decision containing:

- Ticket-specific dispatch instructions;
- explicit blocks with reasons; and
- a summary of its coordination decision.

The orchestrator rejects malformed, unavailable, duplicated, conflicting,
over-capacity, or silently stalling commands. It alone applies lifecycle
transitions and records Handoff Receipts. The supervisor adapter runs in a
disposable detached worktree, and its prompt, log, input hash, commands, and
history remain inspectable in the local Control Center.

Lean retains direct scheduler dispatch because its lower-overhead topology does
not include the Supervisor role.

## Consequences

Worker agents communicate through one durable, replayable channel. Coordination
can use Claude, Codex, another registered CLI, or the deterministic Rehearsal
adapter without changing authority boundaries. A supervisor failure stops the
wave safely with ready work preserved, but it also adds one model invocation to
each Standard or Assured dispatch checkpoint.

## Rejected alternatives

- Peer-to-peer agent messages: difficult to recover and audit.
- Giving the Supervisor direct board or GitHub mutation: duplicates the
  orchestrator's authority and bypasses validation.
- Embedding coordination in each worker prompt only: no agent has the complete
  receipt and dependency view needed to synchronize the next wave.
