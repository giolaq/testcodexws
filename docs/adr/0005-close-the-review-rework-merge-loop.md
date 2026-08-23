# ADR 0005: Close the review, rework, and merge loop

Status: Accepted

## Context

ADR 0004 deliberately kept pull-request approval and merge as human actions.
The workshop now needs to demonstrate a complete supervised delivery loop:
independent code review can request changes, implementation can repair the same
pull request, and an approved revision can be merged without an extra manual
handoff. This adds authority, so revision identity and GitHub behavior must stay
explicit and auditable.

## Decision

Standard and Assured profiles open or update the pull request after required
gates pass. A distinct, read-only Code Review Agent reviews the exact
base-to-head candidate and returns schema-versioned `APPROVE` or
`REQUEST_CHANGES` JSON. Every comment requires `REQUEST_CHANGES`; `APPROVE`
requires an empty findings list. Findings are limited to changed paths.

`REQUEST_CHANGES` is published to the pull request and becomes the existing
bounded retry context. The same implementation role works on the same branch
and pull request. Protected Acceptance Tests, required gates, and code review
all run again. Approval applies only to the newly reviewed commit.

After approval, the Agent Supervisor receives the review, required gates,
Handoff Receipts, PR URL, and candidate head. It may return only `MERGE` or
`BLOCK` for that exact Ticket and revision. The Supervisor does not execute
GitHub commands. The orchestrator validates the command, confirms that the live
PR head still equals the approved head, and then executes the merge. It observes
the merged commit on the default branch before completing the Ticket.

The factory first attempts an official GitHub review. GitHub rejects approval
when the authenticated reviewer also authored the PR, so the workshop's
single-account setup falls back to an explicit Factory comment. That comment is
auditable but is not represented as a formal approval and does not bypass branch
protection. Repositories that require formal approval must use a distinct
reviewer identity.

Lean retains its direct human diff-and-merge path.

## Consequences

- Reviewer comments produce a visible development loop instead of ending at a
  passive report.
- Approval and merge commands are revision-specific; a changed PR head requires
  a new gate and review pass.
- Branch protection, publication failure, malformed agent output, missing gate
  evidence, and stale revisions fail closed.
- The Code Review Agent owns technical approval; the Supervisor owns a bounded
  merge recommendation; the orchestrator remains the only lifecycle and GitHub
  mutation authority.
