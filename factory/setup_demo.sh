#!/bin/sh
set -eu

force=false
scenario=tv
while [ "$#" -gt 0 ]; do
  case "$1" in
    --force) force=true ;;
    --scenario)
      shift
      [ "$#" -gt 0 ] || { echo "--scenario requires tv or recipe-rebrand" >&2; exit 2; }
      scenario=$1
      ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done
case "$scenario" in tv|recipe-rebrand) ;; *) echo "Unknown scenario: $scenario" >&2; exit 2 ;; esac

repo=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
repo_parent=$(CDPATH= cd -- "$repo/.." && pwd)
cd "$repo"

if [ ! -f factory/orchestrator.py ] || [ ! -f demo-app/app.py ]; then
  echo "Run setup_demo.sh from the Software (re)-Factory repository." >&2
  exit 1
fi

if [ ! -d .git ]; then
  git init -b main >/dev/null
fi

demo_changes=$(git status --porcelain -- demo-app)
if [ -n "$demo_changes" ] && [ "$force" != true ]; then
  echo "Refusing to reset because demo-app has uncommitted changes:" >&2
  echo "$demo_changes" >&2
  echo "Commit them, move them elsewhere, or rerun with --force." >&2
  exit 1
fi
git config user.name >/dev/null 2>&1 || git config user.name "Factory Rehearsal"
git config user.email >/dev/null 2>&1 || git config user.email "factory@example.invalid"

git worktree list --porcelain | awk '/^worktree /{print substr($0,10)}' | while IFS= read -r worktree; do
  case "$worktree" in
    "$repo_parent"/wt-[0-9]*) git worktree remove --force "$worktree" >/dev/null 2>&1 || true ;;
  esac
done
git worktree prune

baseline_subject="chore: establish factory workshop baseline"

fresh_history=false
if ! git rev-parse --verify HEAD >/dev/null 2>&1; then
  git add -A
  git commit -m "$baseline_subject" >/dev/null
  fresh_history=true
fi

# The tag must name the mobile workpiece, never whatever HEAD happens to be: a
# baseline taken from a finished rehearsal grades new tickets against tests for
# a product they replaced.
if [ "$fresh_history" = true ]; then
  expected_baseline=$(git rev-parse HEAD)
else
  expected_baseline=$(git rev-list --max-count=1 --grep="^${baseline_subject}\$" HEAD || true)
fi

if [ -z "$expected_baseline" ]; then
  echo "Cannot locate the workshop baseline commit (\"$baseline_subject\")." >&2
  echo "Fetch it with 'git fetch origin --tags', or tag it explicitly:" >&2
  echo "  git tag -f factory-baseline <mobile-baseline-commit>" >&2
  exit 1
fi

current_baseline=$(git rev-parse --verify --quiet refs/tags/factory-baseline^{commit} || true)
if [ "$current_baseline" != "$expected_baseline" ]; then
  [ -n "$current_baseline" ] && echo "Repointing factory-baseline: $current_baseline -> $expected_baseline"
  git tag -f factory-baseline "$expected_baseline" >/dev/null
fi

git restore --source=factory-baseline --staged --worktree -- demo-app
git add demo-app
if ! git diff --cached --quiet; then
  git commit -m "chore: reset Pocket Cinema to mobile baseline" >/dev/null
fi

git for-each-ref --format='%(refname:short)' 'refs/heads/factory/*' | while IFS= read -r branch; do
  [ -n "$branch" ] && git branch -D "$branch" >/dev/null 2>&1 || true
done

mkdir -p .factory
find .factory/logs .factory/prompts .factory/qa-approvals -type f -delete 2>/dev/null || true
rm -f .factory/state.json .factory/state.tmp .factory/ids.json

if [ ! -x .factory/venv/bin/python ]; then
  python3 -m venv .factory/venv
fi
.factory/venv/bin/python -m pip install -q -r demo-app/requirements.txt

cat > .factory/state.json <<JSON
{
  "mode": "mock",
  "scenario": "$scenario",
  "states": ["Backlog", "Ready", "In Progress", "QA Review", "Verifying", "In Review", "Done", "Blocked"],
  "updated_at": "waiting for run",
  "tickets": []
}
JSON

echo "Factory reset complete for scenario: $scenario"
echo "Run: ./factory/factory run --mock --scenario $scenario --once"
echo "Board: python3 -m http.server 8000, then open http://localhost:8000/factory/dashboard.html"
