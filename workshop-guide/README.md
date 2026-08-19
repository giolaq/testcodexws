# Software (re)-Factory workshop guide

The attendee-facing, self-guided website for the Software (re)-Factory
workshop. It introduces the AI software factory operating model, explains why
it matters now, follows one PRD through two delivery systems, and helps
attendees design the right level of control for their own work. It also
includes complete mode-specific prerequisites, two workshop paths, nine guided
steps, progress tracking, copyable commands, checkpoints, troubleshooting, and
the complete factory command reference. Claude is the live worked example, but
the guide also explains how to use built-in adapters by role or register a
team's own implementation and QA agent, model wrapper, and execution
environment in `factory/factory.toml`.

## Local development

Requires Node.js 22.13 or later.

```sh
npm install
npm run dev
```

Open `http://localhost:3000`.

## Verification

```sh
npm run lint
npm test
```

Workshop progress and the selected path are stored in the attendee's browser.
The site does not require a database, account, or application secrets.
