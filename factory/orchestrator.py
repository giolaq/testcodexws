#!/usr/bin/env python3
"""Software (re)-Factory: a small, visible coding-agent pipeline.

Tickets start as GitHub issues (or seed JSON in a Rehearsal Run). The scheduler
unlocks dependency-ready work, creates one Git worktree per ticket, asks an
independent QA agent to commit protected acceptance tests, runs the selected
implementation agent, verifies ordered gates, retries with the failure in the
prompt, then publishes a PR. A Rehearsal Run (`--mock`) follows the implementation path but
skips real QA by default and merges locally.
Every transition is mirrored to .factory/state.json for the Control Center and
read-only dashboard.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import fnmatch
import hashlib
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
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from doctor import run_doctor
from acceptance_evidence import classify_focused_result, focused_test_command
from adapter_capabilities import load_capabilities
from evidence_packet import create_canvas, export_evidence
from factory_charter import CHARTER_PATH, FactoryCharter, FactoryCharterError
from factory_contracts import (
    WORKSHOP_VERSION,
    handoff_receipt,
    profile as factory_profile,
    render_profiles,
    role_input,
    write_handoff_receipt,
)
from release_check import render_release_check
from github_backend import GitHubBackend, GitHubError
from github_repository import (
    checkout_github_repository,
    connect_github_repository,
    parse_github_repository,
)
from planner import approve_plan
from planning_pipeline import (
    approve_rehearsal,
    approve_product,
    continue_plan,
    load_manifest,
    mark_published,
    plan_prd,
    prepare_publication,
    revise_plan,
    resolve_run,
    review as review_plan,
)
from project_contract import ProjectContract, ProjectContractError
from triage import GATE_ORDER, classify_controls, triage_ticket
from run_summary import factory_run_summary, render_factory_run_summary
from monitor import FactoryMonitor
from session_config import (
    FACTORY_PROFILES,
    PRESETS,
    configure_session,
    load_session_config,
    remember_project,
    render_session_config,
)
from supervisor import AgentSupervisor
from code_review import (
    CodeReviewError,
    extract_review,
    render_review_comment,
    validate_review,
)

STATES = ["Backlog", "Ready", "In Progress", "QA Review", "Verifying", "In Review", "Done", "Blocked"]
ACTIVE = {"In Progress", "Verifying"}
TERMINAL = {"Done", "Blocked"}
DEFAULT_AGENTS = {
    "claude": 'claude -p "$(cat {prompt})" --permission-mode acceptEdits',
    "codex": '{codex} exec --sandbox workspace-write --ephemeral "$(cat {prompt})"',
    "cursor": 'cursor-agent -p "$(cat {prompt})"',
    "mock": "{python} {factory_dir}/mock_agent.py {ticket} --scenario {scenario} --attempt {attempt}",
    "mock-qa": "{python} {factory_dir}/mock_qa_agent.py {ticket} --scenario {scenario}",
    "mock-supervisor": "{python} {factory_dir}/mock_supervisor.py {prompt}",
    "mock-review": "{python} {factory_dir}/mock_review_agent.py {ticket} {prompt} --attempt {attempt}",
}
DEFAULT_QA = {
    "agent": "codex",
    "max_retries": 1,
    "test_roots": ["tests"],
    "test_file_patterns": [
        "test_ticket_{ticket}*.py", "ticket-{ticket}*.test.js",
        "ticket-{ticket}*.test.ts", "ticket-{ticket}*.test.tsx",
    ],
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def worktree_path(repo: Path, ticket_number: int) -> Path:
    """Return a sibling path scoped to this repository.

    A generic ``../wt-4`` collides as soon as two workshop repositories run the
    same Ticket number. Including the repository name keeps each run isolated
    while leaving worktrees easy to find and inspect beside the checkout.
    """
    return repo.parent / f"{repo.name}-wt-{ticket_number}"


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
    project = ProjectContract.load(repo)
    cfg = {
        "factory": {"max_retries": 2, "poll_interval": 20, "agent_timeout": 900, "gate_timeout": 300},
        "agents": DEFAULT_AGENTS.copy(),
        "supervisor": {"agent": "codex"},
        "review": {"agent": "codex"},
        "qa": {**DEFAULT_QA, "test_roots": DEFAULT_QA["test_roots"].copy()},
        "gate": list(project.gates),
    }
    path = repo / "factory" / "factory.toml"
    if not path.is_file():
        path = Path(__file__).with_name("factory.toml")
    if path.exists():
        supplied = tomllib.loads(path.read_text())
        cfg["factory"].update(supplied.get("factory", {}))
        cfg["agents"].update(supplied.get("agents", {}))
        cfg["supervisor"].update(supplied.get("supervisor", {}))
        cfg["review"].update(supplied.get("review", {}))
        cfg["qa"].update(supplied.get("qa", {}))
        raw_capabilities = supplied.get("agent_capabilities", {})
    else:
        raw_capabilities = {}
    cfg["qa"]["test_roots"] = list(project.test_roots)
    cfg["qa"]["test_file_patterns"] = list(project.test_file_patterns)
    cfg["gate"] = list(project.gates)
    cfg["project"] = project
    cfg["agent_capabilities"] = load_capabilities(raw_capabilities, cfg["agents"])
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
    patterns = qa.get("test_file_patterns", DEFAULT_QA["test_file_patterns"])
    if not isinstance(patterns, list) or not patterns or not all(
        isinstance(pattern, str) and "{ticket}" in pattern and "/" not in pattern
        for pattern in patterns
    ):
        raise ValueError("qa.test_file_patterns must contain filename patterns with {ticket}")


def validate_qa_changes(
    changes: list[tuple[str, str]], ticket_number: int,
    test_roots: list[str], test_file_patterns: list[str] | None = None,
) -> list[str]:
    """Return policy failures for the files produced by an independent QA agent."""
    if not changes:
        return ["QA agent did not create an acceptance-test file"]
    errors = []
    roots = [root.strip("/") + "/" for root in test_roots]
    patterns = test_file_patterns or DEFAULT_QA["test_file_patterns"]
    rendered_patterns = [pattern.format(ticket=ticket_number) for pattern in patterns]
    for status, raw_path in changes:
        path = PurePosixPath(raw_path).as_posix().removeprefix("./")
        if status != "A":
            errors.append(f"QA may only add new test files, but {raw_path} has Git status {status}")
            continue
        if not any(path.startswith(root) for root in roots):
            errors.append(f"QA changed {raw_path}, which is outside the configured test roots")
            continue
        name = PurePosixPath(path).name
        if not any(fnmatch.fnmatchcase(name, pattern) for pattern in rendered_patterns):
            errors.append(
                f"Acceptance Test {raw_path} must match one configured filename pattern: "
                + ", ".join(rendered_patterns)
            )
    return errors


def validate_protected_changes(
    changed_paths: list[str],
    protected_paths: tuple[str, ...],
    charter_never_modify: tuple[str, ...] = (),
) -> list[str]:
    """Return repository-policy failures for paths an agent must never change."""
    errors = []
    protected = (*protected_paths, "factory.project.toml")
    for raw_path in changed_paths:
        path = PurePosixPath(raw_path).as_posix().removeprefix("./")
        charter_match = next((
            root.rstrip("/") for root in charter_never_modify
            if path == root.rstrip("/") or path.startswith(root.rstrip("/") + "/")
        ), None)
        if charter_match:
            errors.append(f"{raw_path} is protected by the Factory Charter never-modify policy")
            continue
        for root in protected:
            root = root.rstrip("/")
            if path == root or path.startswith(root + "/"):
                errors.append(f"{raw_path} is protected by the Project Contract")
                break
    return errors


def parse_dependencies(body: str) -> list[int]:
    match = re.search(r"(?im)^\s*Depends-on:\s*(.+)$", body or "")
    return [int(n) for n in re.findall(r"#(\d+)", match.group(1))] if match else []


def parse_agent(body: str, default: str) -> str:
    match = re.search(r"(?im)^\s*agent:\s*([a-z][a-z0-9_-]{0,31})\s*$", body or "")
    return match.group(1).lower() if match else default


def parse_plan_id(body: str) -> str:
    match = re.search(r"factory-plan:([a-zA-Z0-9_-]+):", body or "")
    return match.group(1) if match else ""


def parse_ticket_governance(body: str) -> dict:
    """Read the immutable planning controls published with a Ticket."""
    marker = re.search(
        r"<!--\s*factory-governance:v(?P<schema>\d+);"
        r"profile=(?P<profile>[a-z][a-z0-9-]{0,31});"
        r"charter=(?P<charter>[a-f0-9]{64});"
        r"merge=(?P<merge>human|supervisor)\s*-->",
        body or "",
    )
    if marker:
        return {
            "schema_version": int(marker.group("schema")),
            "profile": marker.group("profile"),
            "charter_sha256": marker.group("charter"),
            "merge_authority": marker.group("merge"),
        }
    if "factory-governance:" in (body or ""):
        raise ValueError(
            "Ticket contains an invalid factory-governance marker; republish it from "
            "an approved Planning Run."
        )
    return {}


def slugify(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:42] or "ticket"


def role_verdict(role: str, output: str) -> str:
    matches = list(re.finditer(
        r"(?im)^FACTORY_ROLE_VERDICT:\s*(PASS|BLOCK)(?::\s*(.+))?\s*$",
        output,
    ))
    display = role.replace("_", " ").title()
    if not matches:
        return f"{display} did not return a structured FACTORY_ROLE_VERDICT"
    result = matches[-1]
    if result.group(1).upper() == "PASS":
        return ""
    reason = (result.group(2) or "no reason supplied").strip()
    return f"{display} blocked: {reason}"


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
        args.profile = args.profile or session.get("profile", "standard")
        if args.mock:
            args.agent = args.agent or "codex"
            args.review_qa_tests = bool(args.review_qa_tests)
            args.max_parallel = args.max_parallel or 4
        else:
            args.agent = args.agent or session.get("agent", "codex")
            args.qa_agent = args.qa_agent or session.get("qa_agent")
            args.supervisor_agent = args.supervisor_agent or session.get("supervisor_agent")
            args.review_agent = args.review_agent or session.get("review_agent")
            if args.review_qa_tests is None:
                args.review_qa_tests = session.get("review_qa_tests", False)
            args.max_parallel = args.max_parallel or session.get("max_parallel", 1)
            args.project_number = args.project_number or session.get("project_number")
    elif args.command == "plan":
        args.profile = args.profile or session.get("profile", "standard")
        args.default_agent = args.default_agent or session.get("agent", "codex")
        args.planning_agent = args.planning_agent or session.get("planning_agent", "codex")
    elif args.command == "approve":
        if args.project_number is None and not args.new_project_title:
            args.project_number = session.get("project_number")
    elif args.command in {"retry", "merge"}:
        args.project_number = args.project_number or session.get("project_number")
    elif args.command == "seed":
        args.agent = args.agent or session.get("agent", "codex")
        if args.github_repo is None and session.get("github_repository"):
            args.github_repo = parse_github_repository(session["github_repository"]).slug
    elif args.command == "doctor":
        args.agent = args.agent or session.get("agent", "codex")
        args.qa_agent = args.qa_agent or session.get("qa_agent")
        args.supervisor_agent = args.supervisor_agent or session.get("supervisor_agent")
        args.review_agent = args.review_agent or session.get("review_agent")
        args.planning_agent = args.planning_agent or session.get("planning_agent", "codex")
    return session


def resolved_run_config(args, session: dict) -> dict:
    qa_agent = "disabled" if args.no_qa else (
        args.qa_agent or load_config(Path(args.repo).resolve())["qa"]["agent"]
    )
    profile = factory_profile(args.profile)
    supervisor_agent = "disabled"
    if "supervisor" in profile["execution_roles"]:
        supervisor_agent = (
            args.supervisor_agent
            or load_config(Path(args.repo).resolve())["supervisor"]["agent"]
        )
    review_agent = "disabled"
    if "code_review" in profile["execution_roles"]:
        review_agent = (
            args.review_agent
            or load_config(Path(args.repo).resolve())["review"]["agent"]
        )
    return {
        **session,
        "profile": args.profile,
        "agent": args.agent,
        "qa_agent": qa_agent,
        "supervisor_agent": supervisor_agent,
        "review_agent": review_agent,
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
    seed_script = repo / "factory/seed_github.py"
    if not seed_script.is_file():
        seed_script = Path(__file__).with_name("seed_github.py")
    command = [
        sys.executable, str(seed_script),
        "--repo", str(repo), "--agent", args.agent, "--scenario", args.scenario,
    ]
    if args.github_repo:
        command.extend(["--github-repo", args.github_repo])
    if args.dry_run:
        command.append("--dry-run")
    result = subprocess.run(command, cwd=repo)
    if result.returncode:
        raise RuntimeError("deterministic ticket seeding failed")


def recover_remote_ticket_state(raw: dict, summary: dict | None) -> dict:
    """Reconstruct durable execution state from GitHub without local runtime files."""
    summary = summary if isinstance(summary, dict) else {}
    revisions = summary.get("revisions") if isinstance(summary.get("revisions"), dict) else {}
    verdicts = summary.get("verdicts") if isinstance(summary.get("verdicts"), dict) else {}
    decisions = summary.get("human_decisions") if isinstance(summary.get("human_decisions"), dict) else {}
    metrics = summary.get("metrics") if isinstance(summary.get("metrics"), dict) else {}
    pull_request = raw.get("pull_request") if isinstance(raw.get("pull_request"), dict) else {}
    approved_head = str(revisions.get("approved_head") or "")
    pr_head = str(pull_request.get("headRefOid") or "")
    review_decision = str(verdicts.get("code_review") or "")
    status = str(raw.get("status") or summary.get("status") or "Backlog")
    failure = ""
    next_action = ""

    if pull_request.get("mergedAt"):
        status = "Done"
        next_action = "none"
    elif pull_request and str(pull_request.get("state") or "").upper() == "CLOSED":
        status = "Blocked"
        failure = "The remote pull request was closed without merging; inspect it before retrying."
        next_action = "inspect_closed_pull_request"
    elif pull_request and review_decision == "APPROVE" and approved_head:
        if pr_head and pr_head != approved_head:
            status = "Blocked"
            failure = (
                "Pull request head changed after the remote approval; rerun code review "
                "for the current exact revision."
            )
            next_action = "rerun_code_review"
        else:
            status = "In Review"
            next_action = "merge_exact_revision"
    elif pull_request:
        status = "Blocked"
        failure = "A remote pull request exists without a recoverable exact-revision approval."
        next_action = "retry_ticket"

    qa_evidence = {
        name: {"result": verdicts.get(name, ""), "recovered": True}
        for name in ("red", "green", "negative")
        if verdicts.get(name)
    }
    code_review = None
    if review_decision:
        code_review = {
            "candidate_sha": approved_head,
            "recovered": True,
            "result": {"decision": review_decision},
        }
    merge_commit = pull_request.get("mergeCommit") or {}
    merge_commit_sha = merge_commit.get("oid", "") if isinstance(merge_commit, dict) else ""
    return {
        "status": status,
        "failure": failure,
        "next_human_action": next_action,
        "pr_url": raw.get("pr_url") or pull_request.get("url", ""),
        "pr_state": pull_request.get("state", ""),
        "pr_head": pr_head,
        "pr_merged_at": pull_request.get("mergedAt") or "",
        "pr_merge_commit": merge_commit_sha,
        "branch": pull_request.get("headRefName", ""),
        "base_sha": revisions.get("base", ""),
        "qa_commit": revisions.get("qa", ""),
        "approved_head": approved_head,
        "qa_evidence": qa_evidence,
        "qa_approved": bool(decisions.get("qa_approved")),
        "code_review": code_review,
        "gate_results": summary.get("gates", []) if isinstance(summary.get("gates"), list) else [],
        "attempt": int(metrics.get("attempts") or 0),
        "qa_attempt": int(metrics.get("qa_attempts") or 0),
        "metrics": {
            key: metrics[key]
            for key in (
                "stage_seconds", "agent_seconds", "gate_seconds", "human_wait_seconds",
                "retry_count", "verifier_rejections",
            )
            if key in metrics
        },
        "merge_executed_by": decisions.get("merge_executed_by", ""),
        "recovered_run_id": summary.get("run_id", ""),
        "remote_run_summary": {
            "recovered": bool(summary),
            "run_id": summary.get("run_id", ""),
            "schema_version": summary.get("schema_version"),
        },
    }


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
        self.project = self.cfg["project"]
        self.capabilities = self.cfg["agent_capabilities"]
        self.project_context = self.project.context()
        self.profile_name = getattr(args, "profile", None) or "standard"
        self.profile = factory_profile(self.profile_name)
        self.charter = FactoryCharter.load(self.repo, require_approved=True)
        self.charter_context = self.charter.context()
        self.governance = self.charter.governance(
            self.profile_name,
            explicit_autonomy=bool(getattr(args, "allow_autonomous_merge", False)),
        )
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
        if "qa" not in self.profile["execution_roles"]:
            self.qa_agent = None
        elif args.no_qa:
            raise ValueError(
                f"Factory Profile {self.profile['name']} requires independent QA; "
                "select the Lean profile instead of --no-qa"
            )
        if self.qa_agent and (
            self.qa_agent not in self.cfg["agents"]
            or self.qa_agent == "mock"
            or (self.qa_agent == "mock-qa" and not args.mock)
        ):
            raise ValueError("--qa-agent must name a configured non-mock adapter")
        requested_supervisor = getattr(args, "supervisor_agent", None) or self.cfg["supervisor"]["agent"]
        if "supervisor" not in self.profile["execution_roles"]:
            self.supervisor_agent = None
        else:
            self.supervisor_agent = "mock-supervisor" if args.mock else requested_supervisor
        if self.supervisor_agent and (
            self.supervisor_agent not in self.cfg["agents"]
            or self.supervisor_agent in {"mock", "mock-qa"}
            or (self.supervisor_agent == "mock-supervisor" and not args.mock)
        ):
            raise ValueError("--supervisor-agent must name a configured non-mock adapter")
        requested_review = getattr(args, "review_agent", None) or self.cfg["review"]["agent"]
        if "code_review" not in self.profile["execution_roles"]:
            self.review_agent = None
        else:
            self.review_agent = "mock-review" if args.mock else requested_review
        if self.review_agent and (
            self.review_agent not in self.cfg["agents"]
            or self.review_agent in {"mock", "mock-qa", "mock-supervisor"}
            or (self.review_agent == "mock-review" and not args.mock)
        ):
            raise ValueError("--review-agent must name a configured non-mock adapter")
        self.review_qa_tests = bool(args.review_qa_tests or self.cfg["qa"].get("require_human_approval", False))
        self.python = sys.executable
        self.store = StateStore(self.repo)
        self.run_id = self.store.data.get("run_id") or uuid.uuid4().hex[:12]
        existing_tickets = self.store.data.get("tickets", [])
        if existing_tickets:
            recorded_governance = self.store.data.get("governance")
            if not isinstance(recorded_governance, dict):
                raise ValueError(
                    "Existing Factory Run predates Charter governance. Reset the local run, "
                    "then execute the approved Tickets again."
                )
            governed_fields = (
                "schema_version", "profile", "charter_sha256", "merge_authority",
            )
            drift = [
                field for field in governed_fields
                if recorded_governance.get(field) != self.governance.get(field)
            ]
            if drift:
                raise ValueError(
                    "Factory Run governance changed after execution began ("
                    + ", ".join(drift)
                    + "). Review the new Charter, reset the local run, and execute again."
                )
            if self.profile["protected_acceptance_tests"]:
                legacy_qa = [
                    ticket.get("number", "?")
                    for ticket in existing_tickets
                    if ticket.get("qa_commit")
                    and ticket.get("qa_evidence", {}).get("red", {}).get("result") != "RED PROVED"
                ]
                if legacy_qa:
                    rendered = ", ".join(f"#{number}" for number in legacy_qa)
                    raise ValueError(
                        "Existing Factory Run predates causal Acceptance Test evidence for "
                        f"{rendered}. Reset the local run and execute these Tickets again so "
                        "QA can prove RED before implementation."
                    )
        self.tickets: dict[int, dict] = {}
        self.transition_lock = threading.RLock()
        self.merge_lock = threading.Lock()
        self.last_deadlock = None
        self.last_qa_wait = None
        self.codex_bin = None
        self.supervisor = None
        self.backend = None if args.mock else GitHubBackend(self.repo, args.project_number)

    def load_tickets(self):
        rehearsal_plan_id = ""
        if self.args.mock:
            scenario_path = self.repo / "factory/scenarios" / self.args.scenario / "tickets.json"
            if not scenario_path.is_file():
                scenario_path = Path(__file__).with_name("scenarios") / self.args.scenario / "tickets.json"
            latest_plan = self.repo / ".factory/plans/latest.json"
            if latest_plan.is_file():
                try:
                    rehearsal_plan_id = json.loads(latest_plan.read_text()).get("plan_id", "")
                except json.JSONDecodeError:
                    pass
            approved_path = self.repo / ".factory/rehearsal" / rehearsal_plan_id / "tickets.json"
            source_path = (
                approved_path
                if rehearsal_plan_id and approved_path.is_file()
                else scenario_path if scenario_path.is_file()
                else self.repo / "factory/seed/tickets.json"
            )
            source = json.loads(source_path.read_text())
        else:
            source = self.backend.load(read_only=self.args.dry_run)
            if not self.args.dry_run and self.backend.project_number:
                remember_project(self.repo, self.backend.project_number)
        previous = {t["number"]: t for t in self.store.data.get("tickets", [])}
        for raw in source:
            number = int(raw["number"])
            old = previous.get(number, {})
            remote_claim = old.get("remote_claim", {})
            if self.backend:
                remote_claim = self.backend.read_claim(number) or remote_claim
            remote_state = recover_remote_ticket_state(
                raw,
                raw.get("remote_run_summary") if self.backend else None,
            )
            ticket_plan_id = parse_plan_id(raw.get("body", ""))
            ticket_governance = parse_ticket_governance(raw.get("body", ""))
            governed_ticket_required = bool(ticket_plan_id) and (
                not self.args.mock or bool(rehearsal_plan_id)
            )
            if governed_ticket_required and not ticket_governance:
                raise ValueError(
                    f"Ticket #{number} predates governed Tickets. Re-approve and republish "
                    "the Planning Run so every Ticket records its profile and Charter hash."
                )
            if ticket_governance:
                governed_fields = (
                    "schema_version", "profile", "charter_sha256", "merge_authority",
                )
                drift = [
                    field for field in governed_fields
                    if ticket_governance.get(field) != self.governance.get(field)
                ]
                if drift:
                    raise ValueError(
                        f"Ticket #{number} governance does not match this Factory Run: "
                        + ", ".join(drift)
                    )
            ticket = {
                "number": number, "title": raw["title"], "body": raw.get("body", ""),
                "labels": raw.get("labels", []), "status": raw.get("status", old.get("status", "Backlog")),
                "agent": parse_agent(raw.get("body", ""), "mock" if self.args.mock else self.args.agent),
                "dependencies": parse_dependencies(raw.get("body", "")),
                "attempt": old.get("attempt", 0), "branch": old.get("branch", ""),
                "base_sha": old.get("base_sha", ""),
                "qa_agent": self.qa_agent or "", "qa_attempt": old.get("qa_attempt", 0),
                "qa_commit": old.get("qa_commit", ""), "qa_tests": old.get("qa_tests", {}),
                "qa_evidence": old.get("qa_evidence", {}),
                "qa_approved": old.get("qa_approved", False),
                "existing_test_policy": old.get("existing_test_policy", self.charter.existing_tests),
                "existing_tests": old.get("existing_tests", {}),
                "existing_test_changes": old.get("existing_test_changes", []),
                "pr_url": raw.get("pr_url", old.get("pr_url", "")),
                "pr_state": old.get("pr_state", ""),
                "pr_head": old.get("pr_head", ""),
                "pr_merged_at": old.get("pr_merged_at", ""),
                "pr_merge_commit": old.get("pr_merge_commit", ""),
                "issue_url": raw.get("url", old.get("issue_url", "")),
                "failure": old.get("failure", ""), "warnings": old.get("warnings", []),
                "gate_results": old.get("gate_results", []),
                "changed_files": old.get("changed_files", []),
                "current_prompt": old.get("current_prompt", ""),
                "current_log": old.get("current_log", ""),
                "phase": old.get("phase", ""),
                "plan_id": (
                    ticket_plan_id
                    or rehearsal_plan_id
                    or old.get("plan_id", "")
                ),
                "planned": bool(ticket_plan_id) or self.args.mock,
                "triage": old.get("triage", {}),
                "governance": ticket_governance or self.governance,
                "receipts": old.get("receipts", []),
                "supervisor_instruction": old.get("supervisor_instruction", ""),
                "supervisor_decision": old.get("supervisor_decision", ""),
                "review_agent": self.review_agent or "",
                "code_review": old.get("code_review"),
                "merge_authority": old.get("merge_authority", self.governance["merge_authority"]),
                "approved_head": old.get("approved_head", ""),
                "merge_executed_by": old.get("merge_executed_by", ""),
                "remote_claim": remote_claim,
                "metrics": old.get("metrics", {}),
                "remote_run_summary": old.get("remote_run_summary", {}),
                "recovered_run_id": old.get("recovered_run_id", ""),
                "next_human_action": old.get("next_human_action", ""),
                "supervisor_merge_decision": old.get("supervisor_merge_decision", ""),
                "supervisor_merge_action": old.get("supervisor_merge_action", ""),
                "history": old.get("history", []), "mock_action": raw.get("mock_action", ""),
                "simulate_merge_conflict": raw.get("simulate_merge_conflict", False),
            }
            if self.backend and not old and (
                raw.get("remote_run_summary") or raw.get("pull_request")
            ):
                ticket.update(remote_state)
            foreign_claim = bool(
                remote_claim
                and remote_claim.get("run_id")
                and remote_claim.get("run_id") != self.run_id
            )
            if foreign_claim and ticket["status"] not in {"In Review", "Done"}:
                owner = remote_claim.get("run_id")
                ticket["status"] = "Blocked"
                ticket["phase"] = "claim"
                ticket["failure"] = (
                    f"Remote Ticket claim belongs to Factory run {owner}. "
                    "Resume that run or explicitly release the confirmed abandoned claim."
                )
                ticket["next_human_action"] = "release_or_resume_claim"
            if ticket["agent"] not in self.cfg["agents"]:
                raise ValueError(
                    f"Ticket #{number} requests unregistered agent {ticket['agent']!r}; "
                    "add it to factory/factory.toml [agents] or edit the ticket"
                )
            recovered = ticket["status"] in ACTIVE and not foreign_claim and bool(old)
            if recovered:
                ticket["status"] = "Backlog"  # safely replay interrupted work
                ticket.update(
                    qa_approved=False,
                    qa_commit="",
                    qa_tests={},
                    qa_evidence={},
                    existing_tests={},
                    existing_test_changes=[],
                    base_sha="",
                )
                ticket["history"].append({"at": now(), "status": "Backlog", "note": "Recovered after restart"})
            self.tickets[number] = ticket
            if recovered and self.backend and not self.args.dry_run:
                self.backend.set_status(ticket, "Backlog", "Recovered after restart")
        self._sync_store(save=not self.args.dry_run)

    def _sync_store(self, save=True):
        self.store.data["mode"] = "mock" if self.args.mock else "github"
        self.store.data["run_id"] = self.run_id
        self.store.data["schema_version"] = 2
        self.store.data["profile"] = self.profile_name
        self.store.data["governance"] = self.governance
        self.store.data["execution_roles"] = self.profile["execution_roles"]
        run_policy = role_input(self.repo, "implementation")
        self.store.data["policy"] = {
            "version": run_policy["policy_version"],
            "hashes": run_policy["policy_hashes"],
        }
        self.store.data["scenario"] = self.args.scenario
        self.store.data["qa_review_required"] = self.review_qa_tests
        self.store.data["supervisor_agent"] = self.supervisor_agent or "disabled"
        self.store.data["review_agent"] = self.review_agent or "disabled"
        self.store.data["states"] = STATES
        self.store.data["tickets"] = sorted(self.tickets.values(), key=lambda t: t["number"])
        attention = self.human_attention_snapshot()
        self.store.data["human_attention"] = attention
        metrics = self.store.data.setdefault("metrics", {})
        metrics["peak_review_queue"] = max(
            metrics.get("peak_review_queue", 0), attention["awaiting_review"],
        )
        if save:
            self.store.save()

    def record_receipt(
        self,
        ticket: dict,
        role: str,
        phase: str,
        *,
        attempt: int,
        input_revisions: dict[str, str],
        output_revisions: dict[str, str],
        claimed_result: str,
        verification: list[str],
        unresolved_risks: list[str] | None = None,
        artifacts: list[str] | None = None,
        evidence: dict | None = None,
    ) -> str:
        contract = role_input(self.repo, role)
        receipt = handoff_receipt(
            run_id=ticket.get("plan_id") or f"{'rehearsal' if self.args.mock else 'live'}-{self.args.scenario}",
            role=role,
            phase=phase,
            ticket=ticket["number"],
            attempt=max(1, attempt),
            input_revisions=input_revisions,
            output_revisions=output_revisions,
            claimed_result=claimed_result,
            verification=verification,
            unresolved_risks=unresolved_risks or [],
            artifacts=artifacts or [],
            policy_hashes=contract["policy_hashes"],
            evidence=evidence or {},
        )
        path = write_handoff_receipt(self.repo, receipt)
        reference = os.path.relpath(path.resolve(), self.repo.resolve())
        ticket.setdefault("receipts", []).append(reference)
        self._sync_store()
        return reference

    def transition(self, ticket: dict, status: str, note=""):
        if status not in STATES:
            raise ValueError(status)
        with self.transition_lock:
            previous_status = ticket.get("status", "")
            previous_at = ticket.get("history", [{}])[-1].get("at", "") if ticket.get("history") else ""
            elapsed = 0.0
            if previous_at:
                try:
                    parsed = datetime.fromisoformat(previous_at.replace("Z", "+00:00"))
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    elapsed = max(0.0, (datetime.now(timezone.utc) - parsed).total_seconds())
                except ValueError:
                    pass
            metrics = ticket.setdefault("metrics", {
                "stage_seconds": {}, "agent_seconds": 0.0, "gate_seconds": 0.0,
                "human_wait_seconds": 0.0, "retry_count": 0, "verifier_rejections": 0,
            })
            metrics.setdefault("stage_seconds", {})
            metrics.setdefault("agent_seconds", 0.0)
            metrics.setdefault("gate_seconds", 0.0)
            metrics.setdefault("human_wait_seconds", 0.0)
            metrics.setdefault("retry_count", 0)
            metrics.setdefault("verifier_rejections", 0)
            if elapsed:
                key = previous_status or "unknown"
                metrics["stage_seconds"][key] = round(
                    metrics["stage_seconds"].get(key, 0) + elapsed, 2,
                )
                if previous_status == "In Progress":
                    metrics["agent_seconds"] = round(metrics.get("agent_seconds", 0) + elapsed, 2)
                elif previous_status == "Verifying":
                    metrics["gate_seconds"] = round(metrics.get("gate_seconds", 0) + elapsed, 2)
                elif previous_status in {"QA Review", "In Review"}:
                    metrics["human_wait_seconds"] = round(metrics.get("human_wait_seconds", 0) + elapsed, 2)
            ticket["status"] = status
            if status not in {"In Progress", "Blocked"}:
                ticket["phase"] = status.lower().replace(" ", "-")
            elif status == "Blocked" and not ticket.get("phase"):
                ticket["phase"] = "build"
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

    def human_attention_snapshot(self) -> dict:
        """Return the bounded human-decision queue that controls dispatch."""
        awaiting = [
            ticket for ticket in self.tickets.values()
            if ticket.get("status") in {"QA Review", "In Review"}
        ]
        human_words = ("human", "decision", "clarif", "approval", "answer", "scope")
        blocked = [
            ticket for ticket in self.tickets.values()
            if ticket.get("status") == "Blocked" and (
                ticket.get("blocking_questions")
                or any(word in ticket.get("failure", "").lower() for word in human_words)
            )
        ]

        def waiting_since(ticket: dict) -> str:
            current = ticket.get("status")
            events = [
                event.get("at", "") for event in ticket.get("history", [])
                if event.get("status") == current and event.get("at")
            ]
            return events[-1] if events else ticket.get("finished_at") or ticket.get("started_at") or ""

        decisions = []
        current_time = datetime.now(timezone.utc)
        for ticket in awaiting + blocked:
            since = waiting_since(ticket)
            age_hours = 0.0
            if since:
                try:
                    parsed = datetime.fromisoformat(since.replace("Z", "+00:00"))
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    age_hours = max(0.0, (current_time - parsed).total_seconds() / 3600)
                except ValueError:
                    pass
            decisions.append({
                "ticket": ticket.get("number"),
                "status": ticket.get("status"),
                "waiting_since": since,
                "age_hours": round(age_hours, 2),
            })
        decisions.sort(key=lambda item: item["waiting_since"] or "9999")
        review_limit = self.charter.max_awaiting_human_review
        blocked_limit = self.charter.max_blocked_for_human
        oldest_limit = self.charter.oldest_review_hours
        reason = ""
        if len(awaiting) >= review_limit:
            reason = f"human review queue {len(awaiting)} / limit {review_limit}"
        elif len(blocked) >= blocked_limit:
            reason = f"human-blocked queue {len(blocked)} / limit {blocked_limit}"
        elif decisions and decisions[0]["age_hours"] >= oldest_limit:
            reason = (
                f"oldest human decision has waited {decisions[0]['age_hours']:.1f}h "
                f"/ limit {oldest_limit}h"
            )
        return {
            "dispatch_paused": bool(reason),
            "reason": reason,
            "awaiting_review": len(awaiting),
            "review_limit": review_limit,
            "blocked_for_human": len(blocked),
            "blocked_limit": blocked_limit,
            "oldest_review_hours": oldest_limit,
            "oldest": decisions[0] if decisions else None,
            "decisions": decisions,
        }

    def refresh_readiness(self):
        for ticket in self.tickets.values():
            if ticket["status"] in TERMINAL | {"In Review", "QA Review"}:
                continue
            ready_label = self.args.mock or "agent-ready" in ticket["labels"]
            deps_done = all(self.tickets.get(n, {}).get("status") == "Done" for n in ticket["dependencies"])
            ticket["triage"] = triage_ticket(
                ticket.get("body", ""),
                dependencies_ready=deps_done,
                planned=bool(ticket.get("planned")),
                profile=self.profile_name,
                charter=self.charter,
            )
            triage_result = ticket["triage"]["result"]
            if triage_result == "NEEDS_INFORMATION":
                ticket["failure"] = ticket["triage"]["reason"]
                ticket["blocking_questions"] = [ticket["triage"]["reason"]]
                self.transition(ticket, "Blocked", "Triage needs human information")
                continue
            wanted = (
                "Ready"
                if ready_label and triage_result == "READY_TO_IMPLEMENT"
                else "Backlog"
            )
            if ticket["status"] != wanted:
                note = (
                    "Triage: READY_TO_IMPLEMENT"
                    if wanted == "Ready" else f"Triage: {triage_result} — {ticket['triage']['reason']}"
                )
                self.transition(ticket, wanted, note)

    def apply_qa_approvals(self):
        approval_dir = self.repo / ".factory/qa-approvals"
        for ticket in self.tickets.values():
            marker = approval_dir / str(ticket["number"])
            if ticket["status"] != "QA Review" or not marker.is_file():
                continue
            worktree = worktree_path(self.repo, ticket["number"])
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
        worktree = worktree_path(self.repo, ticket["number"])
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

    def supervisor_context(self, ticket: dict) -> str:
        instruction = ticket.get("supervisor_instruction", "").strip()
        if not instruction:
            return ""
        decision = ticket.get("supervisor_decision", "supervisor")
        return (
            "\n## Supervisor coordination\n"
            f"Decision `{decision}`: {instruction}\n\n"
            "This instruction coordinates delivery only. The approved Ticket, role contract, "
            "project policy, protected tests, and human gates remain authoritative. Your observed "
            "result, verification, and unresolved risks will be returned to the supervisor through "
            "a Handoff Receipt.\n"
        )

    def charter_prompt_context(self) -> str:
        context = getattr(self, "charter_context", None)
        if context is None:
            context = FactoryCharter.load(
                self.repo, require_approved=True,
            ).context()
        return f"## Approved Factory Charter\n```json\n{context}\n```\n"

    def make_prompt(self, ticket: dict, failure: str) -> Path:
        path = self.repo / ".factory/prompts" / f"{ticket['number']}-attempt{ticket['attempt']}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        gates = "\n".join(f"- {g['name']}: `{g['cmd']}`" for g in self.cfg["gate"])
        retry = f"\n## Previous failure\n```\n{failure[-3000:]}\n```\n" if failure else ""
        protected = ""
        contract = role_input(self.repo, "implementation")["text"]
        supervisor = self.supervisor_context(ticket)
        if ticket.get("qa_tests"):
            paths = "\n".join(f"- `{path}`" for path in sorted(ticket["qa_tests"]))
            focused = ticket.get("qa_evidence", {}).get("focused_test_command", "")
            focused_instruction = (
                f"The factory proved these tests red before implementation. Run the identical "
                f"accepted command until it is green: `{focused}`\n"
                if focused else ""
            )
            protected = (
                "\n## Independent QA acceptance tests\n"
                f"The {ticket['qa_agent']} QA agent created and committed these protected tests:\n{paths}\n\n"
                f"{focused_instruction}"
                "Make the implementation pass them. You may add other tests, but do not edit, "
                "rename, delete, skip, or weaken the protected tests; the factory verifies their Git hashes.\n"
            )
        path.write_text(
            f"# Ticket #{ticket['number']}: {ticket['title']}\n\n{ticket['body']}\n\n"
            f"## Repository Project Contract and inventory\n```json\n{self.project_context}\n```\n\n"
            f"{self.charter_prompt_context()}\n"
            f"## Verification gates\n{gates}\n{protected}\nCommit as `factory(#{ticket['number']}): <summary>`.\n"
            "Work only in the current worktree. Do not change ticket scope.\n" + supervisor + "\n" + contract + retry
        )
        return path

    def make_qa_prompt(self, ticket: dict, failure: str) -> Path:
        attempt = ticket["qa_attempt"]
        path = self.repo / ".factory/prompts" / f"{ticket['number']}-qa-attempt{attempt}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        roots = "\n".join(f"- `{root}/`" for root in self.cfg["qa"]["test_roots"])
        patterns = "\n".join(
            f"- `{pattern.format(ticket=ticket['number'])}`"
            for pattern in self.cfg["qa"]["test_file_patterns"]
        )
        gates = "\n".join(f"- {g['name']}: `{g['cmd']}`" for g in self.cfg["gate"])
        retry = f"\n## Previous QA failure\n```\n{failure[-3000:]}\n```\n" if failure else ""
        contract = role_input(self.repo, "qa")["text"]
        supervisor = self.supervisor_context(ticket)
        path.write_text(
            f"# QA assignment for ticket #{ticket['number']}: {ticket['title']}\n\n{ticket['body']}\n\n"
            f"## Repository Project Contract and inventory\n```json\n{self.project_context}\n```\n\n"
            f"{self.charter_prompt_context()}\n"
            "## Role\n"
            "Act as the independent QA engineer before implementation begins. Translate the ticket's "
            "acceptance criteria into deterministic executable acceptance tests. Inspect production code "
            "only to understand public behavior; do not implement or repair the feature.\n\n"
            "## Test-file contract\n"
            "- Add at least one new test file. Do not edit, rename, or delete an existing file.\n"
            f"- New test filenames must match one of the configured patterns:\n{patterns}\n"
            f"- Add files only below these roots:\n{roots}\n"
            "- Cover each automatable acceptance criterion, including failure and boundary cases.\n"
            "- Use the repository's existing test tools and fixtures; keep tests offline and deterministic.\n"
            "- Include at least one assertion that detects behavior missing at the assigned base revision. "
            "The factory runs the exact new files before implementation and accepts red evidence only "
            "for a behavior assertion failure. Already-passing, skipped, uncollectable, timed-out, or "
            "infrastructure-broken tests are rejected.\n"
            "- Do not skip tests, soften assertions, change production files, or commit; the factory commits "
            "the accepted QA files separately.\n\n"
            f"## Later verification gates\n{gates}\n" + supervisor + "\n" + contract + retry
        )
        return path

    def make_role_prompt(self, ticket: dict, role: str, failure: str = "") -> Path:
        path = self.repo / ".factory/prompts" / f"{ticket['number']}-{role}-attempt{ticket['attempt']}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        retry = f"\n## Previous role failure\n```\n{failure[-3000:]}\n```\n" if failure else ""
        supervisor = self.supervisor_context(ticket)
        path.write_text(
            f"# {role.replace('_', ' ').title()} for Ticket #{ticket['number']}: {ticket['title']}\n\n"
            f"{ticket['body']}\n\n## Repository Project Contract and inventory\n"
            f"```json\n{self.project_context}\n```\n{self.charter_prompt_context()}\n" + supervisor + f"\n{role_input(self.repo, role)['text']}\n"
            "Work only within this Ticket handoff. The orchestrator owns lifecycle state.\n\n"
            "End the response with exactly one structured verdict line:\n"
            "`FACTORY_ROLE_VERDICT: PASS` or `FACTORY_ROLE_VERDICT: BLOCK: <reason>`.\n"
            + retry
        )
        return path

    def make_code_review_prompt(
        self, ticket: dict, base_sha: str, head_sha: str, changed_paths: list[str],
        pull_request: str,
    ) -> Path:
        path = self.repo / ".factory/prompts" / f"{ticket['number']}-code-review-attempt{ticket['attempt']}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        gates = "\n".join(
            f"- {gate['name']}: {'PASS' if gate['exit_code'] == 0 else 'FAIL'} "
            f"({'required' if gate['required'] else 'advisory'})"
            for gate in ticket.get("gate_results", [])
        ) or "- No gate evidence recorded."
        changed = "\n".join(f"- `{item}`" for item in changed_paths)
        path.write_text(
            f"# Code Review for Ticket #{ticket['number']}: {ticket['title']}\n\n"
            "Review the exact candidate diff in this worktree. Use "
            f"`git diff {base_sha}..{head_sha}` and inspect relevant surrounding code.\n\n"
            f"## Ticket\n\n<ticket>\n{ticket['body']}\n</ticket>\n\n"
            f"## Candidate revisions\n\n- Base: `{base_sha}`\n- Head: `{head_sha}`\n\n"
            f"## Pull request\n\n{pull_request}\n\n"
            f"## Changed paths\n\n{changed}\n\n"
            f"## Recorded gates\n\n{gates}\n\n"
            "## Repository Project Contract and inventory\n\n```json\n"
            f"{getattr(self, 'project_context', ProjectContract.load(self.repo).context())}\n```\n\n"
            f"{self.charter_prompt_context()}\n"
            f"{role_input(self.repo, 'code_review')['text']}\n"
            "Review for correctness, regressions, security, maintainability, and test quality. "
            "Report only actionable comments in changed paths. If there is any comment, return "
            "REQUEST_CHANGES so the implementation agent fixes every comment. Return APPROVE only "
            "when there are no comments. Do not modify files, commit, or merge. The orchestrator "
            "submits your decision to the pull request.\n\n"
            "Return one JSON object with exactly this shape and no Markdown fence:\n"
            '{"schema_version":2,"decision":"APPROVE|REQUEST_CHANGES","summary":"...",'
            '"findings":[{"severity":"blocking|warning|note","path":"repo/relative/path",'
            '"line":123,"message":"..."}]}\n'
        )
        return path

    def run_code_review(
        self, ticket: dict, worktree: Path, base_sha: str, pull_request: str,
    ) -> str:
        """Run the configured read-only reviewer against the exact PR candidate."""
        head_sha = self.git("rev-parse", "HEAD", cwd=worktree).stdout.strip()
        changed_paths = sorted(filter(None, self.git(
            "diff", "--name-only", f"{base_sha}..{head_sha}", cwd=worktree,
        ).stdout.splitlines()))
        before_status = self.git("status", "--porcelain", cwd=worktree).stdout
        prompt = self.make_code_review_prompt(
            ticket, base_sha, head_sha, changed_paths, pull_request,
        )
        code, output = self.run_adapter(
            self.review_agent,
            ticket,
            worktree,
            prompt,
            f"{ticket['number']}-code-review-attempt{ticket['attempt']}.log",
            "code-review",
        )
        failure = ""
        review = None
        try:
            if code:
                raise CodeReviewError(f"Code Review Agent exited with code {code}; inspect its log.")
            review = validate_review(extract_review(output), set(changed_paths))
            after_head = self.git("rev-parse", "HEAD", cwd=worktree).stdout.strip()
            after_status = self.git("status", "--porcelain", cwd=worktree).stdout
            if after_head != head_sha or after_status != before_status:
                raise CodeReviewError("Read-only Code Review Agent modified the worktree.")
            protected_failure = self.verify_qa_tests_unchanged(ticket, worktree)
            if protected_failure:
                raise CodeReviewError(protected_failure)
            if review["decision"] == "REQUEST_CHANGES":
                details = "; ".join(
                    f"{item['path']}{':' + str(item['line']) if item['line'] else ''}: {item['message']}"
                    for item in review["findings"]
                )
                failure = f"Code Review requested changes: {review['summary']} {details}".strip()
        except (CodeReviewError, ValueError) as exc:
            failure = str(exc)

        artifact = self.repo / ".factory/reviews" / f"ticket-{ticket['number']}-attempt-{ticket['attempt']}.json"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        reference = str(artifact.relative_to(self.repo))
        record = {
            "schema_version": 1,
            "status": (
                "approved" if review and review["decision"] == "APPROVE" and not failure
                else "changes_requested" if review and review["decision"] == "REQUEST_CHANGES"
                else "invalid"
            ),
            "agent": self.review_agent,
            "attempt": ticket["attempt"],
            "base": base_sha,
            "head": head_sha,
            "pull_request": pull_request,
            "prompt": str(prompt.relative_to(self.repo)),
            "log": ticket.get("current_log", ""),
            "artifact": reference,
            "result": review,
            "failure": failure,
            "created_at": now(),
        }
        temp = artifact.with_suffix(".tmp")
        temp.write_text(json.dumps(record, indent=2) + "\n")
        os.replace(temp, artifact)
        ticket["code_review"] = record
        self.record_receipt(
            ticket,
            "code_review",
            "Review",
            attempt=ticket["attempt"],
            input_revisions={"candidate_base": base_sha, "candidate_head": head_sha},
            output_revisions={
                "reviewed_commit": head_sha,
                "pull_request": pull_request,
                "decision": review.get("decision", "") if review else "",
            },
            claimed_result="Code review approved" if not failure else "Code review requested changes",
            verification=[
                "Structured review schema validated.",
                "Worktree commit and status checked for read-only conformance.",
                "Findings constrained to candidate changed paths.",
            ],
            unresolved_risks=[failure] if failure else [
                item["message"] for item in (review or {}).get("findings", [])
            ],
            artifacts=[reference, str(prompt.relative_to(self.repo)), ticket.get("current_log", "")],
        )
        return failure

    def coordinate_ready(self, candidates: list[dict]) -> list[dict]:
        attention = self.human_attention_snapshot()
        self.store.data["human_attention"] = attention
        if attention["dispatch_paused"]:
            self.store.save()
            print(f"Dispatch paused: {attention['reason']}", flush=True)
            return []
        if not self.supervisor:
            return candidates[: self.args.max_parallel]
        decision = self.supervisor.coordinate(list(self.tickets.values()), self.args.max_parallel)
        sequence = int(decision["id"].rsplit("-", 1)[-1])
        selected = []
        for command in decision["block"]:
            ticket = self.tickets[command["ticket"]]
            ticket["failure"] = "Supervisor blocked dispatch: " + command["reason"]
            self.record_receipt(
                ticket,
                "supervisor",
                "Build",
                attempt=sequence,
                input_revisions={"state_sha256": decision["input_hash"]},
                output_revisions={"decision": decision["id"]},
                claimed_result="Supervisor blocked Ticket dispatch",
                verification=[command["reason"]],
                unresolved_risks=[command["reason"]],
                artifacts=[decision["prompt"], decision["log"]],
            )
            self.transition(ticket, "Blocked", f"Supervisor: {command['reason']}"[:180])
        for command in decision["dispatch"]:
            ticket = self.tickets[command["ticket"]]
            ticket["supervisor_instruction"] = command["instruction"]
            ticket["supervisor_decision"] = decision["id"]
            ticket["history"].append({
                "at": now(),
                "status": "Ready",
                "note": f"{decision['id']} dispatched Ticket: {command['instruction']}",
            })
            self.record_receipt(
                ticket,
                "supervisor",
                "Build",
                attempt=sequence,
                input_revisions={"state_sha256": decision["input_hash"]},
                output_revisions={"decision": decision["id"]},
                claimed_result="Supervisor dispatched Ticket",
                verification=[command["instruction"]],
                artifacts=[decision["prompt"], decision["log"]],
            )
            selected.append(ticket)
        self._sync_store()
        dispatched = ", ".join(f"#{ticket['number']}" for ticket in selected) or "none"
        deferred = ", ".join(f"#{number}" for number in decision["deferred"]) or "none"
        print(f"Supervisor {decision['id']}: dispatch {dispatched}; deferred {deferred}. {decision['summary']}", flush=True)
        return selected

    def run_profile_role(
        self,
        ticket: dict,
        worktree: Path,
        role: str,
        input_commit: str,
        *,
        read_only: bool,
        failure_context: str = "",
    ) -> str:
        before_head = self.git("rev-parse", "HEAD", cwd=worktree).stdout.strip()
        before_status = self.git("status", "--porcelain", cwd=worktree).stdout
        if read_only and before_status:
            return (
                f"Read-only Agent Role {role} requires a clean worktree; "
                "resolve the existing candidate changes before retrying"
            )
        prompt = self.make_role_prompt(ticket, role, failure_context)
        code, output = self.run_adapter(
            ticket["agent"],
            ticket,
            worktree,
            prompt,
            f"{ticket['number']}-{role}-attempt{ticket['attempt']}.log",
            role,
        )
        failure = output[-3000:] if code else role_verdict(role, output)
        if read_only:
            after_head = self.git("rev-parse", "HEAD", cwd=worktree).stdout.strip()
            after_status = self.git("status", "--porcelain", cwd=worktree).stdout
            if after_head != before_head or after_status != before_status:
                failure = f"Read-only Agent Role {role} modified the worktree"
                self.git("reset", "--hard", before_head, cwd=worktree)
                self.git("clean", "-fd", cwd=worktree)
                restored_head = self.git("rev-parse", "HEAD", cwd=worktree).stdout.strip()
                restored_status = self.git("status", "--porcelain", cwd=worktree).stdout
                if restored_head != before_head or restored_status != before_status:
                    failure += "; the isolated worktree could not be restored and must be reset"
        else:
            try:
                self.commit_leftovers(
                    ticket,
                    worktree,
                    f"factory(#{ticket['number']}): {role.replace('_', ' ')}",
                )
            except Exception as exc:
                failure = str(exc)[-3000:]
            after_head = self.git("rev-parse", "HEAD", cwd=worktree).stdout.strip()
        protected_failure = self.verify_qa_tests_unchanged(ticket, worktree)
        if protected_failure:
            failure = protected_failure
        phase = "Verify" if read_only else "Build"
        verification_summary = [
            f"Agent adapter exit code: {code}.",
            "Protected Acceptance Test hashes checked.",
        ]
        if read_only:
            verification_summary.append("Worktree commit and status were checked for read-only conformance.")
        self.record_receipt(
            ticket,
            role,
            phase,
            attempt=ticket["attempt"],
            input_revisions={"input_commit": input_commit},
            output_revisions={"output_commit": after_head} if not failure else {},
            claimed_result=f"{role.replace('_', ' ').title()} passed" if not failure else f"{role.replace('_', ' ').title()} blocked",
            verification=verification_summary,
            unresolved_risks=(
                [f"{role.replace('_', ' ').title()} did not complete; inspect the referenced role log."]
                if failure else []
            ),
            artifacts=[os.path.relpath(prompt, self.repo)],
        )
        return failure

    def run_assured_roles(self, ticket: dict, worktree: Path, input_commit: str) -> str:
        current = input_commit
        for role, read_only in (
            ("cleanup", False),
            ("architecture_conformance", True),
            ("hardening", False),
        ):
            failure = self.run_profile_role(
                ticket,
                worktree,
                role,
                current,
                read_only=read_only,
            )
            if failure:
                return failure
            current = self.git("rev-parse", "HEAD", cwd=worktree).stdout.strip()
        return ""

    def run_final_verifier(self, ticket: dict, worktree: Path, input_commit: str) -> str:
        failure = self.run_profile_role(
            ticket,
            worktree,
            "final_verifier",
            input_commit,
            read_only=True,
        )
        if not failure:
            return ""
        correction = self.run_profile_role(
            ticket,
            worktree,
            "hardening",
            input_commit,
            read_only=False,
            failure_context=failure,
        )
        if correction:
            return correction
        corrected_head = self.git("rev-parse", "HEAD", cwd=worktree).stdout.strip()
        gate_failure = self.verify_qa_tests_unchanged(ticket, worktree) or self.verify(ticket, worktree)
        verification = [
            f"{gate['name']}: exit {gate['exit_code']} ({'required' if gate['required'] else 'advisory'})"
            for gate in ticket.get("gate_results", [])
        ]
        self.record_receipt(
            ticket,
            "verification",
            "Verify",
            attempt=ticket["attempt"],
            input_revisions={"hardening_commit": corrected_head},
            output_revisions={"verified_commit": corrected_head} if not gate_failure else {},
            claimed_result="Post-hardening verification passed" if not gate_failure else "Post-hardening verification failed",
            verification=verification or ["Protected Acceptance Test hashes checked."],
            unresolved_risks=(
                ["Required verification did not pass after hardening; inspect gate results in factory state."]
                if gate_failure else []
            ),
            artifacts=sorted(ticket.get("qa_tests", {})),
        )
        if gate_failure:
            return gate_failure
        return self.run_profile_role(
            ticket,
            worktree,
            "final_verifier",
            corrected_head,
            read_only=True,
        )

    def run_adapter(
        self, agent: str, ticket: dict, worktree: Path, prompt: Path, log_name: str,
        phase: str,
    ):
        capability = self.capabilities[agent]
        if "worktree" not in capability.allowed_working_roots:
            return 2, (
                f"Adapter {agent} does not allow the isolated Ticket worktree as a working root"
            )
        read_only_role = phase in {
            "architecture_conformance", "final_verifier", "critic", "code-review",
        }
        template = (
            capability.read_only_template
            if read_only_role and capability.read_only_template
            else self.cfg["agents"].get(agent)
        )
        if not template:
            return 2, f"Unknown agent adapter: {agent}"
        if read_only_role and not capability.supports_read_only:
            ticket.setdefault("warnings", []).append(
                f"Adapter {agent} cannot enforce read-only execution; worktree mutation detection remains active."
            )
        command = template.format(
            prompt=shlex.quote(str(prompt)), ticket=ticket["number"],
            python=shlex.quote(self.python), codex=shlex.quote(self.codex_bin or "codex"),
            scenario=shlex.quote(self.args.scenario),
            attempt=max(1, ticket.get("attempt", ticket.get("qa_attempt", 1))),
            repo=shlex.quote(str(self.repo)), worktree=shlex.quote(str(worktree)),
            factory_dir=shlex.quote(str(Path(__file__).parent)),
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
                env=self.adapter_environment(agent),
            )
            stdout = process.stdout
            assert stdout is not None

            def copy_output():
                try:
                    for chunk in iter(stdout.readline, ""):
                        chunks.append(chunk)
                        stream.write(chunk)
                        stream.flush()
                except (OSError, ValueError):
                    pass

            reader = threading.Thread(target=copy_output, daemon=True)
            reader.start()
            try:
                returncode = process.wait(timeout=self.adapter_timeout(agent))
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                returncode = 124
                timeout_message = f"Agent timed out after {self.cfg['factory']['agent_timeout']}s\n"
                chunks.append(timeout_message); stream.write(timeout_message); stream.flush()
            reader.join(timeout=5)
            stdout.close()
            if reader.is_alive():
                reader.join(timeout=1)
        output = "".join(chunks)
        ticket.update(last_agent_exit=returncode, phase_finished_at=now())
        self._sync_store()
        return returncode, output

    def adapter_timeout(self, agent: str | None = None) -> int | None:
        """Use an adapter-declared timeout, with a deterministic rehearsal fallback."""
        if agent and agent in getattr(self, "capabilities", {}):
            timeout = self.capabilities[agent].timeout_seconds
            if timeout is not None:
                return timeout
        return self.cfg["factory"]["agent_timeout"] if self.args.mock else None

    def adapter_environment(self, agent: str) -> dict[str, str]:
        """Pass only the environment names declared for this Agent Adapter."""
        capability = self.capabilities[agent]
        allowed = set(capability.environment_allowlist) | set(capability.credential_names)
        return {name: value for name, value in os.environ.items() if name in allowed}

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

    def snapshot_existing_tests(
        self, ticket: dict, worktree: Path, base_sha: str,
    ) -> None:
        """Bind pre-existing test hashes to the Ticket's Charter policy."""
        policy = self.charter.existing_tests
        ticket["existing_test_policy"] = policy
        if policy == "allow":
            ticket["existing_tests"] = {}
            self._sync_store()
            return
        listing = self.git(
            "ls-tree", "-r", "--name-only", base_sha, "--",
            *self.project.test_roots,
            cwd=worktree,
        ).stdout.splitlines()
        ticket["existing_tests"] = {
            path: self.git("rev-parse", f"{base_sha}:{path}", cwd=worktree).stdout.strip()
            for path in sorted(listing)
            if path
        }
        self._sync_store()

    def verify_existing_tests(self, ticket: dict, worktree: Path) -> str:
        policy = ticket.get("existing_test_policy", self.charter.existing_tests)
        changed = []
        for path, expected_hash in ticket.get("existing_tests", {}).items():
            file = worktree / path
            if not file.is_file():
                changed.append(f"{path} was deleted")
                continue
            actual_hash = self.git("hash-object", path, cwd=worktree).stdout.strip()
            if actual_hash != expected_hash:
                changed.append(f"{path} was modified")
        ticket["existing_test_changes"] = changed
        self._sync_store()
        if not changed or policy in {"allow", "review"}:
            return ""
        return "Existing tests are protected by the Factory Charter:\n" + "\n".join(
            f"- {item}" for item in changed
        )

    @staticmethod
    def _command_sha256(command: str) -> str:
        return hashlib.sha256(command.encode()).hexdigest()

    def run_focused_acceptance(
        self, ticket: dict, worktree: Path, *, expected: str,
    ) -> str:
        """Record causal red or green proof for the exact accepted QA command."""
        evidence = ticket.setdefault("qa_evidence", {})
        if expected == "red":
            try:
                command = focused_test_command(sorted(ticket.get("qa_tests", {})), self.python)
            except ValueError as exc:
                evidence["red"] = {
                    "result": "RED NOT PROVED",
                    "classification": "misconfigured",
                    "exit_code": None,
                    "output": str(exc)[:3000],
                }
                self._sync_store()
                return f"Causal Acceptance Test evidence is misconfigured: {exc}"
            evidence.update({
                "focused_test_command": command,
                "focused_test_command_sha256": self._command_sha256(command),
                "expected_failure_classification": "behavior_assertion",
                "test_revision": ticket.get("qa_commit", ""),
            })
        elif expected == "green":
            command = evidence.get("focused_test_command", "")
            accepted_hash = evidence.get("focused_test_command_sha256", "")
            if not command or self._command_sha256(command) != accepted_hash:
                return "Accepted focused Acceptance Test command is missing or changed."
        else:
            raise ValueError("focused Acceptance Test expectation must be red or green")

        started = time.monotonic()
        try:
            result = run(
                command,
                worktree,
                timeout=self.cfg["factory"]["gate_timeout"],
                check=False,
                shell=True,
            )
            exit_code = result.returncode
            output = (result.stdout + result.stderr)[-3000:]
        except subprocess.TimeoutExpired as exc:
            exit_code = 124
            partial = (exc.stdout or "") + (exc.stderr or "")
            output = (str(partial) + f"\nTimed out after {self.cfg['factory']['gate_timeout']}s")[-3000:]
        classification = classify_focused_result(exit_code, output)
        proved = (
            classification == "behavior_assertion"
            if expected == "red"
            else classification == "pass"
        )
        label = f"{expected.upper()} {'PROVED' if proved else 'NOT PROVED'}"
        evidence[expected] = {
            "result": label,
            "classification": classification,
            "exit_code": exit_code,
            "output": output,
            "revision": (
                ticket.get("qa_commit", "")
                if expected == "red"
                else self.git("rev-parse", "HEAD", cwd=worktree).stdout.strip()
            ),
            "duration_seconds": round(time.monotonic() - started, 2),
        }
        self._sync_store()
        if proved:
            return ""
        reasons = {
            "pass": "focused test already passes before implementation",
            "skipped": "focused test was skipped instead of proving behavior",
            "collection_error": "focused test did not collect; fix imports, dependencies, or syntax",
            "command_error": "focused test command could not run",
            "timeout": "focused test command timed out",
            "unrelated_failure": "focused test failed for an unrelated or unclassified reason",
            "behavior_assertion": "focused test still reports the missing behavior after implementation",
        }
        return "Causal Acceptance Test evidence failed: " + reasons.get(
            classification, f"unexpected {classification} result",
        ) + "."

    def run_negative_proof(
        self, ticket: dict, worktree: Path, candidate_head: str,
    ) -> str:
        """Prove an Assured test fails when candidate production changes vanish."""
        evidence = ticket.setdefault("qa_evidence", {})
        command = evidence.get("focused_test_command", "")
        command_hash = evidence.get("focused_test_command_sha256", "")
        qa_commit = ticket.get("qa_commit", "")
        if (
            evidence.get("green", {}).get("result") != "GREEN PROVED"
            or not command
            or self._command_sha256(command) != command_hash
            or not qa_commit
        ):
            return "Negative proof requires intact RED and GREEN focused Acceptance Test evidence."
        changes = self.git(
            "diff", "--name-status", "--no-renames", qa_commit, candidate_head,
            cwd=worktree,
        ).stdout.splitlines()
        changed_paths = []
        statuses = []
        for line in changes:
            fields = line.split("\t")
            if len(fields) < 2:
                continue
            status, path = fields[0], fields[-1]
            in_test_root = any(
                path == root or path.startswith(root.rstrip("/") + "/")
                for root in self.project.test_roots
            )
            if not in_test_root:
                statuses.append((status, path))
                changed_paths.append(path)
        if not changed_paths:
            return "Negative proof found no non-test candidate changes to reverse."

        original_head = self.git("rev-parse", "HEAD", cwd=worktree).stdout.strip()
        original_status = self.git("status", "--porcelain", cwd=worktree).stdout
        classification = "internal_error"
        exit_code = None
        output = ""
        added = False
        with tempfile.TemporaryDirectory(prefix=f"factory-negative-{ticket['number']}-") as directory:
            disposable = Path(directory) / "worktree"
            try:
                self.git("worktree", "add", "--detach", str(disposable), candidate_head)
                added = True
                for status, path in statuses:
                    target = disposable / path
                    if status.startswith("A"):
                        target.unlink(missing_ok=True)
                    else:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        self.git("checkout", qa_commit, "--", path, cwd=disposable)
                try:
                    result = run(
                        command,
                        disposable,
                        timeout=self.cfg["factory"]["gate_timeout"],
                        check=False,
                        shell=True,
                    )
                    exit_code = result.returncode
                    output = (result.stdout + result.stderr)[-3000:]
                except subprocess.TimeoutExpired as exc:
                    exit_code = 124
                    output = (
                        str((exc.stdout or "") + (exc.stderr or ""))
                        + f"\nTimed out after {self.cfg['factory']['gate_timeout']}s"
                    )[-3000:]
                classification = classify_focused_result(exit_code, output)
            except Exception as exc:
                output = str(exc)[-3000:]
            finally:
                if added:
                    self.git("worktree", "remove", "--force", str(disposable), check=False)
                    self.git("worktree", "prune", check=False)

        restored = (
            self.git("rev-parse", "HEAD", cwd=worktree).stdout.strip() == original_head
            and self.git("status", "--porcelain", cwd=worktree).stdout == original_status
        )
        proved = classification == "behavior_assertion" and restored
        negative = {
            "result": "NEGATIVE PROOF PROVED" if proved else "NEGATIVE PROOF NOT PROVED",
            "classification": classification,
            "exit_code": exit_code,
            "output": output,
            "candidate_revision": candidate_head,
            "qa_revision": qa_commit,
            "reversed_paths": sorted(changed_paths),
            "focused_test_command_sha256": command_hash,
            "candidate_restored": restored,
        }
        evidence["negative"] = negative
        self._sync_store()
        failure = "" if proved else (
            "Negative proof did not reproduce the expected behavior assertion failure"
            if restored else "Negative proof could not prove the candidate worktree was restored"
        )
        self.record_receipt(
            ticket,
            "negative_proof",
            "Verify",
            attempt=ticket.get("attempt", 1),
            input_revisions={
                "qa_commit": qa_commit,
                "candidate_commit": candidate_head,
            },
            output_revisions={"negative_proof_for": candidate_head} if proved else {},
            claimed_result=negative["result"],
            verification=[
                "Candidate worktree remained unchanged.",
                f"Focused command classification: {classification}.",
            ],
            unresolved_risks=[failure] if failure else [],
            artifacts=sorted(ticket.get("qa_tests", {})),
            evidence=negative,
        )
        return failure

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
                    self.cfg["qa"]["test_file_patterns"],
                )
                if not policy_errors:
                    self.commit_leftovers(
                        ticket, worktree,
                        f"test(#{ticket['number']}): add independent acceptance tests",
                    )
                    self.snapshot_qa_tests(ticket, worktree, [path for _, path in changes])
                    causal_failure = self.run_focused_acceptance(
                        ticket, worktree, expected="red",
                    )
                    if causal_failure:
                        failure = causal_failure
                    else:
                        self.record_receipt(
                            ticket,
                            "qa",
                            "Build",
                            attempt=attempt,
                            input_revisions={"base_commit": base_sha},
                            output_revisions={"qa_commit": ticket["qa_commit"]},
                            claimed_result="RED PROVED",
                            verification=[
                                "The exact focused Acceptance Test command failed on a behavior assertion before implementation.",
                            ],
                            artifacts=sorted(ticket["qa_tests"]),
                            evidence=ticket["qa_evidence"],
                        )
                        return ""
                else:
                    failure = "\n".join(policy_errors)
            ticket["qa_failure"] = failure[-3000:]
            ticket["failure"] = "QA acceptance-test phase failed:\n" + ticket["qa_failure"]
            self.record_receipt(
                ticket,
                "qa",
                "Build",
                attempt=attempt,
                input_revisions={"base_commit": base_sha},
                output_revisions={},
                claimed_result="Acceptance Test creation failed",
                verification=["QA adapter and file policy did not produce an acceptable handoff."],
                unresolved_risks=["QA handoff failed; inspect the referenced QA log."],
                artifacts=[ticket.get("current_log", "")],
                evidence=ticket.get("qa_evidence", {}),
            )
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

    def verify_project_protected_paths(self, worktree: Path, base_sha: str) -> str:
        changed = self.git(
            "diff", "--no-renames", "--name-only", base_sha, "HEAD", cwd=worktree,
        ).stdout.splitlines()
        errors = validate_protected_changes(
            changed,
            self.project.protected_paths,
            self.charter.never_modify,
        )
        if not errors:
            return ""
        return "Protected repository policy paths were changed:\n" + "\n".join(
            f"- {item}" for item in errors
        )

    def commit_leftovers(self, ticket: dict, worktree: Path, message: str | None = None):
        if not self.git("status", "--porcelain", cwd=worktree).stdout.strip():
            return
        self.git("add", "-A", cwd=worktree)
        self.git("commit", "-m", message or f"factory(#{ticket['number']}): complete ticket", cwd=worktree)

    def verify(self, ticket: dict, worktree: Path):
        failures, warnings, gate_results = [], [], []
        selected_level = (
            ticket.get("triage", {}).get("controls", {}).get("gate_level")
            or self.charter.gate_level
        )
        selected_rank = GATE_ORDER[selected_level]
        selected_gates = [
            gate for gate in self.cfg["gate"]
            if GATE_ORDER[gate.get("level", "full")] <= selected_rank
        ]
        if not any(gate.get("required", True) for gate in selected_gates):
            failures.append(
                f"MISCONFIGURED: verification level {selected_level} has no required gate. "
                "Add one to factory.project.toml."
            )
        if selected_level == "deep" and not any(
            gate.get("level") == "deep" for gate in selected_gates
        ):
            failures.append(
                "MISCONFIGURED: deep verification was selected but factory.project.toml "
                "declares no deep gate."
            )
        verification_started = time.monotonic()
        for gate in selected_gates:
            command = self.project.render_command(gate["cmd"], python=self.python)
            started = time.monotonic()
            try:
                result = run(command, worktree, timeout=self.cfg["factory"]["gate_timeout"], check=False, shell=True)
                output = (result.stdout + result.stderr)[-3000:]
            except subprocess.TimeoutExpired:
                result = type("TimedOut", (), {"returncode": 124})()
                output = f"{gate['name']} timed out after {self.cfg['factory']['gate_timeout']}s"
            skipped = result.returncode == 0 and bool(
                re.search(r"(?im)\b[1-9]\d*\s+skipped\b", output)
                or re.search(r"(?im)(?:#|ℹ)\s*skipped\s+[1-9]\d*\b", output)
                or re.search(r"(?im)\b(required tool unavailable|not installed)\b", output)
            )
            classification = (
                "MISCONFIGURED" if skipped else "PASS" if result.returncode == 0 else "FAIL"
            )
            gate_results.append({
                "name": gate["name"], "required": gate.get("required", True),
                "level": gate.get("level", "full"),
                "exit_code": result.returncode, "output": output,
                "classification": classification,
                "duration_seconds": round(time.monotonic() - started, 2),
            })
            if result.returncode or skipped:
                message = f"[{gate['name']}] exit {result.returncode}\n{output}"
                (failures if gate.get("required", True) else warnings).append(message)
        ticket["warnings"] = warnings
        ticket["gate_results"] = gate_results
        ticket["verification_level"] = selected_level
        ticket["verification_duration_seconds"] = round(
            time.monotonic() - verification_started, 2,
        )
        self._sync_store()
        return "\n\n".join(failures)

    def block_or_retry(self, ticket: dict, failure: str):
        ticket["failure"] = failure[-3000:]
        if ticket["attempt"] <= self.cfg["factory"]["max_retries"]:
            ticket.setdefault("metrics", {}).setdefault("retry_count", 0)
            ticket["metrics"]["retry_count"] += 1
            if failure.startswith("Code Review requested changes:"):
                ticket["metrics"].setdefault("verifier_rejections", 0)
                ticket["metrics"]["verifier_rejections"] += 1
            self.transition(ticket, "In Progress", f"Retry {ticket['attempt']} of {self.cfg['factory']['max_retries']}")
            return True
        self.transition(ticket, "Blocked", ticket["failure"][:180].replace("\n", " "))
        return False

    def publish_candidate(self, ticket: dict, worktree: Path) -> str:
        """Open or update the PR before its revision-specific review."""
        if self.args.mock:
            reference = f"rehearsal://ticket/{ticket['number']}/attempt/{ticket['attempt']}"
            ticket["review_ref"] = reference
            self._sync_store()
            return reference
        pr_url = self.backend.publish(ticket, worktree)
        ticket["pr_url"] = pr_url
        self._sync_store()
        return pr_url

    def publish_remote_summary(self, ticket: dict) -> None:
        if not self.backend:
            return
        payload = factory_run_summary(self.store.data, ticket)
        publication = self.backend.publish_run_summary(
            ticket["number"], self.run_id, render_factory_run_summary(payload),
        )
        ticket["remote_run_summary"] = publication
        self._sync_store()

    def publish_review_decision(self, ticket: dict) -> None:
        review = ticket.get("code_review") or {}
        result = review.get("result") or {}
        if self.args.mock:
            publication = {"published": True, "official": False, "mode": "rehearsal"}
        else:
            publication = self.backend.submit_agent_review(
                ticket["pr_url"],
                result["decision"],
                render_review_comment(result, ticket["number"], ticket["attempt"]),
            )
        review["publication"] = publication
        if publication.get("warning"):
            ticket.setdefault("warnings", []).append(
                "GitHub recorded the agent decision as a Factory comment rather than a formal review."
            )
        self._sync_store()

    def supervisor_recommend_merge(self, ticket: dict) -> None:
        """Ask the Supervisor for a bounded recommendation without granting merge authority."""
        if not self.supervisor:
            raise RuntimeError("An approved Code Review requires the configured Agent Supervisor.")
        decision = self.supervisor.authorize_merge(ticket)
        ticket["supervisor_merge_decision"] = decision["id"]
        ticket["supervisor_merge_action"] = decision["action"]
        reviewed_head = ticket.get("code_review", {}).get("head", "")
        if decision["action"] == "BLOCK":
            ticket["failure"] = "Supervisor blocked merge recommendation: " + decision["summary"]
            self.record_receipt(
                ticket,
                "supervisor",
                "Review",
                attempt=ticket["attempt"],
                input_revisions={
                    "reviewed_commit": reviewed_head,
                    "pull_request": ticket.get("pr_url") or ticket.get("review_ref", ""),
                },
                output_revisions={"decision": decision["id"]},
                claimed_result="Supervisor recommends blocking human merge",
                verification=[decision["summary"]],
                unresolved_risks=[decision["summary"]],
                artifacts=[decision["prompt"], decision["log"]],
            )
            self.transition(ticket, "Blocked", ticket["failure"][:180])
            return
        ticket["merge_authority"] = "human"
        ticket["approved_head"] = reviewed_head
        self.record_receipt(
            ticket,
            "supervisor",
            "Review",
            attempt=ticket["attempt"],
            input_revisions={
                "reviewed_commit": reviewed_head,
                "pull_request": ticket.get("pr_url") or ticket.get("review_ref", ""),
            },
            output_revisions={"recommended_commit": reviewed_head, "decision": decision["id"]},
            claimed_result="Supervisor recommends human exact-revision merge",
            verification=[decision["summary"], "The Supervisor did not execute a merge command."],
            unresolved_risks=[],
            artifacts=[decision["prompt"], decision["log"]],
        )
        self.transition(
            ticket,
            "In Review",
            "Code Review Agent approved exact revision; Supervisor recommends human merge",
        )

    def supervisor_merge(self, ticket: dict, worktree: Path) -> None:
        if not self.supervisor:
            raise RuntimeError("An approved Code Review requires the configured Agent Supervisor to merge.")
        decision = self.supervisor.authorize_merge(ticket)
        ticket["supervisor_merge_decision"] = decision["id"]
        ticket["supervisor_merge_action"] = decision["action"]
        if decision["action"] == "BLOCK":
            ticket["failure"] = "Supervisor blocked merge: " + decision["summary"]
            self.record_receipt(
                ticket,
                "supervisor_merge",
                "Review",
                attempt=ticket["attempt"],
                input_revisions={
                    "reviewed_commit": ticket["code_review"]["head"],
                    "pull_request": ticket.get("pr_url") or ticket.get("review_ref", ""),
                },
                output_revisions={"decision": decision["id"]},
                claimed_result="Supervisor blocked merge",
                verification=[decision["summary"]],
                unresolved_risks=[decision["summary"]],
                artifacts=[decision["prompt"], decision["log"]],
            )
            self.transition(ticket, "Blocked", ticket["failure"][:180])
            return

        ticket["merge_authority"] = "supervisor"
        ticket["approved_head"] = ticket["code_review"]["head"]
        ticket["merge_executed_by"] = "supervisor"
        self.transition(ticket, "In Review", "Code Review Agent approved; Supervisor authorized merge")
        if not self.args.mock:
            self.backend.assert_pr_head(ticket["pr_url"], ticket["code_review"]["head"])
            self.backend.merge_pr(ticket["pr_url"])
            ticket["history"].append({
                "at": now(), "status": "In Review",
                "note": f"{decision['id']} submitted the validated merge command",
            })
            self._sync_store()
            return

        current_candidate = self.git("rev-parse", ticket["branch"]).stdout.strip()
        if current_candidate != ticket["code_review"]["head"]:
            raise RuntimeError("Candidate branch changed after Code Review Agent approval; review it again.")
        if ticket.get("simulate_merge_conflict"):
            ticket["merge_conflict_path"] = "A competing integration was detected; the merge lock serialized it safely."
            ticket["history"].append({"at": now(), "status": "In Review", "note": "Merge-conflict rehearsal exercised"})
            self._sync_store()
        with self.merge_lock:
            merged = self.git(
                "merge", "--no-ff", "-m", f"Merge ticket #{ticket['number']}",
                ticket["branch"], check=False,
            )
            if merged.returncode:
                self.git("merge", "--abort", check=False)
                ticket["failure"] = "Merge conflict while integrating mock ticket\n" + merged.stdout + merged.stderr
                self.transition(ticket, "Blocked", "Supervisor merge conflict; worktree preserved")
                return
        merged_head = self.git("rev-parse", "HEAD").stdout.strip()
        self.transition(ticket, "Done", "Supervisor merged approved rehearsal pull request")
        self.record_receipt(
            ticket,
            "supervisor_merge",
            "Review",
            attempt=ticket["attempt"],
            input_revisions={
                "reviewed_commit": ticket["code_review"]["head"],
                "pull_request": ticket.get("review_ref", ""),
            },
            output_revisions={"decision": decision["id"], "merged_commit": merged_head},
            claimed_result="Supervisor-authorized rehearsal merge completed",
            verification=["Approved candidate branch was merged through the validated Supervisor command."],
            artifacts=[decision["prompt"], decision["log"]],
        )
        self.git("worktree", "remove", "--force", str(worktree), check=False)
        self.git("branch", "-d", ticket["branch"], check=False)

    def human_publish(self, ticket: dict, worktree: Path) -> None:
        """Publish a verified candidate and stop at the human exact-revision gate."""
        reference = self.publish_candidate(ticket, worktree)
        reviewed_head = self.git("rev-parse", "HEAD", cwd=worktree).stdout.strip()
        ticket["merge_authority"] = "human"
        ticket["approved_head"] = reviewed_head
        self.transition(ticket, "In Review", "Verified candidate is ready for human exact-revision merge")
        ticket["history"].append({
            "at": now(),
            "status": "In Review",
            "note": f"Human merge gate bound to {reviewed_head[:12]} at {reference}",
        })
        self._sync_store()

    def process(self, ticket: dict):
        resume_qa = bool(ticket.get("qa_approved") and ticket.get("qa_commit") and ticket.get("branch"))
        if self.backend and not resume_qa:
            try:
                base_revision = self.git("rev-parse", "HEAD").stdout.strip()
                claim = self.backend.claim_ticket(ticket, self.run_id, base_revision)
                ticket["remote_claim"] = claim
                self._sync_store()
            except Exception as exc:
                ticket["failure"] = str(exc)[-3000:]
                self.transition(ticket, "Blocked", "Could not acquire the remote Ticket claim")
                return
            if not claim.get("owned"):
                ticket["failure"] = (
                    f"Remote Ticket claim is owned by Factory run {claim.get('owner_run_id', 'unknown')} "
                    f"at {claim.get('ref', 'the deterministic claim ref')}. No agent was started."
                )
                self.transition(ticket, "Blocked", "Another Factory run owns this Ticket")
                return
        first_phase = (
            f"Running {ticket['agent']} with approved Acceptance Tests"
            if resume_qa else (f"Running QA {self.qa_agent}" if self.qa_agent else f"Running {ticket['agent']}")
        )
        self.transition(ticket, "In Progress", first_phase)
        if resume_qa:
            worktree = worktree_path(self.repo, ticket["number"])
            base_sha = ticket.get("base_sha", "")
            if not worktree.is_dir() or self.verify_qa_tests_unchanged(ticket, worktree):
                ticket["failure"] = "Approved QA worktree or protected tests are missing"
                self.transition(ticket, "Blocked", "Could not resume approved QA worktree")
                return
            implementation_base_sha = ticket["qa_commit"]
        else:
            try:
                worktree, base_sha = self.create_worktree(ticket)
                self.snapshot_existing_tests(ticket, worktree, base_sha)
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
            previous_failure = failure
            previously_reviewed_head = (
                ticket.get("code_review", {}).get("head", "")
                if previous_failure.startswith("Code Review requested changes:") else ""
            )
            prompt = self.make_prompt(ticket, previous_failure)
            code, output = self.run_agent(ticket, worktree, prompt)
            candidate_head = ""
            try:
                self.commit_leftovers(ticket, worktree)
                changed = self.git(
                    "diff", "--name-status", implementation_base_sha, "HEAD", cwd=worktree,
                ).stdout.splitlines()
                ticket["changed_files"] = [
                    {"status": fields[0], "path": fields[-1]}
                    for line in changed if len(fields := line.split("\t")) >= 2
                ]
                controls = classify_controls(
                    self.charter,
                    [item["path"] for item in ticket["changed_files"]],
                )
                if self.profile_name == "assured":
                    controls = {
                        **controls,
                        "gate_level": "deep",
                        "reason": controls["reason"] + " The Assured profile requires deep verification.",
                    }
                ticket.setdefault("triage", {})["controls"] = controls
                self._sync_store()
                commits = int(
                    self.git("rev-list", "--count", f"{implementation_base_sha}..HEAD", cwd=worktree).stdout
                )
                candidate_head = self.git("rev-parse", "HEAD", cwd=worktree).stdout.strip()
            except Exception as exc:
                commits, output, code = 0, f"{output}\n{exc}", 1
            unchanged_review_retry = bool(
                previously_reviewed_head and candidate_head == previously_reviewed_head
            )
            if code or not commits or unchanged_review_retry:
                failure = (
                    output[-3000:] if code
                    else "Implementation did not change the candidate after Code Review requested changes."
                    if unchanged_review_retry
                    else "Agent produced no changes or commits."
                )
                self.record_receipt(
                    ticket,
                    "implementation",
                    "Build",
                    attempt=attempt,
                    input_revisions={"implementation_base": implementation_base_sha},
                    output_revisions={},
                    claimed_result="Implementation attempt failed",
                    verification=[f"Agent adapter exit code: {code}"],
                    unresolved_risks=[
                        "Implementation did not produce acceptable committed output; inspect the referenced log."
                    ],
                    artifacts=[ticket.get("current_log", "")],
                )
                if self.block_or_retry(ticket, failure):
                    continue
                return
            implementation_head = candidate_head
            self.record_receipt(
                ticket,
                "implementation",
                "Build",
                attempt=attempt,
                input_revisions={"implementation_base": implementation_base_sha},
                output_revisions={"implementation_commit": implementation_head},
                claimed_result="Implementation committed",
                verification=["Agent exited successfully and produced at least one commit."],
                artifacts=[item["path"] for item in ticket["changed_files"]],
            )
            if "cleanup" in self.profile["execution_roles"]:
                failure = self.run_assured_roles(ticket, worktree, implementation_head)
                if failure:
                    if self.block_or_retry(ticket, failure):
                        continue
                    return
                implementation_head = self.git("rev-parse", "HEAD", cwd=worktree).stdout.strip()
            failure = self.verify_project_protected_paths(worktree, implementation_base_sha)
            if failure:
                if self.block_or_retry(ticket, failure):
                    continue
                return
            self.transition(ticket, "Verifying", f"Attempt {attempt}")
            failure = self.verify_qa_tests_unchanged(ticket, worktree)
            if not failure:
                failure = self.verify_existing_tests(ticket, worktree)
            if not failure and ticket.get("qa_tests"):
                failure = self.run_focused_acceptance(
                    ticket, worktree, expected="green",
                )
            if not failure:
                failure = self.verify(ticket, worktree)
            verification = [
                f"{gate['name']}: exit {gate['exit_code']} ({'required' if gate['required'] else 'advisory'})"
                for gate in ticket.get("gate_results", [])
            ]
            if ticket.get("qa_evidence", {}).get("red", {}).get("result") == "RED PROVED":
                verification.insert(0, "RED PROVED against the QA test revision.")
            if ticket.get("qa_evidence", {}).get("green", {}).get("result") == "GREEN PROVED":
                verification.insert(1, "GREEN PROVED with the identical focused command.")
            self.record_receipt(
                ticket,
                "verification",
                "Verify",
                attempt=attempt,
                input_revisions={"implementation_commit": implementation_head},
                output_revisions={"verified_commit": implementation_head} if not failure else {},
                claimed_result="Verification passed" if not failure else "Verification failed",
                verification=verification or ["Protected Acceptance Test hashes checked."],
                unresolved_risks=(
                    ["Required verification did not pass; inspect gate results in factory state."]
                    if failure else []
                ),
                artifacts=sorted(ticket.get("qa_tests", {})),
                evidence={
                    **ticket.get("qa_evidence", {}),
                    "existing_tests": {
                        "policy": ticket.get("existing_test_policy", ""),
                        "changed": ticket.get("existing_test_changes", []),
                    },
                },
            )
            if not failure and ticket.get("verification_level") == "deep":
                failure = self.run_profile_role(
                    ticket,
                    worktree,
                    "critic",
                    implementation_head,
                    read_only=True,
                )
            if not failure and "negative_proof" in self.profile["execution_roles"]:
                failure = self.run_negative_proof(
                    ticket, worktree, implementation_head,
                )
            if not failure and "final_verifier" in self.profile["execution_roles"]:
                failure = self.run_final_verifier(ticket, worktree, implementation_head)
            if not failure and self.review_agent:
                try:
                    pull_request = self.publish_candidate(ticket, worktree)
                except Exception as exc:
                    ticket["failure"] = str(exc)[-3000:]
                    self.transition(ticket, "Blocked", "Could not open or update the pull request")
                    return
                failure = self.run_code_review(
                    ticket, worktree, ticket["base_sha"] or base_sha, pull_request,
                )
                review_result = (ticket.get("code_review") or {}).get("result")
                if not review_result:
                    ticket["failure"] = failure[-3000:]
                    self.transition(ticket, "Blocked", "Code Review Agent returned an invalid decision")
                    return
                try:
                    self.publish_review_decision(ticket)
                except Exception as exc:
                    ticket["failure"] = str(exc)[-3000:]
                    self.transition(ticket, "Blocked", "Could not publish the code-review decision")
                    return
            if failure:
                if self.block_or_retry(ticket, failure):
                    continue
                return
            ticket["failure"] = ""
            try:
                if self.review_agent:
                    if self.profile["merge_authority"] == "supervisor":
                        self.supervisor_merge(ticket, worktree)
                    else:
                        self.supervisor_recommend_merge(ticket)
                else:
                    self.human_publish(ticket, worktree)
                self.publish_remote_summary(ticket)
            except Exception as exc:
                ticket["failure"] = str(exc)[-3000:]
                self.transition(ticket, "Blocked", "Review handoff failed; worktree preserved")
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
            automated = ticket.get("merge_executed_by") == "supervisor"
            self.record_receipt(
                ticket,
                "supervisor_merge" if automated else "human_review",
                "Review",
                attempt=max(1, ticket.get("attempt", 1)),
                input_revisions={"pull_request": ticket.get("pr_url", "")},
                output_revisions={
                    **({"decision": ticket.get("supervisor_merge_decision", "")} if automated else {}),
                    "merged_commit": merge_sha or head,
                },
                claimed_result=(
                    "Supervisor-authorized pull request merged and synchronized"
                    if automated else "Human-reviewed pull request merged and synchronized"
                ),
                verification=[
                    f"Merge commit is reachable from {self.backend.default_branch}.",
                    *(["Code Review Agent approval matched the merged candidate."] if automated else []),
                ],
                artifacts=[
                    ticket.get("pr_url", ""),
                    *(
                        [
                            ticket.get("code_review", {}).get("artifact", ""),
                        ]
                        if automated else []
                    ),
                ],
            )
            self.publish_remote_summary(ticket)
            worktree = worktree_path(self.repo, ticket["number"])
            self.git("worktree", "remove", "--force", str(worktree), check=False)
            if ticket.get("branch"):
                self.git("branch", "-d", ticket["branch"], check=False)

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
        ) or (self.qa_agent == "codex" and unfinished) or (
            self.supervisor_agent == "codex" and unfinished
        ) or (self.review_agent == "codex" and unfinished)
        if needs_codex:
            self.codex_bin = resolve_codex_cli()
            print(f"Codex adapter: {self.codex_bin}", flush=True)
        if self.supervisor_agent:
            self.supervisor = AgentSupervisor(
                self.repo,
                agent=self.supervisor_agent,
                template=self.cfg["agents"][self.supervisor_agent],
                python=self.python,
                codex_bin=self.codex_bin or "",
                scenario=self.args.scenario,
                mock=self.args.mock,
                agent_timeout=int(self.cfg["factory"]["agent_timeout"]),
            )
            print(f"Supervisor adapter: {self.supervisor_agent}", flush=True)
        for cycle in self.detect_cycles():
            note = "Dependency cycle: " + " → ".join(f"#{n}" for n in cycle)
            for n in set(cycle[:-1]):
                self.tickets[n]["failure"] = note
                self.transition(self.tickets[n], "Blocked", note)
        while True:
            self.sync_merged()
            self.apply_qa_approvals()
            self.refresh_readiness()
            candidates = [t for t in self.tickets.values() if t["status"] == "Ready"]
            ready = self.coordinate_ready(candidates) if candidates else []
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


def release_ticket_claim(
    repo: Path,
    number: int,
    *,
    owner_run_id: str,
    reason: str,
    assume_yes: bool,
) -> dict:
    """Perform an explicit, audited release of one abandoned remote claim."""
    backend = GitHubBackend(repo)
    backend.preflight()
    claim = backend.read_claim(number)
    if not claim:
        raise ValueError(f"Ticket #{number} has no remote Factory claim")
    if claim.get("run_id") != owner_run_id:
        raise ValueError(
            f"Ticket #{number} is owned by {claim.get('run_id')}, not {owner_run_id}"
        )
    if not assume_yes:
        try:
            answer = input(
                f"Release remote claim for Ticket #{number} owned by {owner_run_id}? "
                "Type RELEASE CLAIM: "
            )
        except EOFError as exc:
            raise ValueError("interactive claim release required; rerun with --yes") from exc
        if answer != "RELEASE CLAIM":
            raise ValueError("remote claim release cancelled")
    result = backend.release_claim(number, owner_run_id, reason=reason)
    store = StateStore(repo)
    ticket = next(
        (item for item in store.data.get("tickets", []) if item.get("number") == number),
        None,
    )
    if ticket:
        ticket["remote_claim"] = {**claim, **result}
        ticket.setdefault("history", []).append({
            "at": now(),
            "status": ticket.get("status", "Blocked"),
            "note": f"Operator released remote claim: {reason}",
        })
        store.save()
    print(f"Released remote claim for Ticket #{number} owned by {owner_run_id}.")
    return result


def human_merge_ticket(
    repo: Path,
    number: int,
    *,
    mock: bool,
    project_number: int | None,
    assume_yes: bool,
) -> str:
    """Execute the named human's exact-revision merge decision."""
    repo = repo.resolve()
    store = StateStore(repo)
    ticket = next(
        (item for item in store.data.get("tickets", []) if item.get("number") == number),
        None,
    )
    if not ticket:
        raise ValueError(f"Ticket #{number} not found in factory state")
    if ticket.get("status") != "In Review":
        raise ValueError(f"Ticket #{number} is {ticket.get('status')}, not In Review")
    charter = FactoryCharter.load(repo, require_approved=True)
    if charter.merge_authority != "human":
        raise ValueError(
            "The approved Factory Charter delegates merge authority; use the explicitly opted-in "
            "Autonomous Demo run instead of a human-merge command."
        )
    governance = store.data.get("governance")
    if not isinstance(governance, dict):
        raise ValueError(
            "Factory state predates the governed human-merge gate. Re-run the Ticket with the "
            "approved Factory Charter before merging."
        )
    if governance.get("charter_sha256") != charter.policy_sha256():
        raise ValueError(
            "Factory Charter changed after this Ticket was verified. Re-run verification under "
            "the current approved Charter before merging."
        )
    if governance.get("merge_authority") != "human":
        raise ValueError("The recorded Factory Run does not grant human merge authority.")
    approved_head = ticket.get("approved_head", "")
    if not re.fullmatch(r"[a-f0-9]{40,64}", approved_head or ""):
        raise ValueError("Ticket does not record an exact approved candidate revision.")
    required_failures = [
        gate.get("name", "unnamed")
        for gate in ticket.get("gate_results", [])
        if gate.get("required", True) and gate.get("exit_code") != 0
    ]
    if required_failures:
        raise ValueError("Required gates are not green: " + ", ".join(required_failures))
    review = ticket.get("code_review") or {}
    if review and (
        review.get("result", {}).get("decision") != "APPROVE"
        or review.get("head") != approved_head
    ):
        raise ValueError("Code Review Agent approval does not match the exact candidate revision.")
    branch = ticket.get("branch", "")
    if not branch:
        raise ValueError("Ticket branch is missing; the candidate cannot be merged safely.")
    current_candidate = run(["git", "rev-parse", branch], repo).stdout.strip()
    if current_candidate != approved_head:
        raise ValueError(
            "Candidate branch changed after approval. Review and verify the new revision before merge."
        )
    print(f"Human merge gate for Ticket #{number}: {ticket.get('title', '')}")
    print(f"  Candidate: {approved_head}")
    print(f"  Charter: {charter.policy_sha256()}")
    print(f"  Pull request: {ticket.get('pr_url') or ticket.get('review_ref', 'rehearsal')}")
    if not assume_yes:
        try:
            answer = input("Merge this exact revision? Type MERGE EXACT REVISION: ")
        except EOFError as exc:
            raise ValueError(
                "interactive human merge required; rerun in a terminal or pass --yes"
            ) from exc
        if answer != "MERGE EXACT REVISION":
            raise ValueError("human merge cancelled")
    if mock:
        merged = run(
            ["git", "merge", "--no-ff", "-m", f"Merge ticket #{number}", branch],
            repo,
            check=False,
        )
        if merged.returncode:
            run(["git", "merge", "--abort"], repo, check=False)
            raise ValueError("Human rehearsal merge conflicted; the Ticket worktree was preserved.")
        merged_head = run(["git", "rev-parse", "HEAD"], repo).stdout.strip()
    else:
        backend = GitHubBackend(repo, project_number)
        pr_url = ticket.get("pr_url", "")
        if not pr_url:
            raise ValueError("Ticket pull request is missing.")
        backend.assert_pr_head(pr_url, approved_head)
        backend.merge_pr(pr_url)
        merged_pr = backend.merged_pr(ticket)
        if not merged_pr:
            raise ValueError("GitHub did not report the pull request as merged.")
        merged_head = (merged_pr.get("mergeCommit") or {}).get("oid", "")
        run(["git", "fetch", "origin", backend.default_branch], repo)
        run(["git", "merge", "--ff-only", f"origin/{backend.default_branch}"], repo)
        if merged_head:
            reachable = run(
                ["git", "merge-base", "--is-ancestor", merged_head, "HEAD"],
                repo,
                check=False,
            )
            if reachable.returncode:
                raise ValueError("Merged GitHub revision is not reachable from the synchronized default branch.")
        else:
            merged_head = run(["git", "rev-parse", "HEAD"], repo).stdout.strip()
    contract = role_input(repo, "human_review")
    receipt = handoff_receipt(
        run_id=ticket.get("plan_id") or f"ticket-{number}",
        role="human_review",
        phase="Review",
        ticket=number,
        attempt=max(1, int(ticket.get("attempt", 1))),
        input_revisions={
            "approved_commit": approved_head,
            "charter_sha256": charter.policy_sha256(),
        },
        output_revisions={"merged_commit": merged_head},
        claimed_result="Human merged the exact approved revision",
        verification=[
            "Candidate head matched the approved revision immediately before merge.",
            "Every recorded required gate was green.",
        ],
        unresolved_risks=[],
        artifacts=[
            item for item in (
                ticket.get("pr_url") or ticket.get("review_ref", ""),
                review.get("artifact", ""),
            ) if item
        ],
        policy_hashes=contract["policy_hashes"],
    )
    receipt_path = write_handoff_receipt(repo, receipt)
    ticket.setdefault("receipts", []).append(str(receipt_path.relative_to(repo)))
    ticket["status"] = "Done"
    ticket["phase"] = "human_review"
    ticket["merge_executed_by"] = "human"
    ticket["failure"] = ""
    ticket.setdefault("history", []).append({
        "at": now(),
        "status": "Done",
        "note": f"Human merged exact approved revision {approved_head[:12]}",
    })
    store.save()
    worktree = worktree_path(repo, number)
    run(["git", "worktree", "remove", "--force", str(worktree)], repo, check=False)
    run(["git", "branch", "-d", branch], repo, check=False)
    print(f"Ticket #{number} merged at {merged_head}.")
    return merged_head


def approve_qa_tests(repo: Path, number: int, assume_yes=False):
    store = StateStore(repo)
    ticket = next((item for item in store.data.get("tickets", []) if item["number"] == number), None)
    if not ticket:
        raise ValueError(f"Ticket #{number} not found in factory state")
    if ticket.get("status") != "QA Review":
        raise ValueError(f"Ticket #{number} is {ticket.get('status')}, not QA Review")
    evidence = ticket.get("qa_evidence", {})
    red = evidence.get("red", {})
    command = evidence.get("focused_test_command", "")
    command_hash = evidence.get("focused_test_command_sha256", "")
    if (
        red.get("result") != "RED PROVED"
        or red.get("classification") != "behavior_assertion"
        or red.get("revision") != ticket.get("qa_commit")
        or evidence.get("test_revision") != ticket.get("qa_commit")
        or not command
        or Factory._command_sha256(command) != command_hash
    ):
        raise ValueError(
            "Acceptance Tests cannot be approved without intact RED PROVED evidence "
            "for the exact QA revision and focused command. Retry QA after fixing the "
            "reported causal-evidence failure."
        )
    worktree = worktree_path(repo, number)
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
    print("\nCausal evidence:")
    print(f"- Focused command: {command}")
    print(f"- RED result: {red['result']}")
    print(f"- Failure classification: {red['classification']}")
    print(f"- Test revision: {red['revision']}")
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


def initialize_project(repo: Path, name: str | None, force: bool) -> Path:
    if run(["git", "rev-parse", "--show-toplevel"], repo, check=False).returncode:
        raise ValueError(f"Project repository is not a Git checkout: {repo}")
    contract = ProjectContract.detect(repo, name=name)
    path = contract.write(force=force)
    charter_path = FactoryCharter.draft(repo, contract).write(force=force)
    ignore_path = repo / ".gitignore"
    existing = ignore_path.read_text() if ignore_path.is_file() else ""
    ignored = any(
        line.strip() in {".factory", ".factory/"} for line in existing.splitlines()
    )
    if not ignored:
        separator = "" if not existing or existing.endswith("\n") else "\n"
        ignore_path.write_text(
            existing + separator + "\n# Local Software (re)-Factory state and credentials\n.factory/\n"
        )
    print(f"Project Contract created: {path}")
    print(f"Factory Charter draft created: {charter_path}")
    if not ignored:
        print(f"Factory runtime ignore added: {ignore_path}")
    print(f"  Source roots: {', '.join(contract.source_roots)}")
    print(f"  Test roots: {', '.join(contract.test_roots)}")
    print(f"  Gates: {', '.join(gate['name'] for gate in contract.gates)}")
    print(
        "Review the Charter, then run `factory approve-charter --yes`. Commit both contracts. "
        "Run `factory prepare` if setup commands are present, "
        "then `factory doctor --full` before a Live Run."
    )
    return path


def approve_charter(repo: Path, *, assume_yes: bool) -> Path:
    """Bind human approval to the exact current Charter policy."""
    charter = FactoryCharter.load(repo)
    print("Factory Charter review:")
    print(f"  Consequence tier: {charter.consequence_tier}")
    print(f"  Merge authority: {charter.merge_authority}")
    print(f"  Verification level: {charter.gate_level}")
    print(f"  Policy hash: {charter.policy_sha256()}")
    if not assume_yes:
        try:
            answer = input("Approve this exact policy? Type APPROVE CHARTER: ")
        except EOFError as exc:
            raise ValueError(
                "Charter approval required; rerun in a terminal or pass --yes"
            ) from exc
        if answer != "APPROVE CHARTER":
            raise ValueError("Factory Charter approval cancelled")
    approved = charter.approve()
    print(f"Factory Charter approved: {approved.path}")
    print(f"Approved policy sha256: {approved.approved_policy_sha256}")
    return approved.path or repo / "factory.charter.toml"


def publish_repository_setup(repo: Path, *, assume_yes: bool) -> str:
    """Commit and push only the reviewed repository governance bootstrap."""
    repo = repo.resolve()
    project = ProjectContract.load(repo, require=True)
    charter = FactoryCharter.load(repo, require_approved=True)
    branch = run(["git", "branch", "--show-current"], repo).stdout.strip()
    if branch != project.default_branch:
        raise ValueError(
            f"Repository setup must be published from `{project.default_branch}`, not "
            f"`{branch or 'detached HEAD'}`."
        )
    allowed = {".gitignore", "factory.project.toml", CHARTER_PATH.as_posix()}
    changed = run(
        ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
        repo,
    ).stdout
    paths = {
        entry[3:].split(" -> ")[-1]
        for entry in changed.split("\0")
        if len(entry) >= 4
    }
    unexpected = sorted(paths - allowed)
    if unexpected:
        raise ValueError(
            "Repository setup cannot publish unrelated changes: " + ", ".join(unexpected)
        )
    if not assume_yes:
        try:
            answer = input(
                "Commit and push the approved Project Contract and Factory Charter? "
                "Type PUBLISH SETUP: "
            )
        except EOFError as exc:
            raise ValueError(
                "interactive setup approval required; rerun in a terminal or pass --yes"
            ) from exc
        if answer != "PUBLISH SETUP":
            raise ValueError("repository setup publication cancelled")
    run(["git", "add", "--", *sorted(allowed)], repo)
    staged = run(["git", "diff", "--cached", "--quiet"], repo, check=False)
    if staged.returncode:
        run(["git", "commit", "-m", "chore: configure software factory"], repo)
    commit = run(["git", "rev-parse", "HEAD"], repo).stdout.strip()
    run(["git", "push", "-u", "origin", branch], repo)
    print("Repository setup published.")
    print(f"  Branch: {branch}")
    print(f"  Commit: {commit}")
    print(f"  Charter: {charter.policy_sha256()}")
    return commit


def prepare_project(repo: Path, *, assume_yes: bool) -> None:
    """Run only the setup commands explicitly recorded in the Project Contract."""
    project = ProjectContract.load(repo, require=True)
    if not project.setup_commands:
        print(f"{project.name} does not declare setup commands.")
        return
    venv_python = repo / ".factory/venv/bin/python"
    python = str(venv_python if venv_python.is_file() else Path(sys.executable))
    commands = [project.render_command(item, python=python) for item in project.setup_commands]
    print("Project Contract setup commands:")
    for command_text in commands:
        print(f"  {command_text}")
    if not assume_yes:
        try:
            answer = input("Run these repository commands? Type RUN SETUP: ")
        except EOFError as exc:
            raise ValueError("setup approval required; rerun in a terminal or pass --yes") from exc
        if answer != "RUN SETUP":
            raise ValueError("project setup cancelled")
    for command_text in commands:
        print(f"\n$ {command_text}", flush=True)
        result = subprocess.run(
            command_text, cwd=repo, text=True, shell=True, executable="/bin/sh",
        )
        if result.returncode:
            raise RuntimeError(
                f"project setup failed with exit code {result.returncode}: {command_text}"
            )
    print("\nProject setup completed.")


def reset_project(
    repo: Path, *, scenario: str, start_over: bool, local_state_only: bool = False,
) -> None:
    project = ProjectContract.load(repo)
    command = None if local_state_only else project.reset_argv(scenario, start_over=start_over)
    if command:
        result = subprocess.run(command, cwd=repo)
        if result.returncode:
            raise RuntimeError("project reset adapter failed")
        return
    worktrees = run(["git", "worktree", "list", "--porcelain"], repo, check=False)
    allowed_prefix = str(repo.parent / f"{repo.name}-wt-")
    supervisor_path = str(repo.parent / f"{repo.name}-supervisor-wt")
    for line in worktrees.stdout.splitlines():
        if not line.startswith("worktree "):
            continue
        path = line.removeprefix("worktree ")
        if path.startswith(allowed_prefix) or path == supervisor_path:
            run(["git", "worktree", "remove", "--force", path], repo, check=False)
    run(["git", "worktree", "prune"], repo, check=False)
    runtime = repo / ".factory"
    for relative in ("state.json", "state.tmp", "ids.json"):
        (runtime / relative).unlink(missing_ok=True)
    for relative in ("supervisor", "reviews"):
        shutil.rmtree(runtime / relative, ignore_errors=True)
    for relative in ("prompts", "qa-approvals"):
        directory = runtime / relative
        if directory.is_dir():
            for path in directory.iterdir():
                if path.is_file() or path.is_symlink():
                    path.unlink(missing_ok=True)
                elif path.is_dir():
                    shutil.rmtree(path)
    if start_over:
        for relative in ("plans", "rehearsal", "receipts"):
            shutil.rmtree(runtime / relative, ignore_errors=True)
        for relative in ("planning-state.json", "planning-state.tmp"):
            (runtime / relative).unlink(missing_ok=True)
        for relative in (
            "control-center/workshop-prd.md", "control-center/factory-canvas.md",
            "control-center/product-feedback.md",
        ):
            (runtime / relative).unlink(missing_ok=True)
    runtime.mkdir(parents=True, exist_ok=True)
    (runtime / "state.json").write_text(json.dumps({
        "mode": "local", "project": project.name, "updated_at": "waiting for run", "tickets": [],
    }, indent=2) + "\n")
    print(f"Local factory state reset for {project.name}.")
    print("Tracked source files and remote GitHub artifacts were not changed.")


def parser():
    p = argparse.ArgumentParser(prog="factory", description="Software (re)-Factory orchestrator")
    p.add_argument("--version", action="version", version=f"factory {WORKSHOP_VERSION}")
    sub = p.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="detect a repository and create its Project Contract")
    init.add_argument("--repo", default=".")
    init.add_argument("--name")
    init.add_argument("--force", action="store_true")
    prepare = sub.add_parser(
        "prepare", help="run reviewed setup commands from the Project Contract",
    )
    prepare.add_argument("--repo", default=".")
    prepare.add_argument("--yes", action="store_true")
    approve_charter_p = sub.add_parser(
        "approve-charter", help="approve the exact human-owned Factory Charter policy",
    )
    approve_charter_p.add_argument("--repo", default=".")
    approve_charter_p.add_argument("--yes", action="store_true")
    publish_setup = sub.add_parser(
        "publish-setup",
        help="commit and push the approved Project Contract and Factory Charter",
    )
    publish_setup.add_argument("--repo", default=".")
    publish_setup.add_argument("--yes", action="store_true")
    control_center = sub.add_parser(
        "control-center", help="open the local web control plane",
    )
    control_center.add_argument("--repo", default=".")
    control_center.add_argument("--host", default="127.0.0.1")
    control_center.add_argument("--port", type=positive_int, default=5050)
    control_center.add_argument("--no-open", action="store_true")
    configure = sub.add_parser("configure", help="save attendee defaults for shorter commands")
    configure.add_argument("--repo", default=".")
    configure.add_argument("--preset", choices=sorted(PRESETS))
    configure.add_argument("--profile", choices=sorted(FACTORY_PROFILES))
    configure.add_argument("--agent", help="registered implementation adapter name")
    configure.add_argument("--qa-agent", help="registered independent QA adapter name")
    configure.add_argument("--supervisor-agent", help="registered adapter that coordinates ticket dispatch")
    configure.add_argument("--review-agent", help="registered adapter that reviews candidate pull-request diffs")
    configure.add_argument("--planning-agent", choices=["claude", "codex"])
    configure.add_argument(
        "--review-qa-tests", action=argparse.BooleanOptionalAction, default=None,
        help="pause for human review after QA writes acceptance tests",
    )
    configure.add_argument("--max-parallel", type=positive_int)
    configure.add_argument("--project-number", type=positive_int)
    configure.add_argument(
        "--github-repository", metavar="URL",
        help="GitHub repository URL used for Live issues, branches, Projects, and pull requests",
    )
    checkout = sub.add_parser(
        "checkout",
        help="clone or reuse a GitHub repository in an isolated Control Center workspace",
    )
    checkout.add_argument("github_repository", metavar="URL")
    checkout.add_argument("--workspace-root", required=True)
    profiles = sub.add_parser("profiles", help="show executable Factory Profile role sequences")
    profiles.add_argument("--json", action="store_true", dest="as_json")
    canvas = sub.add_parser("canvas", help="create a Factory Canvas from the versioned template")
    canvas.add_argument("--repo", default=".")
    canvas.add_argument("--output", default="factory-canvas.md")
    canvas.add_argument("--force", action="store_true")
    evidence = sub.add_parser("evidence", help="export a sanitized Evidence Packet")
    evidence.add_argument("plan"); evidence.add_argument("--repo", default=".")
    evidence.add_argument("--canvas", required=True)
    evidence.add_argument("--ticket", action="append", type=int, dest="tickets")
    evidence.add_argument("--output")
    release_check = sub.add_parser("release-check", help="audit a frozen tree before public/template release")
    release_check.add_argument("--repo", default=".")
    release_check.add_argument("--rehearsal", action="store_true", help="run the clean Standard Rehearsal journey")
    release_check.add_argument(
        "--live-smoke",
        action="store_true",
        help="run the Claude golden path and create a fresh Project in a disposable GitHub repo",
    )
    release_check.add_argument("--confirm-disposable-repo", action="store_true")
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
    run_p.add_argument("--profile", choices=sorted(FACTORY_PROFILES))
    run_p.add_argument("--max-parallel", type=positive_int); run_p.add_argument("--project-number", type=positive_int)
    run_p.add_argument(
        "--qa-agent",
        help="independent agent that writes protected acceptance tests before implementation",
    )
    run_p.add_argument(
        "--supervisor-agent",
        help="agent that reads Handoff Receipts and coordinates dependency-ready tickets",
    )
    run_p.add_argument(
        "--review-agent",
        help="read-only agent that approves the exact PR candidate or requests implementation changes",
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
    run_p.add_argument(
        "--allow-autonomous-merge",
        action="store_true",
        help="explicitly delegate exact-revision merge in the Autonomous Demo profile",
    )
    status = sub.add_parser("status"); status.add_argument("--repo", default=".")
    monitor_p = sub.add_parser(
        "monitor", help="inspect delivery health without repairing product code",
    )
    monitor_p.add_argument("--repo", default=".")
    monitor_p.add_argument(
        "--publish", action="store_true",
        help="explicitly create or update GitHub Tickets for unchanged findings",
    )
    monitor_p.add_argument("--json", action="store_true", dest="as_json")
    retry = sub.add_parser("retry"); retry.add_argument("issue", type=int); retry.add_argument("--repo", default=".")
    retry.add_argument("--mock", action="store_true"); retry.add_argument("--project-number", type=positive_int)
    release_claim = sub.add_parser(
        "release-claim", help="explicitly release one abandoned remote Ticket claim",
    )
    release_claim.add_argument("issue", type=int); release_claim.add_argument("--repo", default=".")
    release_claim.add_argument("--owner-run-id", required=True)
    release_claim.add_argument("--reason", required=True)
    release_claim.add_argument("--yes", action="store_true")
    merge = sub.add_parser("merge", help="record a human exact-revision merge decision")
    merge.add_argument("issue", type=int); merge.add_argument("--repo", default=".")
    merge.add_argument("--mock", action="store_true"); merge.add_argument("--project-number", type=positive_int)
    merge.add_argument("--yes", action="store_true")
    reset = sub.add_parser("reset", help="clear local factory state through the Project Contract")
    reset.add_argument("--repo", default=".")
    reset.add_argument("--scenario", choices=["tv", "recipe-rebrand"], default="recipe-rebrand")
    reset.add_argument("--start-over", action="store_true")
    reset.add_argument(
        "--local-state-only", action="store_true",
        help="clear local factory artifacts without invoking the repository reset adapter",
    )
    plan = sub.add_parser("plan", help="run the Product Review expert on a PRD")
    plan.add_argument("prd"); plan.add_argument("--repo", default="."); plan.add_argument("--output")
    plan.add_argument("--profile", choices=sorted(FACTORY_PROFILES))
    plan.add_argument("--default-agent", help="registered adapter written into generated tickets")
    plan.add_argument("--planning-agent", choices=["claude", "codex"])
    plan.add_argument("--min-tickets", type=int, default=3); plan.add_argument("--max-tickets", type=int, default=12)
    plan.add_argument("--mock", action="store_true", help="use bundled deterministic planning artifacts")
    plan.add_argument(
        "--allow-autonomous-merge",
        action="store_true",
        help="explicitly delegate exact-revision merge in the Autonomous Demo profile",
    )
    review = sub.add_parser("review", help="open a human review gate for a planning run")
    review.add_argument("kind", choices=["product", "alignment"]); review.add_argument("plan")
    review.add_argument("--repo", default=".")
    approve_product_p = sub.add_parser("approve-product", help="approve product behavior and scope")
    approve_product_p.add_argument("plan"); approve_product_p.add_argument("--repo", default=".")
    approve_product_p.add_argument("--yes", action="store_true")
    continue_p = sub.add_parser("continue-plan", help="run architecture, program design, and vertical-slice experts")
    continue_p.add_argument("plan"); continue_p.add_argument("--repo", default=".")
    continue_p.add_argument(
        "--planning-agent", choices=["claude", "codex"],
        help="retry blocked planning with a different configured adapter",
    )
    continue_p.add_argument("--mock", action="store_true", help="use bundled deterministic planning artifacts")
    revise = sub.add_parser("revise", help="revise a planning stage from written human feedback")
    revise.add_argument("plan"); revise.add_argument(
        "stage",
        choices=["product", "architecture", "program", "slices"],
        help="planning expert whose artifact must incorporate human feedback",
    )
    revise.add_argument("--repo", default=".")
    feedback = revise.add_mutually_exclusive_group(required=True)
    feedback.add_argument("--feedback")
    feedback.add_argument("--feedback-file")
    revise.add_argument("--mock", action="store_true", help="use the bundled deterministic revision")
    approve = sub.add_parser("approve", help="approve alignment and publish tickets to GitHub")
    approve.add_argument("plan"); approve.add_argument("--repo", default=".")
    approve.add_argument("--project-number", type=positive_int); approve.add_argument("--yes", action="store_true")
    approve.add_argument("--new-project-title", help="create and use a fresh GitHub Project")
    approve_rehearsal_p = sub.add_parser(
        "approve-rehearsal",
        help="approve alignment and materialize local PRD-derived rehearsal tickets",
    )
    approve_rehearsal_p.add_argument("plan"); approve_rehearsal_p.add_argument("--repo", default=".")
    approve_rehearsal_p.add_argument("--yes", action="store_true")
    approve_rehearsal_p.add_argument(
        "--scenario", choices=["tv", "recipe-rebrand"], default="recipe-rebrand",
    )
    approve_tests = sub.add_parser("approve-tests", help="approve protected Acceptance Tests for one ticket")
    approve_tests.add_argument("issue", type=int); approve_tests.add_argument("--repo", default=".")
    approve_tests.add_argument("--yes", action="store_true")
    doctor = sub.add_parser("doctor", help="check workshop prerequisites and safety")
    doctor.add_argument("--repo", default="."); doctor.add_argument("--full", action="store_true")
    doctor.add_argument("--agent", help="registered implementation adapter name")
    doctor.add_argument("--qa-agent", help="registered independent QA adapter name")
    doctor.add_argument("--supervisor-agent", help="registered ticket-supervisor adapter name")
    doctor.add_argument("--review-agent", help="registered pull-request code-review adapter name")
    doctor.add_argument("--planning-agent", choices=["claude", "codex"])
    return p


def main():
    args = parser().parse_args()
    repo = Path(getattr(args, "repo", ".")).resolve()
    try:
        session = apply_session_defaults(args, repo)
        if args.command == "init":
            initialize_project(repo, args.name, args.force)
        elif args.command == "approve-charter":
            approve_charter(repo, assume_yes=args.yes)
        elif args.command == "publish-setup":
            publish_repository_setup(repo, assume_yes=args.yes)
        elif args.command == "prepare":
            prepare_project(repo, assume_yes=args.yes)
        elif args.command == "control-center":
            from control_center import serve
            serve(repo, host=args.host, port=args.port, open_browser=not args.no_open)
        elif args.command == "configure":
            connected_repository = None
            if args.github_repository:
                connected_repository = connect_github_repository(repo, args.github_repository)
            path, configured = configure_session(
                repo, args.preset, args.project_number,
                agent=args.agent, qa_agent=args.qa_agent,
                supervisor_agent=args.supervisor_agent,
                review_agent=args.review_agent,
                planning_agent=args.planning_agent,
                review_qa_tests=args.review_qa_tests,
                max_parallel=args.max_parallel, profile=args.profile,
                github_repository=(connected_repository or {}).get("url"),
            )
            print(render_session_config(configured))
            if connected_repository:
                print(
                    f"\nGitHub repository connected: {connected_repository['url']} "
                    f"(origin {connected_repository['origin']})"
                )
            print(f"\nSaved attendee defaults: {path}")
            print("Next: ./factory/factory doctor")
        elif args.command == "checkout":
            connected = checkout_github_repository(
                Path(args.workspace_root), args.github_repository,
            )
            print(f"Repository {connected['action']}: {connected['path']}")
        elif args.command == "profiles":
            print(render_profiles(args.as_json))
        elif args.command == "canvas":
            path = create_canvas(repo, Path(args.output), args.force)
            print(f"Factory Canvas created: {path}")
        elif args.command == "evidence":
            packet, evidence_manifest = export_evidence(
                repo,
                args.plan,
                Path(args.canvas),
                args.tickets,
                Path(args.output) if args.output else None,
            )
            print(f"Evidence Packet: {packet}")
            print(f"Evidence manifest: {evidence_manifest}")
        elif args.command == "release-check":
            raise SystemExit(render_release_check(
                repo,
                rehearsal=args.rehearsal,
                live_smoke=args.live_smoke,
                confirm_disposable_repo=args.confirm_disposable_repo,
            ))
        elif args.command == "seed":
            seed_backlog(repo, args)
        elif args.command == "status":
            show_status(repo)
        elif args.command == "monitor":
            backend = None
            remote_limit = ""
            repository = session.get("github_repository")
            if repository:
                try:
                    backend = GitHubBackend(repo, repository=repository)
                    backend.preflight()
                except GitHubError as exc:
                    backend = None
                    remote_limit = str(exc)
            if args.publish and not backend:
                raise ValueError(
                    "Monitor publication requires a connected GitHub repository. "
                    + remote_limit
                )
            monitor = FactoryMonitor(repo, backend)
            report = monitor.collect()
            if remote_limit:
                report.setdefault("limitations", []).append(
                    "GitHub CI, advisory, and remote-claim monitoring was unavailable: "
                    + remote_limit
                )
            if args.publish:
                report["publication"] = monitor.publish(report)
            output = repo / ".factory/monitor/report.json"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(report, indent=2) + "\n")
            if args.as_json:
                print(json.dumps(report, indent=2))
            else:
                print(f"Monitor: {len(report['findings'])} finding(s) · read-only inspection")
                for finding in report["findings"]:
                    print(f"- {finding['severity'].upper()} {finding['summary']}: {finding['detail']}")
                print(f"Report: {output}")
        elif args.command == "retry":
            retry_ticket(repo, args.issue, args.mock, args.project_number)
        elif args.command == "release-claim":
            release_ticket_claim(
                repo,
                args.issue,
                owner_run_id=args.owner_run_id,
                reason=args.reason,
                assume_yes=args.yes,
            )
        elif args.command == "merge":
            human_merge_ticket(
                repo,
                args.issue,
                mock=args.mock,
                project_number=args.project_number,
                assume_yes=args.yes,
            )
        elif args.command == "reset":
            reset_project(
                repo, scenario=args.scenario, start_over=args.start_over,
                local_state_only=args.local_state_only,
            )
        elif args.command == "plan":
            planner_label = "deterministic fixtures" if args.mock else args.planning_agent.title()
            print(f"Planning with {planner_label}; generated tickets will use {args.default_agent.title()}.")
            plan_prd(
                repo, Path(args.prd), args.output, args.default_agent,
                args.min_tickets, args.max_tickets,
                "mock" if args.mock else args.planning_agent,
                "mock" if args.mock else resolve_planning_cli(args.planning_agent),
                args.mock,
                args.profile,
                explicit_autonomy=args.allow_autonomous_merge,
            )
        elif args.command == "review":
            review_plan(repo, args.kind, args.plan)
        elif args.command == "approve-product":
            approve_product(repo, args.plan, args.yes)
        elif args.command == "continue-plan":
            run_dir = resolve_run(repo, args.plan)
            planning_agent = args.planning_agent or load_manifest(run_dir).get("planning_agent", "codex")
            agent_bin = "mock" if args.mock or planning_agent == "mock" else resolve_planning_cli(planning_agent)
            continue_plan(
                repo, args.plan, agent_bin, args.mock,
                planning_agent_override=args.planning_agent,
            )
        elif args.command == "revise":
            run_dir = resolve_run(repo, args.plan)
            planning_agent = load_manifest(run_dir).get("planning_agent", "codex")
            agent_bin = "mock" if args.mock or planning_agent == "mock" else resolve_planning_cli(planning_agent)
            feedback_text = args.feedback
            if args.feedback_file:
                feedback_text = Path(args.feedback_file).read_text()
            revise_plan(repo, args.plan, args.stage, feedback_text, agent_bin, args.mock)
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
        elif args.command == "approve-rehearsal":
            tickets_path = approve_rehearsal(
                repo, args.plan, args.yes, args.scenario,
            )
            print(f"Approved rehearsal tickets: {tickets_path}")
            print(f"Next: ./factory/factory run --mock --scenario {args.scenario} --dry-run")
        elif args.command == "approve-tests":
            approve_qa_tests(repo, args.issue, args.yes)
        elif args.command == "doctor":
            raise SystemExit(
                run_doctor(
                    repo, load_config(repo), full=args.full,
                    implementation_agent=args.agent, qa_agent=args.qa_agent,
                    supervisor_agent=args.supervisor_agent,
                    review_agent=args.review_agent,
                    planning_agent=args.planning_agent,
                    profile_name=session.get("profile", "standard"),
                    github_repository=session.get("github_repository"),
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
