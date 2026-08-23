# ADR 0006: Drive repository behavior from a Project Contract

Status: accepted

## Context

The original workshop implementation encoded Pocket Cinema paths, Python and
Node commands, and a baseline reset directly in the factory. That made the
deterministic exercise reliable, but it also made an arbitrary PRD appear more
portable than its execution environment actually was. Planning could describe a
different product while QA and verification still assumed `demo-app/`.

The factory needs to target an existing Git repository without teaching every
planning or execution role how to detect every language and layout.

## Decision

Each target repository owns one committed `factory.project.toml`. The
`ProjectContract` module is the narrow interface for:

- project identity, default branch, source roots, and protected paths;
- required tools, reviewed setup commands, and ports;
- QA roots and ticket-numbered test filename patterns;
- ordered required or advisory verification gates; and
- an optional argument-vector reset adapter.

`factory init --repo PATH` detects conservative defaults for common Python,
Node.js, Go, and Rust repositories. It writes configuration but never runs setup.
`factory prepare --repo PATH` displays the committed setup commands and requires
explicit approval before executing them. Unknown stacks receive `git diff
--check` as a reviewable integrity gate.

Planning, QA, implementation, code review, doctor, gates, Control Center, and
reset consume the same contract. Planning records a hash of the contract and
bounded file inventory; a changed value invalidates approval before ticket
publication.

The bundled Pocket Cinema reset and deterministic agents remain a Rehearsal
pack. Live mode is the generic path for arbitrary PRDs and repositories. A Live
local-state reset bypasses the repository reset adapter and never rewrites
tracked source or remote GitHub artifacts.

## Consequences

- Repository assumptions are visible and reviewable before agents run.
- The factory core can support an unfamiliar stack without adding stack checks
  throughout the orchestrator.
- Setup remains an explicit trust boundary; generated commands are not run by
  detection.
- A repository layout or gate change requires planning to run again.
- Automatic detection is a starting point, not authority. A human must review
  the contract.
- Credential-free Rehearsal remains intentionally domain-specific; it cannot
  implement arbitrary PRDs deterministically.
