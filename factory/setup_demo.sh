#!/bin/sh
set -eu

repo=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
repo_parent=$(CDPATH= cd -- "$repo/.." && pwd)
cd "$repo"

if [ ! -f factory/orchestrator.py ] || [ ! -f demo-app/catalog.json ]; then
  echo "Run setup_demo.sh from the Software (re)-Factory repository." >&2
  exit 1
fi

if [ ! -d .git ]; then
  git init -b main >/dev/null
fi
git config user.name >/dev/null 2>&1 || git config user.name "Factory Rehearsal"
git config user.email >/dev/null 2>&1 || git config user.email "factory@example.invalid"

git worktree list --porcelain | awk '/^worktree /{print substr($0,10)}' | while IFS= read -r worktree; do
  case "$worktree" in
    "$repo_parent"/wt-[0-9]*) git worktree remove --force "$worktree" >/dev/null 2>&1 || true ;;
  esac
done
git worktree prune

if ! git rev-parse --verify HEAD >/dev/null 2>&1; then
  git add -A
  git commit -m "chore: establish factory workshop baseline" >/dev/null
fi
if ! git rev-parse refs/tags/factory-baseline >/dev/null 2>&1; then
  git tag factory-baseline
fi

git restore --source=factory-baseline -- demo-app
git add demo-app
if ! git diff --cached --quiet; then
  git commit -m "chore: reset Pocket Cinema to mobile baseline" >/dev/null
fi

git for-each-ref --format='%(refname:short)' 'refs/heads/factory/*' | while IFS= read -r branch; do
  [ -n "$branch" ] && git branch -D "$branch" >/dev/null 2>&1 || true
done

mkdir -p .factory
find .factory/logs .factory/prompts -type f -delete 2>/dev/null || true
rm -f .factory/state.json .factory/state.tmp .factory/ids.json

if [ ! -x .factory/venv/bin/python ]; then
  python3 -m venv .factory/venv
fi
.factory/venv/bin/python -m pip install -q -r demo-app/requirements.txt

cat > .factory/state.json <<'JSON'
{
  "mode": "mock",
  "states": ["Backlog", "Ready", "In Progress", "Verifying", "In Review", "Done", "Blocked"],
  "updated_at": "waiting for run",
  "tickets": []
}
JSON

echo "Factory reset complete."
echo "Run: ./factory/factory run --mock --once"
echo "Board: python3 -m http.server 8000, then open http://localhost:8000/factory/dashboard.html"
