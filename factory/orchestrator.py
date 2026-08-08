#!/usr/bin/env python3
"""Software (re)-Factory: a small, visible coding-agent pipeline.

Tickets start as GitHub issues (or seed JSON in mock mode).  The scheduler
unlocks dependency-ready work, creates one Git worktree per ticket, asks an
independent QA agent to commit protected acceptance tests, runs the selected
implementation agent, verifies ordered gates, retries with the failure in the
prompt, then publishes a PR.  Mock mode follows the implementation path but
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

from github_backend import GitHubBackend, GitHubError
from planner import approve_plan, plan_prd

STATES = ["Backlog", "Ready", "In Progress", "Verifying", "In Review", "Done", "Blocked"]
ACTIVE = {"In Progress", "Verifying"}
TERMINAL = {"Done", "Blocked"}
DEFAULT_AGENTS = {
    "claude": 'claude -p "$(cat {prompt})" --permission-mode acceptEdits',
    "codex": '{codex} exec --sandbox workspace-write --ephemeral "$(cat {prompt})"',
    "cursor": 'cursor-agent -p "$(cat {prompt})"',
    "mock": "{python} factory/mock_agent.py {ticket}",
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
        raise ValueError("qa.agent must name a configured claude, codex, or cursor adapter")
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
                f"QA test {raw_path} must be named test_ticket_{ticket_number}[_topic].py "
                f"or ticket-{ticket_number}[-topic].test.js"
            )
    return errors


def parse_dependencies(body: str) -> list[int]:
    match = re.search(r"(?im)^\s*Depends-on:\s*(.+)$", body or "")
    return [int(n) for n in re.findall(r"#(\d+)", match.group(1))] if match else []


def parse_agent(body: str, default: str) -> str:
    match = re.search(r"(?im)^\s*agent:\s*(claude|codex|cursor|mock)\s*$", body or "")
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
        requested_qa = args.qa_agent or self.cfg["qa"]["agent"]
        self.qa_agent = None if args.no_qa or (args.mock and args.qa_agent is None) else requested_qa
        if self.qa_agent and (self.qa_agent not in self.cfg["agents"] or self.qa_agent == "mock"):
            raise ValueError("--qa-agent must name a configured claude, codex, or cursor adapter")
        self.python = sys.executable
        self.store = StateStore(self.repo)
        self.tickets: dict[int, dict] = {}
        self.transition_lock = threading.RLock()
        self.merge_lock = threading.Lock()
        self.last_deadlock = None
        self.codex_bin = None
        self.backend = None if args.mock else GitHubBackend(self.repo, args.project_number)

    def load_tickets(self):
        source = json.loads((self.repo / "factory/seed/tickets.json").read_text()) if self.args.mock else self.backend.load(read_only=self.args.dry_run)
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
                "qa_agent": self.qa_agent or "", "qa_attempt": old.get("qa_attempt", 0),
                "qa_commit": old.get("qa_commit", ""), "qa_tests": old.get("qa_tests", {}),
                "pr_url": raw.get("pr_url", old.get("pr_url", "")),
                "failure": old.get("failure", ""), "warnings": old.get("warnings", []),
                "history": old.get("history", []), "mock_action": raw.get("mock_action", ""),
                "simulate_merge_conflict": raw.get("simulate_merge_conflict", False),
            }
            recovered = ticket["status"] in ACTIVE
            if recovered:
                ticket["status"] = "Backlog"  # safely replay interrupted work
                ticket["history"].append({"at": now(), "status": "Backlog", "note": "Recovered after restart"})
            self.tickets[number] = ticket
            if recovered and self.backend and not self.args.dry_run:
                self.backend.set_status(ticket, "Backlog", "Recovered after restart")
        self._sync_store(save=not self.args.dry_run)

    def _sync_store(self, save=True):
        self.store.data["mode"] = "mock" if self.args.mock else "github"
        self.store.data["states"] = STATES
        self.store.data["tickets"] = sorted(self.tickets.values(), key=lambda t: t["number"])
        if save:
            self.store.save()

    def transition(self, ticket: dict, status: str, note=""):
        if status not in STATES:
            raise ValueError(status)
        with self.transition_lock:
            ticket["status"] = status
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
            if ticket["status"] in TERMINAL | {"In Review"}:
                continue
            ready_label = self.args.mock or "agent-ready" in ticket["labels"]
            deps_done = all(self.tickets.get(n, {}).get("status") == "Done" for n in ticket["dependencies"])
            wanted = "Ready" if ready_label and deps_done else "Backlog"
            if ticket["status"] != wanted:
                self.transition(ticket, wanted, "Dependencies satisfied" if wanted == "Ready" else "Waiting for dependencies")

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

    def run_adapter(self, agent: str, ticket: dict, worktree: Path, prompt: Path, log_name: str):
        template = self.cfg["agents"].get(agent)
        if not template:
            return 2, f"Unknown agent adapter: {agent}"
        command = template.format(
            prompt=shlex.quote(str(prompt)), ticket=ticket["number"],
            python=shlex.quote(self.python), codex=shlex.quote(self.codex_bin or "codex"),
        )
        log = self.repo / ".factory/logs" / log_name
        log.parent.mkdir(parents=True, exist_ok=True)
        try:
            result = run(command, worktree, timeout=self.cfg["factory"]["agent_timeout"], check=False, shell=True)
            output = result.stdout + result.stderr
            log.write_text(output)
            return result.returncode, output
        except subprocess.TimeoutExpired as exc:
            output = f"Agent timed out after {self.cfg['factory']['agent_timeout']}s\n{exc.stdout or ''}{exc.stderr or ''}"
            log.write_text(output)
            return 124, output

    def run_agent(self, ticket: dict, worktree: Path, prompt: Path):
        return self.run_adapter(
            ticket["agent"], ticket, worktree, prompt,
            f"{ticket['number']}-attempt{ticket['attempt']}.log",
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
                f"{ticket['number']}-qa-attempt{attempt}.log",
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
        return "Independent QA tests are protected:\n" + "\n".join(f"- {item}" for item in changed)

    def commit_leftovers(self, ticket: dict, worktree: Path, message: str | None = None):
        if not self.git("status", "--porcelain", cwd=worktree).stdout.strip():
            return
        self.git("add", "-A", cwd=worktree)
        self.git("commit", "-m", message or f"factory(#{ticket['number']}): complete ticket", cwd=worktree)

    def verify(self, ticket: dict, worktree: Path):
        failures, warnings = [], []
        for gate in self.cfg["gate"]:
            command = gate["cmd"].format(python=shlex.quote(self.python), repo=shlex.quote(str(self.repo)))
            try:
                result = run(command, worktree, timeout=self.cfg["factory"]["gate_timeout"], check=False, shell=True)
                output = (result.stdout + result.stderr)[-3000:]
            except subprocess.TimeoutExpired:
                result = type("TimedOut", (), {"returncode": 124})()
                output = f"{gate['name']} timed out after {self.cfg['factory']['gate_timeout']}s"
            if result.returncode:
                message = f"[{gate['name']}] exit {result.returncode}\n{output}"
                (failures if gate.get("required", True) else warnings).append(message)
        ticket["warnings"] = warnings
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
        first_phase = f"Running QA {self.qa_agent}" if self.qa_agent else f"Running {ticket['agent']}"
        self.transition(ticket, "In Progress", first_phase)
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
        for ticket in self.tickets.values():
            if ticket["status"] == "In Review" and self.backend.is_merged(ticket):
                self.transition(ticket, "Done", "PR merged")
                worktree = self.repo.parent / f"wt-{ticket['number']}"
                self.git("worktree", "remove", "--force", str(worktree), check=False)

    def run_loop(self):
        self.load_tickets()
        if self.args.dry_run:
            self.dry_plan(); return
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
            self.refresh_readiness()
            ready = [t for t in self.tickets.values() if t["status"] == "Ready"][: self.args.max_parallel]
            if ready:
                with concurrent.futures.ThreadPoolExecutor(max_workers=self.args.max_parallel) as pool:
                    list(pool.map(self.process, ready))
                continue
            unfinished = [t for t in self.tickets.values() if t["status"] not in TERMINAL | {"In Review"}]
            if unfinished:
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
                qa_commit="", qa_tests={}, qa_failure="",
            )
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


def parser():
    p = argparse.ArgumentParser(prog="factory", description="Software (re)-Factory orchestrator")
    sub = p.add_subparsers(dest="command", required=True)
    run_p = sub.add_parser("run", help="schedule and execute tickets")
    run_p.add_argument("--repo", default="."); run_p.add_argument("--agent", choices=DEFAULT_AGENTS, default="codex")
    run_p.add_argument("--max-parallel", type=int, default=4); run_p.add_argument("--project-number", type=int)
    run_p.add_argument(
        "--qa-agent", choices=["claude", "codex", "cursor"],
        help="independent agent that writes protected acceptance tests before implementation",
    )
    run_p.add_argument("--no-qa", action="store_true", help="skip the independent QA phase")
    run_p.add_argument("--once", action="store_true"); run_p.add_argument("--dry-run", action="store_true")
    run_p.add_argument("--mock", action="store_true", help="use seed tickets, mock agent, and local merges")
    status = sub.add_parser("status"); status.add_argument("--repo", default=".")
    retry = sub.add_parser("retry"); retry.add_argument("issue", type=int); retry.add_argument("--repo", default=".")
    retry.add_argument("--mock", action="store_true"); retry.add_argument("--project-number", type=int)
    plan = sub.add_parser("plan", help="turn a PRD into an editable ticket plan")
    plan.add_argument("prd"); plan.add_argument("--repo", default="."); plan.add_argument("--output")
    plan.add_argument("--default-agent", choices=["claude", "codex", "cursor"], default="codex")
    plan.add_argument("--min-tickets", type=int, default=3); plan.add_argument("--max-tickets", type=int, default=12)
    approve = sub.add_parser("approve", help="review and publish a ticket plan to GitHub")
    approve.add_argument("plan"); approve.add_argument("--repo", default=".")
    approve.add_argument("--project-number", type=int); approve.add_argument("--yes", action="store_true")
    return p


def main():
    args = parser().parse_args()
    repo = Path(args.repo).resolve()
    try:
        if args.command == "status":
            show_status(repo)
        elif args.command == "retry":
            retry_ticket(repo, args.issue, args.mock, args.project_number)
        elif args.command == "plan":
            plan_prd(
                repo, Path(args.prd), args.output, args.default_agent,
                args.min_tickets, args.max_tickets, resolve_codex_cli(),
            )
        elif args.command == "approve":
            approve_plan(repo, Path(args.plan), args.project_number, args.yes)
        else:
            Factory(args).run_loop()
    except (RuntimeError, GitHubError, FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"factory: {exc}") from exc


if __name__ == "__main__":
    main()
