#!/usr/bin/env python3
"""Deterministic ticket implementer used for credential-free rehearsals."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()


def replace(path: str, old: str, new: str):
    file = ROOT / path
    text = file.read_text()
    if new in text:
        return
    if old not in text:
        raise RuntimeError(f"Could not find the expected edit point in {path}")
    file.write_text(text.replace(old, new, 1))


def append(path: str, marker: str, addition: str):
    file = ROOT / path
    text = file.read_text()
    if marker not in text:
        file.write_text(text.rstrip() + "\n\n" + addition.strip() + "\n")


def write(path: str, content: str):
    file = ROOT / path
    file.parent.mkdir(parents=True, exist_ok=True)
    if not file.exists() or file.read_text() != content:
        file.write_text(content)


def ticket_1():
    replace(
        "demo-app/app.py", "ROOT = Path(__file__).parent\n", """ROOT = Path(__file__).parent
TV_USER_AGENTS = ("smart-tv", "smarttv", "hbbtv", "appletv", "googletv")


def is_tv_mode() -> bool:
    user_agent = request.headers.get("User-Agent", "").lower()
    return request.args.get("mode") == "tv" or any(hint in user_agent for hint in TV_USER_AGENTS)
""",
    )
    replace(
        "demo-app/app.py",
        'return render_template("index.html", movies=catalog)',
        'return render_template("index.html", movies=catalog, tv_mode=is_tv_mode())',
    )
    replace("demo-app/templates/index.html", "<body>", "<body class=\"{{ 'tv' if tv_mode else 'mobile' }}\">")
    write("demo-app/tests/test_device_mode.py", '''def test_query_parameter_enables_tv_mode(client):
    assert b'class="tv"' in client.get("/?mode=tv").data
    assert b'class="mobile"' in client.get("/").data


def test_tv_user_agent_enables_tv_mode(client):
    response = client.get("/", headers={"User-Agent": "Example Smart-TV"})
    assert b'class="tv"' in response.data
''')


def ticket_2():
    append("demo-app/static/styles.css", "/* ticket-2-tv-theme */", '''/* ticket-2-tv-theme */
body.tv { --paper:#08090d; --card:#171922; font-size:22px; padding:4.5vh 5vw; }
body.tv .topbar { position:static; height:8vh; padding:0; background:transparent; }
body.tv main { max-width:none; padding:2vh 0 8vh; }
body.tv .hero { padding:3vh 0; }
body.tv .hero h1 { font-size:7.5vw; max-width:11ch; }
body.tv .search { max-width:38vw; height:64px; }
body.tv .movie-grid { grid-template-columns:repeat(6,minmax(0,1fr)); gap:2vw; }
body.tv .movie-card h3 { font-size:1.1vw; }
body.tv .movie-card p { font-size:.85vw; }
body.tv .tabbar { display:none; }
''')


def ticket_3():
    write("demo-app/static/focus.js", '''const ARROWS = new Set(['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown']);

export function nextFocus(index, columns, count, key) {
  if (!ARROWS.has(key) || count <= 0 || index < 0 || index >= count) return index;
  const row = Math.floor(index / columns);
  const column = index % columns;
  if (key === 'ArrowLeft') return column === 0 ? index : index - 1;
  if (key === 'ArrowRight') return column === columns - 1 || index + 1 >= count ? index : index + 1;
  if (key === 'ArrowUp') return row === 0 ? index : index - columns;
  return index + columns >= count ? index : index + columns;
}
''')
    write("demo-app/static/tests/focus.test.js", '''import test from 'node:test';
import assert from 'node:assert/strict';
import {nextFocus} from '../focus.js';

test('moves through a regular grid', () => {
  assert.equal(nextFocus(4, 3, 9, 'ArrowLeft'), 3);
  assert.equal(nextFocus(4, 3, 9, 'ArrowRight'), 5);
  assert.equal(nextFocus(4, 3, 9, 'ArrowUp'), 1);
  assert.equal(nextFocus(4, 3, 9, 'ArrowDown'), 7);
});

test('stays put at grid boundaries and short final rows', () => {
  assert.equal(nextFocus(0, 3, 8, 'ArrowLeft'), 0);
  assert.equal(nextFocus(2, 3, 8, 'ArrowRight'), 2);
  assert.equal(nextFocus(7, 3, 8, 'ArrowDown'), 7);
  assert.equal(nextFocus(7, 3, 8, 'ArrowRight'), 7);
});
''')


def ticket_4():
    write("demo-app/static/tv-nav.js", '''import {nextFocus} from './focus.js';

if (document.body.classList.contains('tv')) {
  const getTargets = () => [...document.querySelectorAll('.movie-card > a')].filter(target => target.offsetParent !== null);
  const initial = getTargets();
  initial.forEach((target, index) => target.tabIndex = index === 0 ? 0 : -1);
  initial[0]?.focus();
  document.addEventListener('keydown', event => {
    const targets = getTargets();
    const index = targets.indexOf(document.activeElement);
    if (index < 0) return;
    if (event.key === 'Enter') { document.activeElement.click(); return; }
    const next = nextFocus(index, 6, targets.length, event.key);
    if (next !== index) {
      event.preventDefault(); targets[index].tabIndex = -1; targets[next].tabIndex = 0; targets[next].focus();
    }
  });
}
''')
    write("demo-app/static/tv-nav.css", '''body.tv .movie-card>a:focus { outline:0; }
body.tv .movie-card>a:focus .poster { transform:scale(1.06); box-shadow:0 0 0 5px var(--lime),0 24px 55px #000b; }
body.tv .poster { transition:transform 150ms ease,box-shadow 150ms ease; }
''')
    replace(
        "demo-app/templates/index.html",
        "  <link rel=\"stylesheet\" href=\"{{ url_for('static', filename='styles.css') }}\">",
        "  <link rel=\"stylesheet\" href=\"{{ url_for('static', filename='styles.css') }}\">\n  <link rel=\"stylesheet\" href=\"{{ url_for('static', filename='tv-nav.css') }}\">",
    )
    replace(
        "demo-app/templates/index.html",
        "  <script type=\"module\" src=\"{{ url_for('static', filename='app.js') }}\"></script>",
        "  <script type=\"module\" src=\"{{ url_for('static', filename='app.js') }}\"></script>\n  <script type=\"module\" src=\"{{ url_for('static', filename='tv-nav.js') }}\"></script>",
    )


def ticket_5():
    write("demo-app/static/rails.js", '''async function buildRails() {
  if (!document.body.classList.contains('tv')) return;
  const response = await fetch('/api/rails');
  const rails = await response.json();
  const grid = document.querySelector('#movie-grid');
  const cards = new Map([...grid.children].map(card => [card.querySelector('a').href.split('/').pop(), card]));
  const shelf = document.createElement('div'); shelf.className = 'rails';
  for (const rail of rails) {
    const section = document.createElement('section'); section.className = 'rail';
    section.innerHTML = `<h2>${rail.title}</h2><div class="rail-track"></div>`;
    for (const id of rail.movie_ids) if (cards.has(id)) section.lastElementChild.append(cards.get(id).cloneNode(true));
    shelf.append(section);
  }
  grid.replaceWith(shelf);
  const targets = [...shelf.querySelectorAll('.movie-card > a')];
  targets.forEach((target, index) => target.tabIndex = index === 0 ? 0 : -1);
  targets[0]?.focus();
}
buildRails();
''')
    write("demo-app/static/tv-rails.css", '''body.tv .section-heading,body.tv #movie-grid { display:none; }
.rails { display:grid; gap:3vh; }.rail h2 { margin:0 0 1.3vh; font-size:1.6vw; }
.rail-track { display:grid; grid-auto-flow:column; grid-auto-columns:14vw; gap:1.5vw; overflow:hidden; padding:1vh .4vw 2vh; }
.rail .movie-card:nth-child(n+7) { display:none; }
''')
    replace(
        "demo-app/templates/index.html",
        "  <link rel=\"stylesheet\" href=\"{{ url_for('static', filename='tv-nav.css') }}\">",
        "  <link rel=\"stylesheet\" href=\"{{ url_for('static', filename='tv-nav.css') }}\">\n  <link rel=\"stylesheet\" href=\"{{ url_for('static', filename='tv-rails.css') }}\">",
    )
    replace(
        "demo-app/templates/index.html",
        "  <script type=\"module\" src=\"{{ url_for('static', filename='tv-nav.js') }}\"></script>",
        "  <script type=\"module\" src=\"{{ url_for('static', filename='tv-nav.js') }}\"></script>\n  <script type=\"module\" src=\"{{ url_for('static', filename='rails.js') }}\"></script>",
    )


def ticket_6():
    replace(
        "demo-app/app.py", 'return render_template("detail.html", movie=movie)',
        'return render_template("detail.html", movie=movie, tv_mode=is_tv_mode())',
    )
    replace(
        "demo-app/templates/detail.html", '<body class="detail-page">',
        '<body class="detail-page {{ \'tv\' if tv_mode else \'mobile\' }}">',
    )
    replace(
        "demo-app/templates/detail.html",
        "  <link rel=\"stylesheet\" href=\"{{ url_for('static', filename='styles.css') }}\">",
        "  <link rel=\"stylesheet\" href=\"{{ url_for('static', filename='styles.css') }}\">\n  <link rel=\"stylesheet\" href=\"{{ url_for('static', filename='tv-detail.css') }}\">",
    )
    replace(
        "demo-app/templates/detail.html", "</body>",
        "  <script type=\"module\" src=\"{{ url_for('static', filename='tv-detail.js') }}\"></script>\n</body>",
    )
    write("demo-app/static/tv-detail.css", '''body.tv.detail-page { padding:0; background:radial-gradient(circle at 20% 30%,#25233e,#08090d 56%); }
body.tv .detail-shell { max-width:none; min-height:100vh; padding:8vh 8vw 8vh 49vw; display:flex; flex-direction:column; justify-content:center; }
body.tv .detail-poster { position:absolute; left:9vw; top:10vh; width:29vw; height:78vh; }
body.tv .detail-shell h1 { font-size:5vw; }.detail-page.tv .synopsis { max-width:42vw; font-size:1.4vw; }
body.tv .detail-shell .primary { width:20vw; font-size:1.2vw; }
body.tv a:focus,body.tv button:focus { outline:5px solid var(--lime); outline-offset:5px; }
''')
    write("demo-app/static/tv-detail.js", '''if (document.body.classList.contains('tv')) {
  const actions = [...document.querySelectorAll('.detail-shell a,.detail-shell button')];
  actions[0]?.focus();
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' || event.key === 'Backspace') { event.preventDefault(); history.back(); }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      const at = Math.max(0, actions.indexOf(document.activeElement));
      actions[(at + (event.key === 'ArrowDown' ? 1 : actions.length - 1)) % actions.length].focus();
    }
  });
}
''')


def ticket_7():
    replace(
        "demo-app/app.py", "    return app\n", '''    @app.get("/api/rails")
    def rails_api():
        def ids(predicate):
            return [movie["id"] for movie in catalog if predicate(movie)][:8]
        watchlist = app.config["WATCHLIST"]
        return jsonify([
            {"title": "Trending now", "movie_ids": [movie["id"] for movie in catalog[:8]]},
            {"title": "My watchlist", "movie_ids": ids(lambda movie: movie["id"] in watchlist)},
            {"title": "Science fiction", "movie_ids": ids(lambda movie: "Sci-Fi" in movie["genres"])},
            {"title": "Mysteries", "movie_ids": ids(lambda movie: "Mystery" in movie["genres"])},
        ])

    return app
''')
    write("demo-app/tests/test_rails.py", '''def test_rails_are_curated_and_stable(client):
    rails = client.get("/api/rails").get_json()
    assert [rail["title"] for rail in rails] == ["Trending now", "My watchlist", "Science fiction", "Mysteries"]
    assert len(rails[0]["movie_ids"]) == 8
    assert len(rails[2]["movie_ids"]) >= 3


def test_watchlist_rail_reflects_session_state(client):
    client.post("/api/watchlist", json={"id": "afterlight"})
    assert client.get("/api/rails").get_json()[1]["movie_ids"] == ["afterlight"]
''')


TICKETS = {1: ticket_1, 2: ticket_2, 3: ticket_3, 4: ticket_4, 5: ticket_5, 6: ticket_6, 7: ticket_7}


def main():
    number = int(sys.argv[1])
    if number == 8:
        print("Ticket #8 is not actionable: no measurable acceptance criteria, target screens, or expected behavior.", file=sys.stderr)
        return 2
    action = TICKETS.get(number)
    if not action:
        print(f"No scripted mock action for ticket #{number}", file=sys.stderr)
        return 2
    action()
    status = subprocess.run(["git", "status", "--porcelain"], text=True, capture_output=True, check=True).stdout
    if status:
        subprocess.run(["git", "add", "-A"], check=True)
        subprocess.run(["git", "commit", "-m", f"factory(#{number}): implement mock ticket"], check=True)
    print(f"Mock agent completed ticket #{number}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
