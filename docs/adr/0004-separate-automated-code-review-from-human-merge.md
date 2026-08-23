# ADR 0004: Separate automated code review from human merge

Status: Superseded by ADR 0005

## Context

Implementation, QA, verification, and supervision have different authority.
Using the implementation agent to review its own output weakens independence;
using the Agent Supervisor as a reviewer mixes coordination with technical
judgment. Neither should silently approve a pull request.

## Decision

Standard and Assured profiles run a distinct, read-only Code Review Agent after
required verification and before pull-request publication. It inspects the
exact candidate base-to-head diff and returns a validated JSON PASS or BLOCK
verdict. Findings are limited to changed paths and include severity, optional
line, and message.

A BLOCK becomes retry context for implementation and consumes the existing
bounded retry budget. A PASS is stored under `.factory/reviews/`; in a Live Run
the factory opens the pull request and posts the validated review as a comment.
The orchestrator remains the lifecycle authority. A human remains the only
actor that can approve or merge.

Lean omits automated review and retains direct human diff review. Rehearsal uses
a deterministic mock reviewer but exercises the same contract and evidence
path without credentials.

## Consequences

- Code review has one inspectable Interface and can use a different Agent
  Adapter from implementation.
- Malformed output, findings on unchanged paths, contradictory verdicts, and
  worktree modification fail closed.
- A failed GitHub comment does not discard an otherwise valid local review or
  pull request; the Control Center records a warning.
- Automated review increases cost and latency in Standard and Assured runs, but
  does not weaken the human merge gate.
