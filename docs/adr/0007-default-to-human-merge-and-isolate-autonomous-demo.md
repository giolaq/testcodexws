# ADR 0007: Default to human merge and isolate Autonomous Demo

Status: accepted

## Context

ADR 0005 closed the automated code-review, repair, and merge loop by allowing
the Agent Supervisor to recommend `MERGE` and the orchestrator to execute that
decision for Standard and Assured Factory Profiles. The implementation verifies
the exact reviewed pull-request head and fails closed on stale revisions or
branch-protection failures.

Those controls protect revision integrity, but they do not answer the ownership
question: who decides that the available evidence is sufficient to ship?
Standard is the workshop's normal path and Assured represents higher-consequence
work. Automatic merge in both profiles makes delegated accountability look like
the default rather than a deliberate autonomy choice.

## Decision

Lean, Standard, and Assured end at a human exact-revision merge gate.

The Code Review Agent may still return `APPROVE` or `REQUEST_CHANGES` for an
exact candidate. The implementation-repair loop remains automated and all
required gates rerun after a changed head. After approval, the Agent Supervisor
produces a revision-bound merge recommendation and evidence summary, but it
does not cause the orchestrator to merge. A person performs the final merge;
the orchestrator observes the merged revision before completing the Ticket.

A fourth Factory Profile, Autonomous Demo, preserves the ADR 0005 merge path.
It has the Standard planning and execution topology but permits a validated
Supervisor `MERGE` recommendation to be executed by the orchestrator. It is
workshop-only, never a preset default, and requires an explicit run opt-in that
states that final shipping accountability has been delegated.

The profile contract exposes `merge_authority` and
`requires_explicit_opt_in`. The human-owned Factory Charter may further restrict
merge authority, but it cannot make Standard or Assured automatically merge.
Repository branch protection remains the ultimate remote enforcement point.

This decision supersedes only the Standard and Assured merge-authority portion
of ADR 0005. ADR 0005 remains authoritative for exact-revision review,
structured rework, publication, stale-head checks, and the Autonomous Demo
merge implementation.

## Consequences

- The normal workshop path names a person as the final shipping owner.
- Code-review automation remains useful because it prepares a bounded,
  revision-specific decision instead of silently transferring accountability.
- Existing Standard and Assured runs that expected automatic merge require a
  state migration and stop at the human merge gate.
- Autonomous Demo remains available for teaching a complete automated loop,
  but its warning and opt-in become testable behavior.
- Live repositories may enforce a second human identity through branch
  protection; a single-account Factory comment is evidence, not formal GitHub
  approval.
