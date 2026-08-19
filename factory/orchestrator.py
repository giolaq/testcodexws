#!/usr/bin/env python3
"""Software (re)-Factory: a small, visible coding-agent pipeline.

Tickets start as GitHub issues (or seed JSON in a Rehearsal Run). The scheduler
unlocks dependency-ready work, creates one Git worktree per ticket, asks an
independent QA agent to commit protected acceptance tests, runs the selected
implementation agent, verifies ordered gates, retries with the failure in the
prompt, then publishes a PR. A Rehearsal Run (`--mock`) follows the implementation path but
skips real QA by default and merges locally.
Every transition is mirrored to .factory/state.json for the dashboard.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time
import tomllib
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from doctor import run_doctor
from github_backend import GitHubBackend, GitHubError
from planner import approve_plan
from planning_pipeline import (
    approve_product,
    continue_plan,
    load_manifest,
    mark_published,
    plan_prd,
    prepare_publication,
    resolve_run,
    review as review_plan,
)
from session_config import (
    PRESETS,
    configure_session,
    load_session_config,
    remember_project,
    render_session_config,
)

STATES = ["Backlog", "Ready", "In Progress", "QA Review", "Verifying", "In Review", "Done", "Blocked"]
ACTIVE = {"In Progress", "Verifying"}
TERMINAL = {"Done", "Blocked"}
DEFAULT_AGENTS = {
    "claude": 'claude -p "$(cat {prompt})" --permission-mode acceptEdits',
    "codex": '{codex} exec --sandbox workspace-write --ephemeral "$(cat {prompt})"',
    "cursor": 'cursor-agent -p "$(cat {prompt})"',
    "mock": "{python} factory/mock_agent.py {ticket} --scenario {scenario}",
    "mock-qa": "{python} factory/mock_qa_agent.py {ticket} --scenario {scenario}",
}
DEFAULT_QA = {
    "agent": "codex",
    "max_retries": 1,
    "test_roots": ["demo-app/tests", "demo-app/static/tests"],
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run(cmd, cwd: Path, *, timeout=None, check=True, shell=False):
    result = subprocess.run(
        cmd, cwd=cwd, text=True, capture_output=True, timeout=timeout,
        shell=shell, executable="/bin/sh" if shell else None,
    )
    if check and result.returncode:
        rendered = cmd if isinstance(cmd, str) else shlex.join(cmd)
        raise RuntimeError(f"{rendered}\n{result.stdout}{result.stderr}".strip())
    return result


def load_config(repo: Path) -> dict:
    cfg = {
        "factory": {"max_retries": 2, "poll_interval": 20, "agent_timeout": 900, "gate_timeout": 300},
        "agents": DEFAULT_AGENTS.copy(),
        "qa": {**DEFAULT_QA, "test_roots": DEFAULT_QA["test_roots"].copy()},
        "gate": [{"name": "tests", "cmd": "{python} -m pytest -q", "required": True}],
    }
    path = repo / "factory" / "factory.toml"
    if path.exists():
        supplied = tomllib.loads(path.read_text())
        cfg["factory"].update(supplied.get("factory", {}))
        cfg["agents"].update(supplied.get("agents", {}))
        cfg["qa"].update(supplied.get("qa", {}))
        if supplied.get("gate"):
            cfg["gate"] = supplied["gate"]
    return cfg


def validate_qa_config(qa: dict, agents: dict):
    agent = qa.get("agent")
    if agent not in agents or agent == "mock":
        raise ValueError("qa.agent must name a configured non-mock adapter")
    retries = qa.get("max_retries")
    if not isinstance(retries, int) or retries < 0:
        raise ValueError("qa.max_retries must be a non-negative integer")
    roots = qa.get("test_roots")
    if not isinstance(roots, list) or not roots or not all(isinstance(root, str) and root for root in roots):
        raise ValueError("qa.test_roots must be a non-empty list of repository-relative directories")
    for root in roots:
        path = PurePosixPath(root)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"qa.test_roots must stay inside the repository: {root}")


def validate_qa_changes(changes: list[tuple[str, str]], ticket_number: int, test_roots: list[str]) -> list[str]:
    """Return policy failures for the files produced by an independent QA agent."""
    if not changes:
        return ["QA agent did not create an acceptance-test file"]
    errors = []
    roots = [root.strip("/") + "/" for root in test_roots]
    python_name = re.compile(rf"test_ticket_{ticket_number}(?:_[a-z0-9_]+)?\.py$")
    javascript_name = re.compile(rf"ticket-{ticket_number}(?:-[a-z0-9-]+)?\.test\.js$")
    for status, raw_path in changes:
        path = PurePosixPath(raw_path).as_posix().lstrip("./")
        if status != "A":
            errors.append(f"QA may only add new test files, but {raw_path} has Git status {status}")
            continue
        if not any(path.startswith(root) for root in roots):
            errors.append(f"QA changed {raw_path}, which is outside the configured test roots")
            continue
        name = PurePosixPath(path).name
        if not (python_name.fullmatch(name) or javascript_name.fullmatch(name)):
            errors.append(
                f"Acceptance Test {raw_path} must be named test_ticket_{ticket_number}[_topic].py "
                f"or ticket-{ticket_number}[-topic].test.js"
            )
    return errors


def parse_dependencies(body: str) -> list[int]:
    match = re.search(r"(?im)^\s*Depends-on:\s*(.+)$", body or "")
    return [int(n) for n in re.findall(r"#(\d+)", match.group(1))] if match else []


def parse_agent(body: str, default: str) -> str:
    match = re.search(r"(?im)^\s*agent:\s*([a-z][a-z0-9_-]{0,31})\s*$", body or "")
    return match.group(1).lower() if match else default


def slugify(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:42] or "ticket"


def resolve_codex_cli() -> str:
    """Find a current, ChatGPT-authenticated Codex CLI, skipping legacy binaries."""
    override = os.environ.get("FACTORY_CODEX_BIN")
    candidates = [override] if override else [
        shutil.which("codex"),
        "/Applications/ChatGPT.app/Contents/Resources/codex",
    ]
    compatible = []
    for candidate in dict.fromkeys(c for c in candidates if c):
        try:
            help_result = subprocess.run(
                [candidate, "exec", "--help"], text=True, capture_output=True, timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        help_text = help_result.stdout + help_result.stderr
        if help_result.returncode or "codex exec" not in help_text.lower():
            continue
        compatible.append(candidate)
        try:
            status = subprocess.run(
                [candidate, "login", "status"], text=True, capture_output=True, timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if status.returncode == 0:
            return candidate
    if compatible:
        raise RuntimeError(
            f"Codex CLI is not signed in. Run `{shlex.quote(compatible[0])} login`, then retry."
        )
    if override:
        raise RuntimeError(f"FACTORY_CODEX_BIN does not point to a current Codex CLI: {override}")
    raise RuntimeError(
        "No current Codex CLI was found. Install/update Codex or set FACTORY_CODEX_BIN "
        "to the Codex binary bundled with the ChatGPT app."
    )


def resolve_planning_cli(agent: str) -> str:
    if agent == "codex":
        return resolve_codex_cli()
    if agent != "claude":
        raise ValueError(f"unsupported planning agent: {agent}")
    binary = shutil.which("claude")
    if not binary:
        raise RuntimeError("Claude Code CLI not found. Install Claude Code, then run `claude auth login`.")
    help_result = subprocess.run([binary, "--help"], text=True, capture_output=True, timeout=10)
    if help_result.returncode or "--json-schema" not in help_result.stdout + help_result.stderr:
        raise RuntimeError("Claude Code is too old for structured planning output. Update it, then retry.")
    auth = subprocess.run(
        [binary, "auth", "status", "--text"], text=True, capture_output=True, timeout=10,
    )
    if auth.returncode:
        raise RuntimeError("Claude Code is not signed in. Run `claude auth login`, then retry.")
    return binary


def apply_session_defaults(args, repo: Path) -> dict:
    """Apply ignored local defaults after argparse, preserving explicit flags."""
    session = load_session_config(repo)
    if args.command == "run":
        if args.mock:
            args.agent = args.agent or "codex"
            args.review_qa_tests = bool(args.review_qa_tests)
            args.max_parallel = args.max_parallel or 4
        else:
            args.agent = args.agent or session.get("agent", "codex")
            args.qa_agent = args.qa_agent or session.get("qa_agent")
            if args.review_qa_tests is None:
                args.review_qa_tests = session.get("review_qa_tests", False)
            args.max_parallel = args.max_parallel or session.get("max_parallel", 4)
            args.project_number = args.project_number or session.get("project_number")
    elif args.command == "plan":
        args.default_agent = args.default_agent or session.get("agent", "codex")
        args.planning_agent = args.planning_agent or session.get("planning_agent", "codex")
    elif args.command == "approve":
        if args.project_number is None and not args.new_project_title:
            args.project_number = session.get("project_number")
    elif args.command == "retry":
        args.project_number = args.project_number or session.get("project_number")
    elif args.command == "seed":
        args.agent = args.agent or session.get("agent", "codex")
    elif args.command == "doctor":
        args.agent = args.agent or session.get("agent", "codex")
        args.qa_agent = args.qa_agent or session.get("qa_agent")
        args.planning_agent = args.planning_agent or session.get("planning_agent", "codex")
    return session


def resolved_run_config(args, session: dict) -> dict:
    qa_agent = "disabled" if args.no_qa else (
        args.qa_agent or load_config(Path(args.repo).resolve())["qa"]["agent"]
    )
    return {
        **session,
        "agent": args.agent,
        "qa_agent": qa_agent,
        "review_qa_tests": args.review_qa_tests,
        "max_parallel": args.max_parallel,
        **({"project_number": args.project_number} if args.project_number else {}),
    }


def seed_backlog(repo: Path, args):
    print(
        "Using deterministic fallback tickets. This bypasses PRD planning and "
        "the product/alignment review gates.",
        flush=True,
    )
    command = [
        sys.executable, str(repo / "factory/seed_github.py"),
        "--repo", str(repo), "--agent", args.agent, "--scenario", args.scenario,
    ]
    if args.github_repo:
        command.extend(["--github-repo", args.github_repo])
    if args.dry_run:
        command.append("--dry-run")
    result = subprocess.run(command, cwd=repo)
    if result.returncode:
        raise RuntimeError("deterministic ticket seeding failed")


class StateStore:
    def __init__(self, repo: Path):
        self.path = repo / ".factory" / "state.json"
        self.lock = threading.RLock()
        self.data = {"updated_at": now(), "tickets": []}
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text())
            except (OSError, json.JSONDecodeError):
                pass

    def save(self):
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.data["updated_at"] = now()
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, indent=2) + "\n")
            os.replace(tmp, self.path)


class Factory:
    def __init__(self, args):
        self.args = args
        self.repo = Path(args.repo).resolve()
        self.cfg = load_config(self.repo)
        validate_qa_config(self.cfg["qa"], self.cfg["agents"])
        if args.agent not in self.cfg["agents"]:
            raise ValueError(
                f"--agent {args.agent!r} is not registered in factory/factory.toml [agents]"
            )
        requested_qa = args.qa_agent or self.cfg["qa"]["agent"]
        if args.no_qa:
            self.qa_agent = None
        elif args.mock and args.qa_agent is None:
            self.qa_agent = "mock-qa"
        else:
            self.qa_agent = requested_qa
        if self.qa_agent and (
            self.qa_agent not in self.cfg["agents"]
            or self.qa_agent == "mock"
            or (self.qa_agent == "mock-qa" and not args.mock)
        ):
            raise ValueError("--qa-agent must name a configured non-mock adapter")
        self.review_qa_tests = bool(args.review_qa_tests or self.cfg["qa"].get("require_human_approval", False))
        self.python = sys.executable
        self.store = StateStore(self.repo)
        self.tickets: dict[int, dict] = {}
        self.transition_lock = threading.RLock()
        self.merge_lock = threading.Lock()
        self.last_deadlock = None
        self.last_qa_wait = None
        self.codex_bin = None
        self.backend = None if args.mock else GitHubBackend(self.repo, args.project_number)

    def load_tickets(self):
        if self.args.mock:
            scenario_path = self.repo / "factory/scenarios" / self.args.scenario / "tickets.json"
            source_path = scenario_path if scenario_path.is_file() else self.repo / "factory/seed/tickets.json"
            source = json.loads(source_path.read_text())
        else:
            source = self.backend.load(read_only=self.args.dry_run)
            if not self.args.dry_run and self.backend.project_number:
                remember_project(self.repo, self.backend.project_number)
        previous = {t["number"]: t for t in self.store.data.get("tickets", [])}
        for raw in source:
            number = int(raw["number"])
            old = previous.get(number, {})
            ticket = {
                "number": number, "title": raw["title"], "body": raw.get("body", ""),
                "labels": raw.get("labels", []), "status": raw.get("status", old.get("status", "Backlog")),
                "agent": parse_agent(raw.get("body", ""), "mock" if self.args.mock else self.args.agent),
                "dependencies": parse_dependencies(raw.get("body", "")),
                "attempt": old.get("attempt", 0), "branch": old.get("branch", ""),
                "base_sha": old.get("base_sha", ""),
                "qa_agent": self.qa_agent or "", "qa_attempt": old.get("qa_attempt", 0),
                "qa_commit": old.get("qa_commit", ""), "qa_tests": old.get("qa_tests", {}),
                "qa_approved": old.get("qa_approved", False),
                "pr_url": raw.get("pr_url", old.get("pr_url", "")),
                "issue_url": raw.get("url", old.get("issue_url", "")),
                "failure": old.get("failure", ""), "warnings": old.get("warnings", []),
                "gate_results": old.get("gate_results", []),
                "changed_files": old.get("changed_files", []),
                "current_prompt": old.get("current_prompt", ""),
                "current_log": old.get("current_log", ""),
                "phase": old.get("phase", ""),
                "history": old.get("history", []), "mock_action": raw.get("mock_action", ""),
                "simulate_merge_conflict": raw.get("simulate_merge_conflict", False),
            }
            if ticket["agent"] not in self.cfg["agents"]:
                raise ValueError(
                    f"Ticket #{number} requests unregistered agent {ticket['agent']!r}; "
                    "add it to factory/factory.toml [agents] or edit the ticket"
                )
            recovered = ticket["status"] in ACTIVE
            if recovered:
                ticket["status"] = "Backlog"  # safely replay interrupted work
                ticket.update(qa_approved=False, qa_commit="", qa_tests={}, base_sha="")
                ticket["history"].append({"at": now(), "status": "Backlog", "note": "Recovered after restart"})
            self.tickets[number] = ticket
            if recovered and self.backend and not self.args.dry_run:
                self.backend.set_status(ticket, "Backlog", "Recovered after restart")
        self._sync_store(save=not self.args.dry_run)

    def _sync_store(self, save=True):
        self.store.data["mode"] = "mock" if self.args.mock else "github"
        self.store.data["scenario"] = self.args.scenario
        self.store.data["qa_review_required"] = self.review_qa_tests
        self.store.data["states"] = STATES
        self.store.data["tickets"] = sorted(self.tickets.values(), key=lambda t: t["number"])
        if save:
            self.store.save()

    def transition(self, ticket: dict, status: str, note=""):
        if status not in STATES:
            raise ValueError(status)
        with self.transition_lock:
            ticket["status"] = status
            if status != "In Progress":
                ticket["phase"] = status.lower().replace(" ", "-")
            if status == "In Progress" and not ticket.get("started_at"):
                ticket["started_at"] = now()
            if status in TERMINAL | {"In Review"}:
                ticket["finished_at"] = now()
            ticket["history"].append({"at": now(), "status": status, "note": note})
            if self.backend:
                self.backend.set_status(ticket, status, note)
            self._sync_store()
            print(f"#{ticket['number']:<3} {status:<12} {note}".rstrip(), flush=True)

    def detect_cycles(self) -> list[list[int]]:
        visiting, visited, stack, cycles = set(), set(), [], []
        def visit(n):
            if n in visiting:
                i = stack.index(n)
                cycles.append(stack[i:] + [n])
                return
            if n in visited or n not in self.tickets:
                return
            visiting.add(n); stack.append(n)
            for dep in self.tickets[n]["dependencies"]:
                visit(dep)
            stack.pop(); visiting.remove(n); visited.add(n)
        for n in self.tickets:
            visit(n)
        return cycles

    def refresh_readiness(self):
        for ticket in self.tickets.values():
            if ticket["status"] in TERMINAL | {"In Review", "QA Review"}:
                continue
            ready_label = self.args.mock or "agent-ready" in ticket["labels"]
            deps_done = all(self.tickets.get(n, {}).get("status") == "Done" for n in ticket["dependencies"])
            wanted = "Ready" if ready_label and deps_done else "Backlog"
            if ticket["status"] != wanted:
                self.transition(ticket, wanted, "Dependencies satisfied" if wanted == "Ready" else "Waiting for dependencies")

    def apply_qa_approvals(self):
        approval_dir = self.repo / ".factory/qa-approvals"
        for ticket in self.tickets.values():
            marker = approval_dir / str(ticket["number"])
            if ticket["status"] != "QA Review" or not marker.is_file():
                continue
            worktree = self.repo.parent / f"wt-{ticket['number']}"
            failure = self.verify_qa_tests_unchanged(ticket, worktree)
            if failure:
                ticket["failure"] = failure
                marker.unlink(missing_ok=True)
                self.transition(ticket, "Blocked", "Acceptance Tests changed before human approval")
                continue
            marker.unlink(missing_ok=True)
            ticket["qa_approved"] = True
            self.transition(ticket, "Ready", "Human approved independent Acceptance Tests")

    def dry_plan(self):
        remaining = set(self.tickets)
        done, wave = set(), 1
        while remaining:
            ready = sorted(n for n in remaining if set(self.tickets[n]["dependencies"]) <= done)
            if not ready:
                print("Blocked by cycle or missing dependency: " + ", ".join(f"#{n}" for n in sorted(remaining)))
                return
            print(f"Wave {wave}: " + ", ".join(f"#{n} {self.tickets[n]['title']}" for n in ready))
            done.update(ready); remaining.difference_update(ready); wave += 1

    def git(self, *args, cwd=None, **kwargs):
        return run(["git", *args], cwd or self.repo, **kwargs)

    def sync_default_branch(self):
        """Fast-forward the local default branch before dependent work starts."""
        if not self.backend:
            return self.git("rev-parse", "HEAD").stdout.strip()
        branch = self.backend.default_branch
        current = self.git("branch", "--show-current").stdout.strip()
        if current != branch:
            raise RuntimeError(
                f"Factory must run from the GitHub default branch `{branch}`, not `{current or 'detached HEAD'}`"
            )
        dirty = self.git("status", "--porcelain").stdout.strip()
        if dirty:
            raise RuntimeError("Default branch has uncommitted changes; commit or stash them before factory run")
        with self.merge_lock:
            self.git("fetch", "origin", branch)
            self.git("merge", "--ff-only", f"origin/{branch}")
            return self.git("rev-parse", "HEAD").stdout.strip()

    def create_worktree(self, ticket: dict):
        branch = f"factory/{ticket['number']}-{slugify(ticket['title'])}"
        worktree = self.repo.parent / f"wt-{ticket['number']}"
        with self.merge_lock:
            self.git("worktree", "remove", "--force", str(worktree), check=False)
            self.git("branch", "-D", branch, check=False)
            self.git("worktree", "prune")
            base_sha = self.git("rev-parse", "HEAD").stdout.strip()
            self.git("worktree", "add", "-b", branch, str(worktree), base_sha)
        ticket["branch"] = branch
        ticket["base_sha"] = base_sha
        self._sync_store()
        return worktree, base_sha

    def make_prompt(self, ticket: dict, failure: str) -> Path:
        path = self.repo / ".factory/prompts" / f"{ticket['number']}-attempt{ticket['attempt']}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        gates = "\n".join(f"- {g['name']}: `{g['cmd']}`" for g in self.cfg["gate"])
        retry = f"\n## Previous failure\n```\n{failure[-3000:]}\n```\n" if failure else ""
        protected = ""
        if ticket.get("qa_tests"):
            paths = "\n".join(f"- `{path}`" for path in sorted(ticket["qa_tests"]))
            protected = (
                "\n## Independent QA acceptance tests\n"
                f"The {ticket['qa_agent']} QA agent created and committed these protected tests:\n{paths}\n\n"
                "Make the implementation pass them. You may add other tests, but do not edit, "
                "rename, delete, skip, or weaken the protected tests; the factory verifies their Git hashes.\n"
            )
        path.write_text(
            f"# Ticket #{ticket['number']}: {ticket['title']}\n\n{ticket['body']}\n\n"
            f"## Verification gates\n{gates}\n{protected}\nCommit as `factory(#{ticket['number']}): <summary>`.\n"
            "Work only in the current worktree. Do not change ticket scope.\n" + retry
        )
        return path

    def make_qa_prompt(self, ticket: dict, failure: str) -> Path:
        attempt = ticket["qa_attempt"]
        path = self.repo / ".factory/prompts" / f"{ticket['number']}-qa-attempt{attempt}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        roots = "\n".join(f"- `{root}/`" for root in self.cfg["qa"]["test_roots"])
        gates = "\n".join(f"- {g['name']}: `{g['cmd']}`" for g in self.cfg["gate"])
        retry = f"\n## Previous QA failure\n```\n{failure[-3000:]}\n```\n" if failure else ""
        path.write_text(
            f"# QA assignment for ticket #{ticket['number']}: {ticket['title']}\n\n{ticket['body']}\n\n"
            "## Role\n"
            "Act as the independent QA engineer before implementation begins. Translate the ticket's "
            "acceptance criteria into deterministic executable acceptance tests. Inspect production code "
            "only to understand public behavior; do not implement or repair the feature.\n\n"
            "## Test-file contract\n"
            "- Add at least one new test file. Do not edit, rename, or delete an existing file.\n"
            f"- Python files must be named `test_ticket_{ticket['number']}[_topic].py`.\n"
            f"- JavaScript files must be named `ticket-{ticket['number']}[-topic].test.js`.\n"
            f"- Add files only below these roots:\n{roots}\n"
            "- Cover each automatable acceptance criterion, including failure and boundary cases.\n"
            "- Use the repository's existing test tools and fixtures; keep tests offline and deterministic.\n"
            "- Tests for missing behavior are expected to fail before implementation. Existing behavior "
            "may already satisfy regression-oriented criteria.\n"
            "- Do not skip tests, soften assertions, change production files, or commit; the factory commits "
            "the accepted QA files separately.\n\n"
            f"## Later verification gates\n{gates}\n" + retry
        )
        return path

    def run_adapter(
        self, agent: str, ticket: dict, worktree: Path, prompt: Path, log_name: str,
        phase: str,
    ):
        template = self.cfg["agents"].get(agent)
        if not template:
            return 2, f"Unknown agent adapter: {agent}"
        command = template.format(
            prompt=shlex.quote(str(prompt)), ticket=ticket["number"],
            python=shlex.quote(self.python), codex=shlex.quote(self.codex_bin or "codex"),
            scenario=shlex.quote(self.args.scenario),
            repo=shlex.quote(str(self.repo)), worktree=shlex.quote(str(worktree)),
        )
        log = self.repo / ".factory/logs" / log_name
        log.parent.mkdir(parents=True, exist_ok=True)
        ticket.update(
            phase=phase,
            current_prompt=str(prompt.relative_to(self.repo)),
            current_log=str(log.relative_to(self.repo)),
            phase_started_at=now(),
        )
        self._sync_store()
        chunks = []
        with log.open("w") as stream:
            process = subprocess.Popen(
                command, cwd=worktree, text=True, shell=True, executable="/bin/sh",
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            )

            def copy_output():
                for chunk in iter(process.stdout.readline, ""):
                    chunks.append(chunk)
                    stream.write(chunk)
                    stream.flush()

            reader = threading.Thread(target=copy_output, daemon=True)
            reader.start()
            try:
                returncode = process.wait(timeout=self.cfg["factory"]["agent_timeout"])
            except subprocess.TimeoutExpired:
                process.kill()
                returncode = 124
                timeout_message = f"Agent timed out after {self.cfg['factory']['agent_timeout']}s\n"
                chunks.append(timeout_message); stream.write(timeout_message); stream.flush()
            reader.join(timeout=5)
        output = "".join(chunks)
        ticket.update(last_agent_exit=returncode, phase_finished_at=now())
        self._sync_store()
        return returncode, output

    def run_agent(self, ticket: dict, worktree: Path, prompt: Path):
        return self.run_adapter(
            ticket["agent"], ticket, worktree, prompt,
            f"{ticket['number']}-attempt{ticket['attempt']}.log", "implementation",
        )

    def qa_changes(self, worktree: Path, base_sha: str) -> list[tuple[str, str]]:
        result = self.git("diff", "--name-status", base_sha, cwd=worktree)
        changes = []
        for line in result.stdout.splitlines():
            fields = line.split("\t")
            if len(fields) >= 2:
                changes.append((fields[0], fields[-1]))
        known = {path for _, path in changes}
        untracked = self.git("ls-files", "--others", "--exclude-standard", cwd=worktree)
        changes.extend(("A", path) for path in untracked.stdout.splitlines() if path not in known)
        return changes

    def snapshot_qa_tests(self, ticket: dict, worktree: Path, paths: list[str]):
        ticket["qa_commit"] = self.git("rev-parse", "HEAD", cwd=worktree).stdout.strip()
        ticket["qa_tests"] = {
            path: self.git("hash-object", path, cwd=worktree).stdout.strip()
            for path in sorted(paths)
        }
        ticket["qa_failure"] = ""
        ticket["failure"] = ""
        self._sync_store()

    def create_qa_tests(self, ticket: dict, worktree: Path, base_sha: str) -> str:
        ticket.update(qa_attempt=0, qa_commit="", qa_tests={}, qa_failure="")
        failure = ""
        max_attempts = int(self.cfg["qa"]["max_retries"]) + 1
        for attempt in range(1, max_attempts + 1):
            ticket["qa_attempt"] = attempt
            self._sync_store()
            prompt = self.make_qa_prompt(ticket, failure)
            code, output = self.run_adapter(
                self.qa_agent, ticket, worktree, prompt,
                f"{ticket['number']}-qa-attempt{attempt}.log", "qa",
            )
            if code:
                failure = output[-3000:]
            else:
                changes = self.qa_changes(worktree, base_sha)
                policy_errors = validate_qa_changes(
                    changes, ticket["number"], self.cfg["qa"]["test_roots"],
                )
                if not policy_errors:
                    self.commit_leftovers(
                        ticket, worktree,
                        f"test(#{ticket['number']}): add independent acceptance tests",
                    )
                    self.snapshot_qa_tests(ticket, worktree, [path for _, path in changes])
                    return ""
                failure = "\n".join(policy_errors)
            ticket["qa_failure"] = failure[-3000:]
            ticket["failure"] = "QA acceptance-test phase failed:\n" + ticket["qa_failure"]
            self._sync_store()
            if attempt < max_attempts:
                self.transition(ticket, "In Progress", f"Retrying QA ({attempt} of {max_attempts - 1})")
        return ticket["failure"]

    def verify_qa_tests_unchanged(self, ticket: dict, worktree: Path) -> str:
        changed = []
        for path, expected_hash in ticket.get("qa_tests", {}).items():
            file = worktree / path
            if not file.is_file():
                changed.append(f"{path} was deleted")
                continue
            actual_hash = self.git("hash-object", path, cwd=worktree).stdout.strip()
            if actual_hash != expected_hash:
                changed.append(f"{path} was modified")
        if not changed:
            return ""
        return "Independent Acceptance Tests are protected:\n" + "\n".join(f"- {item}" for item in changed)

    def commit_leftovers(self, ticket: dict, worktree: Path, message: str | None = None):
        if not self.git("status", "--porcelain", cwd=worktree).stdout.strip():
            return
        self.git("add", "-A", cwd=worktree)
        self.git("commit", "-m", message or f"factory(#{ticket['number']}): complete ticket", cwd=worktree)

    def verify(self, ticket: dict, worktree: Path):
        failures, warnings, gate_results = [], [], []
        for gate in self.cfg["gate"]:
            command = gate["cmd"].format(python=shlex.quote(self.python), repo=shlex.quote(str(self.repo)))
            started = time.monotonic()
            try:
                result = run(command, worktree, timeout=self.cfg["factory"]["gate_timeout"], check=False, shell=True)
                output = (result.stdout + result.stderr)[-3000:]
            except subprocess.TimeoutExpired:
                result = type("TimedOut", (), {"returncode": 124})()
                output = f"{gate['name']} timed out after {self.cfg['factory']['gate_timeout']}s"
            gate_results.append({
                "name": gate["name"], "required": gate.get("required", True),
                "exit_code": result.returncode, "output": output,
                "duration_seconds": round(time.monotonic() - started, 2),
            })
            if result.returncode:
                message = f"[{gate['name']}] exit {result.returncode}\n{output}"
                (failures if gate.get("required", True) else warnings).append(message)
        ticket["warnings"] = warnings
        ticket["gate_results"] = gate_results
        self._sync_store()
        return "\n\n".join(failures)

    def block_or_retry(self, ticket: dict, failure: str):
        ticket["failure"] = failure[-3000:]
        if ticket["attempt"] <= self.cfg["factory"]["max_retries"]:
            self.transition(ticket, "In Progress", f"Retry {ticket['attempt']} of {self.cfg['factory']['max_retries']}")
            return True
        self.transition(ticket, "Blocked", ticket["failure"][:180].replace("\n", " "))
        return False

    def publish(self, ticket: dict, worktree: Path):
        if self.args.mock:
            self.transition(ticket, "In Review", "Verification passed")
            if ticket.get("simulate_merge_conflict"):
                ticket["merge_conflict_path"] = "A competing integration was detected; the merge lock serialized it safely."
                ticket["history"].append({"at": now(), "status": "In Review", "note": "Merge-conflict rehearsal exercised"})
                self._sync_store()
            with self.merge_lock:
                merged = self.git("merge", "--no-ff", "-m", f"Merge ticket #{ticket['number']}", ticket["branch"], check=False)
                if merged.returncode:
                    self.git("merge", "--abort", check=False)
                    ticket["failure"] = "Merge conflict while integrating mock ticket\n" + merged.stdout + merged.stderr
                    self.transition(ticket, "Blocked", "Merge conflict; worktree preserved")
                    return
            self.transition(ticket, "Done", "Mock review merged locally")
            self.git("worktree", "remove", "--force", str(worktree), check=False)
            self.git("branch", "-d", ticket["branch"], check=False)
            return
        pr_url = self.backend.publish(ticket, worktree)
        ticket["pr_url"] = pr_url
        self.transition(ticket, "In Review", "PR opened after verification")

    def process(self, ticket: dict):
        resume_qa = bool(ticket.get("qa_approved") and ticket.get("qa_commit") and ticket.get("branch"))
        first_phase = (
            f"Running {ticket['agent']} with approved Acceptance Tests"
            if resume_qa else (f"Running QA {self.qa_agent}" if self.qa_agent else f"Running {ticket['agent']}")
        )
        self.transition(ticket, "In Progress", first_phase)
        if resume_qa:
            worktree = self.repo.parent / f"wt-{ticket['number']}"
            base_sha = ticket.get("base_sha", "")
            if not worktree.is_dir() or self.verify_qa_tests_unchanged(ticket, worktree):
                ticket["failure"] = "Approved QA worktree or protected tests are missing"
                self.transition(ticket, "Blocked", "Could not resume approved QA worktree")
                return
            implementation_base_sha = ticket["qa_commit"]
        else:
            try:
                worktree, base_sha = self.create_worktree(ticket)
            except Exception as exc:
                ticket["failure"] = str(exc)[-3000:]
                self.transition(ticket, "Blocked", "Could not create isolated worktree")
                return
            implementation_base_sha = base_sha
            if self.qa_agent:
                try:
                    qa_failure = self.create_qa_tests(ticket, worktree, base_sha)
                except Exception as exc:
                    qa_failure = f"QA acceptance-test phase failed:\n{exc}"
                if qa_failure:
                    ticket["failure"] = qa_failure[-3000:]
                    self.transition(ticket, "Blocked", "Independent QA could not produce valid acceptance tests")
                    return
                implementation_base_sha = ticket["qa_commit"]
                if self.review_qa_tests:
                    ticket["phase"] = "qa-review"
                    self.transition(
                        ticket, "QA Review",
                        f"Review {len(ticket['qa_tests'])} protected test(s), then run factory approve-tests {ticket['number']}",
                    )
                    return
                self.transition(
                    ticket, "In Progress",
                    f"QA committed {len(ticket['qa_tests'])} protected test(s); running {ticket['agent']}",
                )
        failure = ""
        max_attempts = self.cfg["factory"]["max_retries"] + 1
        for attempt in range(1, max_attempts + 1):
            ticket["attempt"] = attempt
            prompt = self.make_prompt(ticket, failure)
            code, output = self.run_agent(ticket, worktree, prompt)
            try:
                self.commit_leftovers(ticket, worktree)
                changed = self.git(
                    "diff", "--name-status", implementation_base_sha, "HEAD", cwd=worktree,
                ).stdout.splitlines()
                ticket["changed_files"] = [
                    {"status": fields[0], "path": fields[-1]}
                    for line in changed if len(fields := line.split("\t")) >= 2
                ]
                self._sync_store()
                commits = int(
                    self.git("rev-list", "--count", f"{implementation_base_sha}..HEAD", cwd=worktree).stdout
                )
            except Exception as exc:
                commits, output, code = 0, f"{output}\n{exc}", 1
            if code or not commits:
                failure = output[-3000:] if code else "Agent produced no changes or commits."
                if self.block_or_retry(ticket, failure):
                    continue
                return
            self.transition(ticket, "Verifying", f"Attempt {attempt}")
            failure = self.verify_qa_tests_unchanged(ticket, worktree)
            if not failure:
                failure = self.verify(ticket, worktree)
            if failure:
                if self.block_or_retry(ticket, failure):
                    continue
                return
            ticket["failure"] = ""
            try:
                self.publish(ticket, worktree)
            except Exception as exc:
                ticket["failure"] = str(exc)[-3000:]
                self.transition(ticket, "Blocked", "Publishing failed; worktree preserved")
            return

    def sync_merged(self):
        if not self.backend:
            return
        merged = []
        for ticket in self.tickets.values():
            if ticket["status"] == "In Review":
                pr = self.backend.merged_pr(ticket)
                if pr:
                    merged.append((ticket, pr))
        if not merged:
            return
        head = self.sync_default_branch()
        for ticket, pr in merged:
            merge_sha = (pr.get("mergeCommit") or {}).get("oid")
            if merge_sha:
                reachable = self.git("merge-base", "--is-ancestor", merge_sha, head, check=False)
                if reachable.returncode:
                    ticket["failure"] = f"Merged PR commit {merge_sha} is not present in {self.backend.default_branch}"
                    self.transition(ticket, "Blocked", "Merged dependency is missing from the synchronized base")
                    continue
            self.transition(ticket, "Done", "PR merged and synchronized")
            worktree = self.repo.parent / f"wt-{ticket['number']}"
            self.git("worktree", "remove", "--force", str(worktree), check=False)

    def run_loop(self):
        self.load_tickets()
        if self.args.dry_run:
            self.dry_plan(); return
        if self.backend:
            self.sync_default_branch()
        unfinished = any(ticket["status"] != "Done" for ticket in self.tickets.values())
        needs_codex = any(
            ticket["agent"] == "codex" and ticket["status"] != "Done"
            for ticket in self.tickets.values()
        ) or (self.qa_agent == "codex" and unfinished)
        if needs_codex:
            self.codex_bin = resolve_codex_cli()
            print(f"Codex adapter: {self.codex_bin}", flush=True)
        for cycle in self.detect_cycles():
            note = "Dependency cycle: " + " → ".join(f"#{n}" for n in cycle)
            for n in set(cycle[:-1]):
                self.tickets[n]["failure"] = note
                self.transition(self.tickets[n], "Blocked", note)
        while True:
            self.sync_merged()
            self.apply_qa_approvals()
            self.refresh_readiness()
            ready = [t for t in self.tickets.values() if t["status"] == "Ready"][: self.args.max_parallel]
            if ready:
                with concurrent.futures.ThreadPoolExecutor(max_workers=self.args.max_parallel) as pool:
                    list(pool.map(self.process, ready))
                continue
            unfinished = [
                t for t in self.tickets.values()
                if t["status"] not in TERMINAL | {"In Review", "QA Review"}
            ]
            waiting_qa = tuple(t["number"] for t in self.tickets.values() if t["status"] == "QA Review")
            if waiting_qa and waiting_qa != self.last_qa_wait:
                print(
                    "Waiting for Acceptance Test approval: " + ", ".join(f"#{number}" for number in waiting_qa),
                    flush=True,
                )
                self.last_qa_wait = waiting_qa
            elif unfinished and not waiting_qa:
                deadlock = tuple((t["number"], tuple(t["dependencies"])) for t in unfinished)
                if deadlock != self.last_deadlock:
                    print("Deadlock: " + ", ".join(f"#{t['number']} waits for {t['dependencies']}" for t in unfinished), flush=True)
                    self.last_deadlock = deadlock
            if self.args.mock and self.args.once:
                return
            if self.args.once:
                return
            time.sleep(max(15, int(self.cfg["factory"]["poll_interval"])))


def show_status(repo: Path):
    path = repo / ".factory/state.json"
    if not path.exists():
        raise SystemExit("No state yet. Run `factory run` first.")
    tickets = json.loads(path.read_text()).get("tickets", [])
    print(f"{'ISSUE':<7} {'STATUS':<13} {'AGENT':<8} {'QA':<8} {'TRY':<4} TITLE")
    for t in tickets:
        print(
            f"#{t['number']:<6} {t['status']:<13} {t['agent']:<8} "
            f"{(t.get('qa_agent') or '—'):<8} {t['attempt']:<4} {t['title']}"
        )


def retry_ticket(repo: Path, number: int, mock=False, project_number=None):
    store = StateStore(repo)
    for ticket in store.data.get("tickets", []):
        if ticket["number"] == number:
            if ticket["status"] != "Blocked":
                raise SystemExit(f"#{number} is {ticket['status']}, not Blocked")
            ticket.update(
                status="Ready", attempt=0, failure="", qa_attempt=0,
                qa_commit="", qa_tests={}, qa_failure="", qa_approved=False, base_sha="",
            )
            (repo / ".factory/qa-approvals" / str(number)).unlink(missing_ok=True)
            ticket.setdefault("history", []).append({"at": now(), "status": "Ready", "note": "Operator retry"})
            if not mock:
                backend = GitHubBackend(repo, project_number)
                remote = {item["number"]: item for item in backend.load()}
                if number not in remote:
                    raise SystemExit(f"Ticket #{number} was not found on GitHub")
                remote[number].update(ticket)
                backend.set_status(remote[number], "Ready", "Operator retry")
            store.save(); print(f"#{number} reset to Ready"); return
    raise SystemExit(f"Ticket #{number} not found")


def approve_qa_tests(repo: Path, number: int, assume_yes=False):
    store = StateStore(repo)
    ticket = next((item for item in store.data.get("tickets", []) if item["number"] == number), None)
    if not ticket:
        raise ValueError(f"Ticket #{number} not found in factory state")
    if ticket.get("status") != "QA Review":
        raise ValueError(f"Ticket #{number} is {ticket.get('status')}, not QA Review")
    worktree = repo.parent / f"wt-{number}"
    if not worktree.is_dir():
        raise ValueError(f"QA worktree is missing: {worktree}")
    failures = []
    for path, expected in ticket.get("qa_tests", {}).items():
        file = worktree / path
        if not file.is_file():
            failures.append(f"{path} is missing")
            continue
        actual = run(["git", "hash-object", path], worktree).stdout.strip()
        if actual != expected:
            failures.append(f"{path} changed after QA committed it")
    if failures:
        raise ValueError("; ".join(failures))
    summary = run(
        ["git", "show", "--stat", "--oneline", "--decorate", ticket["qa_commit"]],
        worktree,
    ).stdout.strip()
    print(f"\nIndependent Acceptance Tests for #{number}: {ticket['title']}\n")
    print(summary)
    print("\nProtected files:")
    for path in sorted(ticket.get("qa_tests", {})):
        print(f"- {path}")
    if not assume_yes:
        try:
            answer = input("\nApprove these tests and start implementation? Type APPROVE TESTS: ")
        except EOFError as exc:
            raise ValueError("interactive approval required; rerun in a terminal or pass --yes") from exc
        if answer != "APPROVE TESTS":
            raise ValueError("Acceptance Test approval cancelled")
    marker = repo / ".factory/qa-approvals" / str(number)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(now() + "\n")
    print(f"Approved Acceptance Tests for #{number}. The running factory will resume it automatically.")


def positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def parser():
    p = argparse.ArgumentParser(prog="factory", description="Software (re)-Factory orchestrator")
    sub = p.add_subparsers(dest="command", required=True)
    configure = sub.add_parser("configure", help="save attendee defaults for shorter commands")
    configure.add_argument("--preset", choices=sorted(PRESETS))
    configure.add_argument("--agent", help="registered implementation adapter name")
    configure.add_argument("--qa-agent", help="registered independent QA adapter name")
    configure.add_argument("--planning-agent", choices=["claude", "codex"])
    configure.add_argument(
        "--review-qa-tests", action=argparse.BooleanOptionalAction, default=None,
        help="pause for human review after QA writes acceptance tests",
    )
    configure.add_argument("--max-parallel", type=positive_int)
    configure.add_argument("--project-number", type=positive_int)
    seed = sub.add_parser("seed", help="create deterministic fallback tickets without PRD planning")
    seed.add_argument("scenario", choices=["tv", "recipe-rebrand"], nargs="?", default="recipe-rebrand")
    seed.add_argument("--repo", default=".")
    seed.add_argument("--github-repo", metavar="OWNER/REPOSITORY")
    seed.add_argument("--agent", help="registered implementation adapter name")
    seed.add_argument("--dry-run", action="store_true")
    run_p = sub.add_parser("run", help="schedule and execute tickets")
    run_p.add_argument("--repo", default="."); run_p.add_argument(
        "--agent", help="registered implementation adapter name",
    )
    run_p.add_argument("--max-parallel", type=positive_int); run_p.add_argument("--project-number", type=positive_int)
    run_p.add_argument(
        "--qa-agent",
        help="independent agent that writes protected acceptance tests before implementation",
    )
    run_p.add_argument("--no-qa", action="store_true", help="skip the independent QA phase")
    run_p.add_argument(
        "--review-qa-tests", action=argparse.BooleanOptionalAction, default=None,
        help="pause each ticket for human approval after QA commits its tests",
    )
    run_p.add_argument(
        "--scenario", choices=["tv", "recipe-rebrand"], default="tv",
        help="deterministic scenario used by --mock",
    )
    run_p.add_argument("--once", action="store_true"); run_p.add_argument("--dry-run", action="store_true")
    run_p.add_argument("--mock", action="store_true", help="use seed tickets, mock agent, and local merges")
    status = sub.add_parser("status"); status.add_argument("--repo", default=".")
    retry = sub.add_parser("retry"); retry.add_argument("issue", type=int); retry.add_argument("--repo", default=".")
    retry.add_argument("--mock", action="store_true"); retry.add_argument("--project-number", type=positive_int)
    plan = sub.add_parser("plan", help="run the Product Review expert on a PRD")
    plan.add_argument("prd"); plan.add_argument("--repo", default="."); plan.add_argument("--output")
    plan.add_argument("--default-agent", help="registered adapter written into generated tickets")
    plan.add_argument("--planning-agent", choices=["claude", "codex"])
    plan.add_argument("--min-tickets", type=int, default=3); plan.add_argument("--max-tickets", type=int, default=12)
    plan.add_argument("--mock", action="store_true", help="use bundled deterministic planning artifacts")
    review = sub.add_parser("review", help="open a human review gate for a planning run")
    review.add_argument("kind", choices=["product", "alignment"]); review.add_argument("plan")
    review.add_argument("--repo", default=".")
    approve_product_p = sub.add_parser("approve-product", help="approve product behavior and scope")
    approve_product_p.add_argument("plan"); approve_product_p.add_argument("--repo", default=".")
    approve_product_p.add_argument("--yes", action="store_true")
    continue_p = sub.add_parser("continue-plan", help="run architecture, program design, and vertical-slice experts")
    continue_p.add_argument("plan"); continue_p.add_argument("--repo", default=".")
    continue_p.add_argument("--mock", action="store_true", help="use bundled deterministic planning artifacts")
    approve = sub.add_parser("approve", help="approve alignment and publish tickets to GitHub")
    approve.add_argument("plan"); approve.add_argument("--repo", default=".")
    approve.add_argument("--project-number", type=positive_int); approve.add_argument("--yes", action="store_true")
    approve.add_argument("--new-project-title", help="create and use a fresh GitHub Project")
    approve_tests = sub.add_parser("approve-tests", help="approve protected Acceptance Tests for one ticket")
    approve_tests.add_argument("issue", type=int); approve_tests.add_argument("--repo", default=".")
    approve_tests.add_argument("--yes", action="store_true")
    doctor = sub.add_parser("doctor", help="check workshop prerequisites and safety")
    doctor.add_argument("--repo", default="."); doctor.add_argument("--full", action="store_true")
    doctor.add_argument("--agent", help="registered implementation adapter name")
    doctor.add_argument("--qa-agent", help="registered independent QA adapter name")
    doctor.add_argument("--planning-agent", choices=["claude", "codex"])
    return p


def main():
    args = parser().parse_args()
    repo = Path(getattr(args, "repo", ".")).resolve()
    try:
        session = apply_session_defaults(args, repo)
        if args.command == "configure":
            path, configured = configure_session(
                repo, args.preset, args.project_number,
                agent=args.agent, qa_agent=args.qa_agent,
                planning_agent=args.planning_agent,
                review_qa_tests=args.review_qa_tests,
                max_parallel=args.max_parallel,
            )
            print(render_session_config(configured))
            print(f"\nSaved attendee defaults: {path}")
            print("Next: ./factory/factory doctor")
        elif args.command == "seed":
            seed_backlog(repo, args)
        elif args.command == "status":
            show_status(repo)
        elif args.command == "retry":
            retry_ticket(repo, args.issue, args.mock, args.project_number)
        elif args.command == "plan":
            planner_label = "deterministic fixtures" if args.mock else args.planning_agent.title()
            print(f"Planning with {planner_label}; generated tickets will use {args.default_agent.title()}.")
            plan_prd(
                repo, Path(args.prd), args.output, args.default_agent,
                args.min_tickets, args.max_tickets,
                "mock" if args.mock else args.planning_agent,
                "mock" if args.mock else resolve_planning_cli(args.planning_agent),
                args.mock,
            )
        elif args.command == "review":
            review_plan(repo, args.kind, args.plan)
        elif args.command == "approve-product":
            approve_product(repo, args.plan, args.yes)
        elif args.command == "continue-plan":
            run_dir = resolve_run(repo, args.plan)
            planning_agent = load_manifest(run_dir).get("planning_agent", "codex")
            agent_bin = "mock" if args.mock or planning_agent == "mock" else resolve_planning_cli(planning_agent)
            continue_plan(repo, args.plan, agent_bin, args.mock)
        elif args.command == "approve":
            supplied = Path(args.plan)
            legacy = supplied.is_file() and supplied.name != "manifest.json" and not (supplied.parent / "manifest.json").is_file()
            if legacy:
                approve_plan(repo, supplied, args.project_number, args.yes, args.new_project_title)
                published = json.loads(supplied.read_text())
            else:
                publishable, run_dir = prepare_publication(repo, args.plan, args.yes)
                url = approve_plan(repo, publishable, args.project_number, True, args.new_project_title)
                mark_published(repo, run_dir, url)
                published = json.loads(publishable.read_text())
            project_number = published.get("publication", {}).get("project_number")
            if project_number:
                path = remember_project(repo, int(project_number))
                print(f"Saved Project #{project_number} for future commands in {path}.")
        elif args.command == "approve-tests":
            approve_qa_tests(repo, args.issue, args.yes)
        elif args.command == "doctor":
            raise SystemExit(
                run_doctor(
                    repo, load_config(repo), full=args.full,
                    implementation_agent=args.agent, qa_agent=args.qa_agent,
                    planning_agent=args.planning_agent,
                )
            )
        else:
            if not args.mock:
                print(render_session_config(resolved_run_config(args, session)))
                print()
            Factory(args).run_loop()
    except (RuntimeError, GitHubError, FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"factory: {exc}") from exc


if __name__ == "__main__":
    main()
