# Lights-off control experiment

This lab gives the workshop a control group. One coding agent receives the
complete TableStory PRD and works autonomously in one branch. It does not use
the factory's planning contracts, tickets, worktrees, independent QA phase, or
human approval gates.

The point is not to make the direct agent fail. Use the same model, PRD,
baseline, and verification commands as the factory run. Compare the amount of
evidence and review work each workflow produces.

## Experimental rules

Keep these variables fixed:

- The starting commit and `recipe-app-prd.md`.
- The coding model and CLI version.
- The functional verification commands.
- The time at which you begin evaluating the result.

Change only the delivery workflow:

| Lights-off control | Software factory |
| --- | --- |
| One complete-PRD prompt | Four planning expert contracts |
| One branch and working tree | One worktree per vertical slice |
| Agent makes assumptions privately | Blocking questions and two human gates |
| Agent writes implementation and tests | Independent QA writes protected tests first |
| One large final review | Ticket-sized review and traceability |

Do not correct, clarify, or redirect the control agent while it runs. Record an
ambiguity as an observation instead. Do not give it planning artifacts produced
by the factory.

## Run the live control

Create it from the repository that contains the workshop scripts, using a
second terminal:

```sh
./factory/new_workshop.sh ../software-refactory-control recipe-rebrand
cd ../software-refactory-control
git switch -c experiment/lights-off
```

Run the same CLI/model that you will use for factory implementation. The
launcher selects the current authenticated Codex CLI in the same way as the
factory and can also start Claude Code or Cursor:

```sh
python3 factory/run_lights_off.py --agent codex
```

Or choose another supported adapter:

```sh
python3 factory/run_lights_off.py --agent claude
python3 factory/run_lights_off.py --agent cursor
```

Leave this second terminal running while the workshop returns to the factory
checkout. Do not treat speed alone as success: record elapsed time, but score
the result against the same PRD evidence.

## Credential-free rehearsal

The bundled report is a deterministic discussion fixture, not a benchmark or a
claim about any model:

```sh
sed -n '1,240p' factory/scenarios/recipe-rebrand/lights-off-sample-report.md
```

It represents a plausible partial one-shot result so attendees can practice the
comparison without model credentials. Replace it with an actual captured run
when the workshop environment supports a live agent.

## Evaluate both results

Run the control's available tests and inspect the complete diff:

```sh
.factory/venv/bin/python -m pytest -q demo-app/tests
node --test demo-app/static/tests/*.test.js
python3 -m compileall -q demo-app
git diff --stat
git status --short
```

Then exercise the same user journeys in both checkouts:

- Search for a recipe by ingredient on mobile.
- Open its details and save or remove it from My Cookbook.
- Complete TV browse, detail, action, and return using only keys.
- Search supported UI, APIs, metadata, tests, and documentation for obsolete
  cinema terminology.
- Trace every PRD requirement to an implementation and objective evidence.

Use the scorecard in the sample report. Discuss review effort as well as output
quality: in the control, a reviewer must reconstruct requirements, architecture,
assumptions, ownership, and test intent from a large diff. The factory exposes
those decisions before or during implementation.
