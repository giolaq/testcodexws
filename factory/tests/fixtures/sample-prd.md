# Shared workshop notes

Build a small command-line tool that lets workshop attendees add and list notes
stored in a local JSON file. Each note has an automatically assigned integer ID,
a title, and body text.

Requirements:

- `notes add --title TITLE --body BODY` appends a note and prints its ID.
- `notes list` prints notes ordered by ID.
- Missing or malformed storage is reported without a traceback.
- Use Python 3.11 standard library only.
- Unit tests must cover adding, listing, and malformed storage.

Out of scope: editing, deleting, synchronization, authentication, and a web UI.
