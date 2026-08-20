# Software (re)-Factory workshop guide

Release: `workshop-v1.0.0`

The attendee-facing, self-guided website for the Software (re)-Factory
workshop. It follows one PRD from intent to verified delivery using a repeated
**Goal → Do → Check** pattern. The main path contains only the decisions,
commands, and evidence attendees need; optional agent configuration and
recovery guidance stay collapsed until needed.

The guide supports deterministic rehearsal and live GitHub paths. Claude is
the worked example, but attendees can use Codex, Cursor, or a custom CLI.

## Local development

Requires Node.js 22.13 or later.

```sh
npm install
npm run dev
```

Open `http://localhost:3000`.

## Local copy editor

Use the local editor when you want to review the guide and change a word,
phrase, heading, or paragraph without editing TSX by hand:

```sh
npm run edit
```

The command opens `http://127.0.0.1:3001/__workshop_editor` and starts the
workshop preview if it is not already running. Click visible text in the
preview, type in the editor, and choose **Save to project**. The draft appears
in the preview while you type; saving writes the change to `app/page.tsx` so it
can be reviewed with Git and included in the next commit. **Undo last save** is
available for changes made during the current editor session.

The editor listens only on the local loopback address. It is not included in
the deployed workshop website and does not need an account, database, or API
key. Use the normal code workflow for layout, links, commands, conditional
logic, and component changes.

## Illustration assets

The concept illustrations in `public/illustrations/` were generated for this
workshop using the visual language and QA guidance from
[Ian Xiaohei Illustrations](https://github.com/helloianneo/ian-xiaohei-illustrations)
by Ian. The source skill is MIT-licensed; the workshop preserves visible
attribution as requested by its notice. The installed skill was audited and
pinned from upstream commit `91b560849e8f883922cc2fa8a358a668caa94105`.

## Verification

```sh
npm run lint
npm test
```

Workshop progress and the selected path are stored in the attendee's browser.
The site does not require a database, account, or application secrets.
