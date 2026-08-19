# Software (re)-Factory

This context defines the language used by the factory, its workshop, and the
attendee guide. It distinguishes the responsibilities people control from the
executables and services used to perform them.

## Factory model

**Software factory**:
A supervised system that turns approved product intent into traceable software
changes by coordinating specialized agent roles, isolated work, evidence, and
human decisions.
_Avoid_: Agent swarm, autonomous development

**Agent role**:
A bounded responsibility in the factory, defined by what it owns, what it must
not change, what it verifies, and what it hands off.
_Avoid_: Agent, when referring to a responsibility

**Agent adapter**:
A configured executable that fulfils an agent role in a particular model and
execution environment.
_Avoid_: Agent role, model

**Factory profile**:
A named bundle of controls selected according to the cost and risk of a change.
The profiles are Lean, Standard, and Assured.
_Avoid_: Mode, safety level

**Planning run**:
The reviewable transformation of a PRD into Product Review, System Architecture,
Program Design, and Vertical Slices before tickets are published.
_Avoid_: Ticket generation

**Factory run**:
The supervised execution of approved tickets through QA, implementation,
verification, review, and completion.
_Avoid_: Autonomous run

**Human gate**:
A decision point at which a person approves, rejects, or revises evidence before
the factory may continue.
_Avoid_: Confirmation step

**Vertical Slice**:
A dependency-aware unit of user or system value that carries its requirements,
contracts, acceptance criteria, and expected QA evidence into execution.
_Avoid_: Task, component ticket

**Ticket**:
An approved Vertical Slice represented as a GitHub Issue and Project item.
_Avoid_: Seed ticket, generated task

**Acceptance test**:
Executable evidence created and owned by the QA role before implementation to
prove a ticket's acceptance criteria.
_Avoid_: QA test, test suggestion

**Handoff receipt**:
A structured claim from one factory phase to the next that identifies its
inputs, outputs, verification, unresolved risks, and supporting artifacts.
_Avoid_: Agent message, note

## Workshop model

**Live run**:
A workshop run that uses GitHub and authenticated agent adapters to create real
issues, Project items, worktrees, commits, and pull requests.
_Avoid_: Production mode

**Rehearsal run**:
A deterministic local workshop run that preserves the factory lifecycle without
requiring GitHub writes or model credentials.
_Avoid_: Mock mode, fake run

**GitHub Project**:
The human work-management view of tickets and their lifecycle.
_Avoid_: Factory dashboard

**Factory dashboard**:
The engine-room view of prompts, attempts, dependencies, handoff receipts,
verification gates, and logs for a factory run.
_Avoid_: Project board

**Evidence packet**:
A sanitized, portable record of selected planning, ticket, QA, execution, and
review evidence from a workshop run.
_Avoid_: Log archive

**Factory Canvas**:
A one-page design for applying the factory model to another use case, including
its risk profile, roles, gates, environment, evidence, recovery, and first slice.
_Avoid_: Retrospective
