# Software (re)-Factory workshop guide

The attendee-facing, self-guided website for the Software (re)-Factory
workshop. It includes complete mode-specific prerequisites, two workshop paths,
the four-expert planning and traceability workflow, a fair lights-off control
experiment, nine guided steps, progress tracking, copyable commands,
checkpoints, exercises, troubleshooting, and the complete factory command
reference.

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
