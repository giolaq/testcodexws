# Facilitator runbook

## Before the room opens

1. Run `./setup_demo.sh` from the repository root.
2. Start `python3 -m http.server 8000` and open
   `http://localhost:8000/factory/dashboard.html` on the presentation display.
3. In a second terminal, run `./factory/factory run --mock --dry-run` to confirm
   the dependency waves, then reset once more.
4. For a live-agent session, run one smoke prompt through every CLI you plan to
   offer and confirm `gh auth status` includes the `project` scope.

## Suggested story beats

- Begin with an attendee PRD: run `factory plan`, review the generated Markdown,
  edit the companion JSON, and emphasize that GitHub remains unchanged until the
  attendee types `APPROVE` in `factory approve`.
- Pause on the dry-run waves: #1, #3, #7, and the vague #8 can begin together.
- Start the mock run. Point out isolation while several cards are In Progress.
- Let #8 exhaust its retries. Ask the room what acceptance criteria are missing.
- Show #7's merge-conflict rehearsal event in `state.json`: serialized publishing
  keeps the happy path deterministic while making the risk concrete.
- Rewrite #8, run `factory retry 8`, and use a real agent for the workshop-2 extension.
- Finish by running Pocket Cinema with `?mode=tv` and driving it using arrows,
  Enter, and Escape as a remote control.

## Recovery

`./setup_demo.sh` removes rehearsal worktrees and factory branches, restores only
`demo-app/` from the baseline tag, clears factory runtime state, and leaves source
changes outside the workpiece alone. A Blocked worktree is deliberately preserved
until reset so it can be inspected with attendees.
