# TableStory

TableStory is a responsive recipe discovery app for mobile screens and television remotes.

## Run locally

From the repository root:

```sh
.factory/venv/bin/python demo-app/app.py
```

Open the mobile experience at <http://localhost:5000/> or TV mode at
<http://localhost:5000/?mode=tv>. In TV mode, use the arrow keys to move,
Enter to open a recipe, and Escape or Backspace to return.

## Verify

```sh
.factory/venv/bin/python -m pytest -q demo-app/tests
node --test demo-app/static/tests/*.test.js
```

Recipe data and generated artwork are bundled locally, so the app needs no API
key or network connection.
