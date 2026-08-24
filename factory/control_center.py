#!/usr/bin/env python3
"""Local web control plane for the Software (re)-Factory.

The server exposes a small allowlisted API over the existing ``factory`` CLI.
It binds to loopback by default, never accepts arbitrary shell commands, and
keeps agent credentials in their normal CLI stores rather than the browser.
"""

from __future__ import annotations

import json
import mimetypes
import os
import re
import shlex
import signal
import subprocess
import sys
import threading
import time
import tomllib
import uuid
import webbrowser
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qs, urlparse

from session_config import (
    AGENT_NAME,
    FACTORY_PROFILES,
    PLANNING_AGENTS,
    PRESETS,
    load_session_config,
)
from github_repository import (
    managed_checkout_path,
    parse_github_repository,
    repository_from_remote,
)
from factory_charter import CHARTER_PATH, FactoryCharter, FactoryCharterError
from human_attention import human_attention_snapshot
from project_contract import CONTRACT_PATH, ProjectContract, ProjectContractError


PLAN_ID = re.compile(r"[a-f0-9]{8,64}")
SCENARIOS = {"recipe-rebrand", "tv"}
DEFAULT_AGENTS = {"claude", "codex", "cursor", "mock", "mock-qa", "mock-supervisor", "mock-review"}
RETRYABLE_PLANNING_STATUSES = {
    "product_approved",
    "system_architecture_approved",
    "program_design_approved",
    "blocked",
    "stale_alignment",
    "planning_system_architecture",
    "planning_program_design",
    "planning_vertical_slices",
}
REPLAN_REQUIRED_STATUSES = {
    "stale_factory_charter",
    "stale_factory_profile",
    "stale_project_contract",
    "stale_product_review",
}
REVISION_STAGE_ALIASES = {
    "product_review": "product",
    "system_architecture": "architecture",
    "program_design": "program",
    "vertical_slices": "slices",
}
MAX_BODY = 256_000
MAX_ARTIFACT = 512_000
MAX_PLANNING_FEEDBACK = 12_000
ACTION_REGISTRY = frozenset({
    "doctor", "init-project", "approve-charter", "publish-setup", "prepare-project",
    "configure", "plan", "restart-plan", "revise-product", "revise-stage",
    "approve-product", "approve-stage", "continue-plan", "publish-plan", "approve-tests", "merge",
    "run", "run-once", "dry-run", "retry", "release-claim", "evidence",
    "monitor", "publish-monitor", "reset-run", "reset-all",
})


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return default


def tail_text(path: Path, limit: int = 80_000) -> str:
    try:
        data = path.read_bytes()
    except OSError:
        return ""
    if len(data) > limit:
        return "… earlier output omitted …\n" + data[-limit:].decode("utf-8", errors="replace")
    return data.decode("utf-8", errors="replace")


def planning_blocking_stage(planning: dict) -> dict | None:
    return next(
        (
            stage for stage in planning.get("stages", [])
            if stage.get("status") == "blocked" and stage.get("questions")
        ),
        None,
    )


def planning_failed_stage(planning: dict) -> dict | None:
    """Return a failed expert stage, including failures without human questions."""
    return next(
        (stage for stage in planning.get("stages", []) if stage.get("status") == "blocked"),
        None,
    )


def planning_recovery(stage: dict | None, current_agent: str, adapters: list[str]) -> dict:
    """Describe the safe recovery for one failed planning stage.

    Retrying is deliberately not the default. Deterministic validation needs a
    correction, provider limits need time or another adapter, and login/tooling
    failures need preflight. Only an otherwise-unclassified process failure is
    eligible for an explicit same-adapter retry.
    """
    if not stage:
        return {}
    error = str(stage.get("error") or "")
    normalized = error.lower()
    alternatives = [
        name for name in adapters
        if name in PLANNING_AGENTS and name != current_agent
    ]
    attempts = max(1, int(stage.get("failure_count") or 0))
    same_failure_count = max(
        1,
        int(stage.get("same_failure_count") or 0),
        attempts if not stage.get("same_failure_count") else 0,
    )
    recommended_adapter = alternatives[0] if alternatives else ""
    if stage.get("failure_kind") == "validation":
        kind = "validation"
        summary = "The artifact must be corrected before planning can continue."
        retry_same = False
        recommended_action = "correct_and_retry"
    elif any(marker in normalized for marker in (
        "session limit", "rate limit", "usage limit", "quota exceeded",
        "too many requests", "capacity",
    )):
        kind = "provider_capacity"
        summary = (
            f"{current_agent.title() or 'The planning provider'} is unavailable or out of capacity. "
            "Retrying the same adapter now will repeat this failure."
        )
        retry_same = False
        recommended_action = "switch_adapter" if recommended_adapter else "wait"
    elif any(marker in normalized for marker in (
        "not logged in", "login required", "authentication", "unauthorized",
        "invalid api key", "missing openai api key", "api key",
    )):
        kind = "authentication"
        summary = "Repair the adapter login, then run preflight before retrying."
        retry_same = False
        recommended_action = "preflight"
    elif any(marker in normalized for marker in (
        "command not found", "no such file", "executable not found",
    )):
        kind = "adapter_setup"
        summary = "Install or configure the planning adapter, then run preflight."
        retry_same = False
        recommended_action = "preflight"
    elif same_failure_count >= 2:
        kind = "repeated_agent_failure"
        summary = (
            f"{current_agent.title() or 'The planning adapter'} failed "
            f"{same_failure_count} times with the same error. "
            "Same-agent retry is disabled; switch adapter and continue from the saved artifacts."
        )
        retry_same = False
        recommended_action = "switch_adapter" if recommended_adapter else "inspect_log"
    else:
        kind = "agent_process"
        summary = "The agent process failed unexpectedly. Inspect the log, then retry explicitly."
        retry_same = True
        recommended_action = "retry_same_adapter"
    return {
        "kind": kind,
        "summary": summary,
        "retry_same_adapter": retry_same,
        "alternative_adapters": alternatives,
        "current_adapter": current_agent,
        "recommended_action": recommended_action,
        "recommended_adapter": recommended_adapter,
        "attempts": attempts,
        "same_failure_count": same_failure_count,
    }


def planning_can_continue(planning: dict) -> bool:
    return (
        bool(planning.get("approvals", {}).get("product"))
        and planning.get("status") in RETRYABLE_PLANNING_STATUSES
        and planning_blocking_stage(planning) is None
    )


def run_text(command: list[str], cwd: Path) -> str:
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else ""


class InputError(ValueError):
    """A safe, user-visible API validation failure."""


class ControlCenter:
    def __init__(self, repo: Path):
        self.control_repo = repo.resolve()
        repository_factory = self.control_repo / "factory" / "factory"
        self.factory = (
            repository_factory if repository_factory.is_file()
            else Path(__file__).with_name("factory")
        )
        self.assets = Path(__file__).with_name("control_center")
        self.control_runtime = self.control_repo / ".factory" / "control-center"
        self.control_runtime.mkdir(parents=True, exist_ok=True)
        (self.control_repo / ".factory" / "logs").mkdir(parents=True, exist_ok=True)
        self.operation_path = self.control_runtime / "operation.json"
        self.active_repository_path = self.control_runtime / "active-repository.json"
        self.repository_root = self.control_repo / ".factory" / "repositories"
        self.lock = threading.RLock()
        self.process: subprocess.Popen | None = None
        self.worker: threading.Thread | None = None
        self._pending_activation: Path | None = None
        self._bind_repo(self._saved_active_repo() or self.control_repo)
        self.operation: dict = read_json(self.operation_path, {})
        if self.operation.get("status") in {"running", "stopping"}:
            self.operation.update(
                status="interrupted",
                finished_at=utc_now(),
                error="The control center restarted while this operation was running.",
            )
            self._save_operation()

    def _saved_active_repo(self) -> Path | None:
        raw = read_json(self.active_repository_path, {}).get("path", "")
        if not isinstance(raw, str) or not raw:
            return None
        candidate = Path(raw).resolve()
        try:
            candidate.relative_to(self.repository_root.resolve())
        except ValueError:
            return None
        return candidate if (candidate / ".git").exists() else None

    def _bind_repo(self, repo: Path):
        self.repo = repo.resolve()
        self.runtime = self.repo / ".factory" / "control-center"
        self.runtime.mkdir(parents=True, exist_ok=True)
        (self.repo / ".factory" / "logs").mkdir(parents=True, exist_ok=True)
        self.prd_path = self.runtime / "workshop-prd.md"
        self.canvas_path = self.runtime / "factory-canvas.md"

    def _activate_repo(self, repo: Path):
        candidate = repo.resolve()
        try:
            candidate.relative_to(self.repository_root.resolve())
        except ValueError as exc:
            raise InputError("Managed repository is outside the Control Center workspace.") from exc
        if not (candidate / ".git").exists():
            raise InputError(f"Managed repository checkout is missing: {candidate}")
        temp = self.active_repository_path.with_suffix(".tmp")
        temp.write_text(json.dumps({"path": str(candidate)}, indent=2) + "\n")
        os.replace(temp, self.active_repository_path)
        self._bind_repo(candidate)

    def _save_operation(self):
        temp = self.operation_path.with_suffix(".tmp")
        temp.write_text(json.dumps(self.operation, indent=2) + "\n")
        os.replace(temp, self.operation_path)

    def adapters(self) -> list[str]:
        names = set(DEFAULT_AGENTS)
        for path in (
            Path(__file__).with_name("factory.toml"),
            self.repo / "factory" / "factory.toml",
        ):
            try:
                names.update(tomllib.loads(path.read_text()).get("agents", {}))
            except (OSError, tomllib.TOMLDecodeError):
                pass
        return sorted(names)

    def repo_info(self) -> dict:
        raw_remote = run_text(["git", "remote", "get-url", "origin"], self.repo)
        remote = re.sub(r"(https?://)[^/@]+@", r"\1", raw_remote)
        branch = run_text(["git", "branch", "--show-current"], self.repo)
        dirty = bool(run_text(["git", "status", "--porcelain"], self.repo))
        connected = repository_from_remote(remote)
        configured_url = self.session_config().get("github_repository", "")
        configured = parse_github_repository(configured_url) if configured_url else None
        matches = bool(
            configured and connected and configured.slug.lower() == connected.slug.lower()
        )
        return {
            "name": self.repo.name,
            "path": str(self.repo),
            "branch": branch or "detached",
            "remote": remote,
            "github_url": configured.url if configured else (connected.url if connected else ""),
            "github_repository": configured.url if configured else "",
            "github_connected": matches,
            "dirty": dirty,
        }

    def session_config(self) -> dict:
        try:
            return load_session_config(self.repo)
        except ValueError:
            return {}

    def project_contract(self) -> dict:
        configured = (self.repo / CONTRACT_PATH).is_file()
        try:
            contract = ProjectContract.load(self.repo)
            error = ""
        except ProjectContractError as exc:
            contract = ProjectContract.detect(self.repo)
            error = str(exc)
        governed_paths = [str(CONTRACT_PATH), str(CHARTER_PATH)]
        tracked = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", *governed_paths],
            cwd=self.repo,
            text=True,
            capture_output=True,
            check=False,
        )
        unchanged = subprocess.run(
            ["git", "status", "--porcelain", "--", *governed_paths],
            cwd=self.repo,
            text=True,
            capture_output=True,
            check=False,
        )
        committed = tracked.returncode == 0 and unchanged.returncode == 0 and not unchanged.stdout.strip()
        return {
            "configured": configured,
            "valid": not error,
            "committed": committed,
            "error": error,
            "path": str(CONTRACT_PATH),
            "name": contract.name,
            "source_roots": list(contract.source_roots),
            "test_roots": list(contract.test_roots),
            "gates": [gate["name"] for gate in contract.gates],
            "required_tools": list(contract.required_tools),
            "setup_commands": list(contract.setup_commands),
        }

    def factory_charter(self) -> dict:
        configured = (self.repo / CHARTER_PATH).is_file()
        if not configured:
            return {
                "configured": False,
                "valid": False,
                "approved": False,
                "error": "Create the Project Contract and Factory Charter before planning.",
                "path": str(CHARTER_PATH),
                "policy_sha256": "",
            }
        try:
            charter = FactoryCharter.load(self.repo)
            approval_error = ""
            try:
                charter.assert_approved()
                approved = True
            except FactoryCharterError as exc:
                approved = False
                approval_error = str(exc)
            return {
                "configured": True,
                "valid": True,
                "approved": approved,
                "error": approval_error,
                "path": str(CHARTER_PATH),
                "text": (self.repo / CHARTER_PATH).read_text()[:64_000],
                "policy_sha256": charter.policy_sha256(),
                "consequence_tier": charter.consequence_tier,
                "merge_authority": charter.merge_authority,
                "gate_level": charter.gate_level,
                "planning_approvals": list(charter.planning_approvals),
                "max_awaiting_human_review": charter.max_awaiting_human_review,
                "max_blocked_for_human": charter.max_blocked_for_human,
                "oldest_review_hours": charter.oldest_review_hours,
            }
        except FactoryCharterError as exc:
            return {
                "configured": True,
                "valid": False,
                "approved": False,
                "error": str(exc),
                "path": str(CHARTER_PATH),
                "text": (self.repo / CHARTER_PATH).read_text()[:64_000],
                "policy_sha256": "",
            }

    def prd(self) -> dict:
        candidates = [
            self.repo / "PRD.md", self.repo / "prd.md",
            self.repo / "requirements.md", self.repo / "recipe-app-prd.md",
        ]
        source = self.prd_path if self.prd_path.is_file() else next(
            (path for path in candidates if path.is_file()), self.prd_path,
        )
        text = source.read_text() if source.is_file() else "# Product requirements document\n\n"
        return {
            "path": str(source.relative_to(self.repo)), "text": text,
            "saved": self.prd_path.is_file(),
        }

    def save_prd(self, text: str) -> dict:
        if not isinstance(text, str) or not text.strip():
            raise InputError("The PRD cannot be empty.")
        if len(text.encode()) > MAX_BODY:
            raise InputError("The PRD is too large for the workshop control center.")
        temp = self.prd_path.with_suffix(".tmp")
        temp.write_text(text.rstrip() + "\n")
        os.replace(temp, self.prd_path)
        return self.prd()

    def latest_plan_id(self) -> str:
        return str(read_json(self.repo / ".factory" / "plans" / "latest.json", {}).get("plan_id", ""))

    def evidence_files(self) -> list[dict]:
        candidates = []
        paths = list(self.runtime.glob("evidence-*/**/*"))
        if self.canvas_path.is_file():
            paths.append(self.canvas_path)
        for path in paths:
            if path.is_file():
                stat = path.stat()
                candidates.append({
                    "path": str(path.relative_to(self.repo)),
                    "name": path.name,
                    "size": stat.st_size,
                    "updated_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(timespec="seconds"),
                })
        return sorted(candidates, key=lambda item: item["updated_at"], reverse=True)

    def canvas(self) -> dict:
        source = self.canvas_path if self.canvas_path.is_file() else self.repo / "factory" / "FACTORY_CANVAS.md"
        text = source.read_text() if source.is_file() else "# Factory Canvas\n\n"
        return {"path": str(self.canvas_path.relative_to(self.repo)), "text": text, "saved": self.canvas_path.is_file()}

    def save_canvas(self, text: str) -> dict:
        if not isinstance(text, str) or not text.strip():
            raise InputError("The Factory Canvas cannot be empty.")
        if len(text.encode()) > MAX_BODY:
            raise InputError("The Factory Canvas is too large.")
        temp = self.canvas_path.with_suffix(".tmp")
        temp.write_text(text.rstrip() + "\n")
        os.replace(temp, self.canvas_path)
        return self.canvas()

    def operation_snapshot(self) -> dict:
        with self.lock:
            value = dict(self.operation)
        log = value.get("log")
        log_path = Path(log) if log else None
        if log_path is not None and not log_path.is_absolute():
            log_path = self.control_repo / log_path
        value["output"] = tail_text(log_path) if log_path else ""
        return value

    def journey(
        self,
        planning: dict,
        factory: dict,
        operation: dict,
        prd: dict,
        evidence: list[dict],
        config: dict | None = None,
        supervisor: dict | None = None,
        project: dict | None = None,
        charter: dict | None = None,
    ) -> dict:
        tickets = factory.get("tickets", [])
        approvals = planning.get("approvals", {})
        phase_specs = [
            ("connect", "Connect", "Choose agents and check the repository", "connect"),
            ("prd", "PRD", "Define the user outcome", "prd"),
            ("plan", "Plan", "Review expert contracts", "planning"),
            ("tickets", "Tickets", "Approve and create vertical slices", "planning"),
            ("build", "Build & verify", "Run QA, implementation, and gates", "tickets"),
            ("evidence", "Evidence", "Verify the integrated result", "evidence"),
        ]
        connected = bool(config if config is not None else self.session_config()) or bool(planning) or bool(tickets)
        project_ready = project is None or bool(project.get("configured") and project.get("valid"))
        charter_ready = charter is None or bool(charter.get("approved"))
        setup_published = (
            project is None
            or bool(project.get("committed"))
            or bool(planning)
            or bool(tickets)
        )
        prd_ready = bool(prd.get("saved")) or bool(planning)
        product_ready = bool(approvals.get("product"))
        plan_complete = planning.get("status") in {"awaiting_alignment_approval", "alignment_approved", "published"}
        tickets_approved = bool(approvals.get("alignment"))
        delivery_done = bool(tickets) and all(ticket.get("status") == "Done" for ticket in tickets)
        evidence_done = any(item.get("name") == "manifest.json" for item in evidence)
        completed = [
            connected and project_ready and charter_ready and setup_published,
            prd_ready,
            plan_complete,
            tickets_approved,
            delivery_done,
            evidence_done,
        ]

        phase_index = next((index for index, done in enumerate(completed) if not done), len(phase_specs) - 1)
        state = "ready"
        headline = "Connect this repository"
        detail = "Choose the agents for each role, then run preflight before planning."
        next_label = "Open Connect"
        next_detail = "Save a preset and fix any blocking preflight result."
        next_view = "connect"
        ticket_number = None

        active = next((ticket for ticket in tickets if ticket.get("status") in {"In Progress", "Verifying"}), None)
        qa_review = next((ticket for ticket in tickets if ticket.get("status") == "QA Review"), None)
        blocked = next((ticket for ticket in tickets if ticket.get("status") == "Blocked"), None)
        in_review = next((ticket for ticket in tickets if ticket.get("status") == "In Review"), None)
        ready = [ticket for ticket in tickets if ticket.get("status") == "Ready"]
        supervising = (supervisor or {}).get("status") == "running"
        blocked_planning = planning_blocking_stage(planning)
        failed_planning = planning_failed_stage(planning)
        failed_recovery = planning.get("recovery") or planning_recovery(
            failed_planning,
            planning.get("planning_agent") or self.session_config().get("planning_agent") or "codex",
            self.adapters(),
        )
        requires_replan = planning.get("status") in REPLAN_REQUIRED_STATUSES

        if not connected:
            pass
        elif not project_ready:
            phase_index = 0
            state = "attention"
            headline = "Define how this repository is built and verified"
            detail = "Create and review the Project Contract before any planning expert reads the repository."
            next_label, next_detail, next_view = "Create Project Contract", "Open Connect and create the detected contract and Charter draft.", "connect"
        elif not charter_ready:
            phase_index = 0
            state = "attention"
            headline = "The Factory Charter needs your approval"
            detail = "Review merge authority, gates, limits, protected paths, and stop conditions before agents can run."
            next_label, next_detail, next_view = "Review Factory Charter", "Open Connect, inspect the Charter policy, and approve its exact hash.", "connect"
        elif not setup_published:
            phase_index = 0
            state = "attention"
            headline = "Publish the approved repository setup"
            detail = "Commit and push only the Project Contract, Factory Charter, and runtime ignore before planning begins."
            next_label, next_detail, next_view = "Publish repository setup", "Open Connect and publish the reviewed governance files to the default branch.", "connect"
        elif not prd_ready:
            phase_index = 1
            headline = "Define the product outcome"
            detail = "Review or replace the sample PRD before any expert agent runs."
            next_label, next_detail, next_view = "Open the PRD", "Confirm the user, behavior, constraints, and evidence.", "prd"
        elif not planning.get("plan_id"):
            phase_index = 2
            headline = "The PRD is ready for Product Review"
            detail = "The first expert will turn the requirement into a testable product contract."
            next_label, next_detail, next_view = "Start Product Review", "Choose Rehearsal or Live agents on the PRD screen.", "prd"
        elif requires_replan:
            phase_index = 2
            state = "blocked"
            headline = "Planning governance changed"
            detail = (
                "This run was invalidated because its PRD, Project Contract, or Factory Charter "
                "no longer matches the current approved repository rules. A retry cannot repair it."
            )
            next_label = "Restart planning safely"
            next_detail = "Keep the saved PRD and regenerate the planning artifacts under the current governance."
            next_view = "planning"
        elif not product_ready:
            phase_index = 2
            product = next((stage for stage in planning.get("stages", []) if stage.get("id") == "product_review"), {})
            if product.get("status") == "complete":
                state = "attention"
                headline = "Product Review needs your decision"
                detail = "Check the problem, user journey, scope, and measurable evidence before approving it."
                next_label, next_detail, next_view = "Review Product Review", "Approve it or request a focused revision.", "planning"
            else:
                headline = "Product Review is the current planning phase"
                detail = "The product expert is preparing the behavior and evidence contract."
                next_label, next_detail, next_view = "Open Planning", "Watch the expert output and inspect its artifact.", "planning"
        elif not tickets_approved:
            if blocked_planning:
                phase_index = 2
                state = "attention"
                headline = f"{blocked_planning.get('title', 'Planning expert')} needs your decisions"
                detail = "Answer every blocking question in Planning. The expert will revise its artifact before downstream work resumes."
                next_label, next_detail, next_view = "Answer blocked questions", "Open the blocked expert, record your decisions, and continue.", "planning"
            elif failed_planning:
                phase_index = 2
                state = "blocked"
                title = failed_planning.get("title", "Planning expert")
                failure = str(failed_planning.get("error") or "").strip()
                headline = f"{title} failed validation" if failed_planning.get("failure_kind") == "validation" else f"{title} failed"
                detail = failure[:420] or "The rejected artifact and failure evidence are available in Planning."
                if failed_recovery.get("kind") == "provider_capacity":
                    next_label = "Switch planning adapter or wait"
                    next_detail = failed_recovery.get("summary", "The current provider cannot run yet.")
                elif failed_recovery.get("kind") == "validation":
                    next_label = f"Correct {title} and continue"
                    next_detail = "The revision will reuse approved upstream work and include the validator feedback."
                else:
                    next_label = "Open expert recovery"
                    next_detail = failed_recovery.get("summary", "Inspect the failure before choosing a recovery.")
                next_view = "planning"
            elif planning.get("status") == "awaiting_alignment_approval":
                phase_index = 3
                state = "attention"
                headline = "The delivery plan needs your approval"
                detail = "Architecture, program design, and vertical slices are complete. No ticket is created until you approve alignment."
                next_label, next_detail, next_view = "Review alignment", "Trace requirements through the four expert artifacts.", "planning"
            elif planning.get("status") in {
                "awaiting_system_architecture_approval",
                "awaiting_program_design_approval",
            }:
                phase_index = 2
                state = "attention"
                architecture = planning.get("status") == "awaiting_system_architecture_approval"
                title = "System Architecture" if architecture else "Program Design"
                headline = f"{title} needs your approval"
                detail = (
                    "The Factory Charter requires a person to approve this exact expert artifact "
                    "before downstream planning can continue."
                )
                next_label, next_detail, next_view = (
                    f"Review {title}",
                    "Inspect the artifact, then approve its exact hash or request a revision.",
                    "planning",
                )
            else:
                phase_index = 2
                headline = "Technical planning is ready to run"
                detail = "Architecture, program design, and vertical-slice experts run in sequence."
                next_label, next_detail, next_view = "Run remaining experts", "Open Planning and start the remaining expert stages.", "planning"
        elif not tickets:
            phase_index = 4
            headline = "Approved tickets are ready to load"
            detail = "The plan is approved. Start the factory to load the PRD-derived tickets and begin independent QA."
            next_label, next_detail, next_view = "Open Tickets", "Run one cycle to pause after the first QA proposal.", "tickets"
        elif supervising:
            phase_index = 4
            state = "running"
            headline = "The supervisor is coordinating the next dispatch wave"
            detail = "It is reading worker Handoff Receipts and dependency-ready Tickets before issuing validated instructions."
            next_label, next_detail, next_view = "Inspect supervisor", "Review its input, dispatch commands, and coordination history.", "supervisor"
        elif qa_review:
            phase_index = 4
            state = "attention"
            ticket_number = qa_review.get("number")
            headline = f"Acceptance tests need approval for #{ticket_number}"
            detail = "Implementation is paused. Inspect the Tests tab and approve only evidence that proves the ticket behavior."
            next_label, next_detail, next_view = f"Review ticket #{ticket_number}", "Open the ticket and inspect its protected tests.", "tickets"
        elif blocked:
            phase_index = 4
            state = "blocked"
            ticket_number = blocked.get("number")
            headline = f"Ticket #{ticket_number} is blocked"
            failure = str(blocked.get("failure") or "").strip()
            detail = (failure.splitlines()[-1][:420] if failure else "Read the ticket history and final log to find the recorded cause.")
            next_label, next_detail, next_view = f"Inspect blocker #{ticket_number}", "Fix the cause before retrying the ticket.", "tickets"
        elif active:
            phase_index = 4
            state = "running"
            ticket_number = active.get("number")
            ticket_phase = active.get("phase", "implementation")
            labels = {
                "qa": "Independent QA is writing acceptance tests",
                "implementation": "The implementation agent is changing the code",
                "verifying": "Quality gates are checking the change",
                "cleanup": "The cleanup agent is checking the change",
                "architecture_conformance": "Architecture conformance is being checked",
                "hardening": "The hardening agent is checking the change",
                "final_verifier": "The final verifier is checking the change",
                "code-review": "The Code Review Agent is inspecting the candidate diff",
            }
            headline = f"{labels.get(ticket_phase, 'An agent is working')} for #{ticket_number}"
            detail = f"{active.get('title', 'Ticket')} · attempt {active.get('attempt') or active.get('qa_attempt') or 1}."
            next_label, next_detail, next_view = f"Inspect ticket #{ticket_number}", "Follow its prompt, live log, diff, tests, code review, and history.", "tickets"
        elif in_review:
            phase_index = 4
            human_merge = in_review.get("merge_authority", "human") == "human"
            state = "attention" if human_merge else "running"
            ticket_number = in_review.get("number")
            headline = (
                f"Your exact-revision merge decision is required for #{ticket_number}"
                if human_merge else f"Autonomous Demo merge for #{ticket_number} is synchronizing"
            )
            detail = (
                "Verification and code review passed. Inspect the approved head and evidence, then decide whether to merge it."
                if human_merge else "The explicitly delegated demo path is synchronizing its Supervisor-authorized merge."
            )
            next_label, next_detail, next_view = f"Review ticket #{ticket_number}", "Open its exact head, review decision, gates, and merge action.", "tickets"
        elif ready:
            phase_index = 4
            headline = f"{len(ready)} ticket{'s are' if len(ready) != 1 else ' is'} ready"
            detail = "Dependencies are satisfied. The next run will dispatch QA and implementation in isolated worktrees."
            next_label, next_detail, next_view = "Run the factory", "Open Tickets and start the available work.", "tickets"
        elif delivery_done and not evidence_done:
            phase_index = 5
            headline = "Implementation is complete"
            detail = "Verify the integrated application and collect the evidence that justifies completion."
            next_label, next_detail, next_view = "Verify the result", "Complete the Factory Canvas and create the evidence packet.", "evidence"
        elif delivery_done and evidence_done:
            phase_index = 5
            state = "complete"
            headline = "The workshop run is complete"
            detail = "Planning approvals, ticket evidence, required gates, and the Evidence Packet are available for review."
            next_label, next_detail, next_view = "Review the evidence", "Inspect the packet, or start a new rehearsal when ready.", "evidence"
        else:
            phase_index = 4
            state = "attention"
            headline = "No ticket can start"
            detail = "Inspect dependencies and ticket history. A cycle or unmet dependency may be preventing progress."
            next_label, next_detail, next_view = "Inspect Tickets", "Find the first dependency that cannot be satisfied.", "tickets"

        attention = factory.get("human_attention", {})
        if attention.get("dispatch_paused"):
            phase_index = 4
            state = "attention"
            oldest = attention.get("oldest") or {}
            ticket_number = oldest.get("ticket")
            headline = "NEEDS YOU — new dispatch is paused"
            detail = (
                f"{attention.get('reason', 'Human-attention capacity is full')}. "
                "Running agents may finish, but the factory will not create more review work."
            )
            next_label = (
                f"Open oldest decision #{ticket_number}"
                if ticket_number
                else f"Open {oldest.get('status', 'planning decision')}"
            )
            next_detail = "Complete the oldest required decision to reduce the queue and resume dispatch."
            next_view = "tickets" if ticket_number else "planning"

        operation_phase = {
            "doctor": 0, "configure": 0, "plan": 2, "restart-plan": 2, "revise-product": 2, "revise-stage": 2,
            "approve-charter": 0, "publish-setup": 0, "approve-product": 2, "continue-plan": 2, "publish-plan": 3,
            "approve-tests": 4, "merge": 4, "run": 4, "run-once": 4, "dry-run": 4,
            "retry": 4, "evidence": 5, "reset-run": 4, "reset-all": 0,
            "release-claim": 4,
        }.get(operation.get("action"), phase_index)
        if operation.get("status") in {"running", "stopping"}:
            phase_index = operation_phase
            if qa_review or blocked or in_review or supervising:
                # A required human decision is more useful than the fact that the
                # scheduler process remains alive while it waits.
                pass
            elif active:
                state = "running"
            else:
                state = "running"
                headline = operation.get("title") or "Factory operation is running"
                detail = "Output is streaming in the operation console. You can inspect tickets while it runs."
                next_label, next_detail, next_view = "Watch live output", "The current command and its latest output are shown below.", "overview"
        elif operation.get("status") == "failed":
            state = "blocked"
            if requires_replan and not tickets_approved:
                phase_index = 2
                headline = "Planning governance changed"
                detail = (
                    "Retrying the old expert cannot succeed. Restart planning from the saved PRD "
                    "so every artifact is bound to the current Charter and Project Contract."
                )
                next_label, next_detail, next_view = (
                    "Restart planning safely",
                    "Open Planning and regenerate the run under the current approved governance.",
                    "planning",
                )
            elif blocked_planning and not tickets_approved:
                phase_index = 2
                headline = f"{blocked_planning.get('title', 'Planning expert')} is waiting for you"
                detail = "The agent completed its analysis and asked for decisions it cannot safely invent. Answer them in Planning."
                next_label, next_detail, next_view = "Answer blocked questions", "Open the blocked expert and submit a decision for every question.", "planning"
            elif planning_can_continue(planning) and not tickets_approved:
                phase_index = 2
                title = (failed_planning or {}).get("title", "Planning expert")
                failure = str((failed_planning or {}).get("error") or "").strip()
                headline = f"{title} failed validation" if (failed_planning or {}).get("failure_kind") == "validation" else f"{title} is blocked"
                detail = failure[:420] or "Read the failure output, then retry the blocked expert. Completed upstream artifacts will be reused."
                has_validation_feedback = bool((failed_planning or {}).get("validation_error"))
                if failed_recovery.get("kind") == "provider_capacity":
                    next_label = "Switch planning adapter or wait"
                    next_detail = failed_recovery.get("summary", "The current provider cannot run yet.")
                elif has_validation_feedback:
                    next_label = f"Retry {title} with correction"
                    next_detail = "The revision will receive the saved validator feedback and rejected artifact."
                else:
                    next_label = "Open expert recovery"
                    next_detail = failed_recovery.get("summary", "Inspect the failure before choosing a recovery.")
                next_view = "planning"
            else:
                phase_index = operation_phase
                headline = f"{operation.get('title') or 'The last operation'} failed"
                detail = operation.get("error") or "Read the final output lines to find the cause."
                next_label, next_detail, next_view = "Read the failure output", "Fix the first reported error, then repeat the action.", "overview"

        phases = []
        for index, (phase_id, label, description, view) in enumerate(phase_specs):
            status = "complete" if completed[index] else ("current" if index == phase_index else "pending")
            phases.append({"id": phase_id, "label": label, "description": description, "view": view, "status": status})
        return {
            "state": state,
            "phase_index": phase_index,
            "phase_number": phase_index + 1,
            "phase_count": len(phases),
            "phase_label": phases[phase_index]["label"],
            "headline": headline,
            "detail": detail,
            "ticket": ticket_number,
            "next": {"label": next_label, "detail": next_detail, "view": next_view},
            "phases": phases,
        }

    def snapshot(self) -> dict:
        planning = read_json(self.repo / ".factory" / "planning-state.json", {})
        plan_id = planning.get("plan_id", "")
        manifest = read_json(self.repo / ".factory" / "plans" / plan_id / "manifest.json", {}) if PLAN_ID.fullmatch(plan_id) else {}
        planning_agent = planning.get("planning_agent") or self.session_config().get("planning_agent") or "codex"
        if manifest.get("plan_id") == plan_id:
            planning_agent = manifest.get("planning_agent", "codex")
            planning["planning_agent"] = planning_agent
            planning["mode"] = "rehearsal" if planning_agent == "mock" else "live"
        blocked_stage = planning_blocking_stage(planning)
        failed_stage = planning_failed_stage(planning)
        recovery = planning_recovery(failed_stage, planning_agent, self.adapters())
        requires_correction = bool(
            failed_stage and failed_stage.get("failure_kind") == "validation"
        )
        requires_replan = planning.get("status") in REPLAN_REQUIRED_STATUSES
        planning["can_continue"] = (
            planning_can_continue(planning)
            and failed_stage is None
            and not requires_correction
            and not requires_replan
        )
        planning["requires_decisions"] = bool(blocked_stage)
        planning["requires_correction"] = requires_correction
        planning["requires_replan"] = requires_replan
        planning_status = planning.get("status", "")
        if requires_replan:
            planning["replan_reason"] = {
                "stale_factory_charter": "The approved Factory Charter changed or this run predates Charter governance.",
                "stale_factory_profile": planning.get("planning_control_error", "The proposed paths require a stronger Factory Profile."),
                "stale_project_contract": "The Project Contract or detected repository inventory changed.",
                "stale_product_review": "The PRD copy changed after Product Review.",
            }.get(planning_status, "Planning inputs changed.")
        planning["blocked_stage"] = blocked_stage.get("id", "") if blocked_stage else ""
        planning["failed_stage"] = failed_stage.get("id", "") if failed_stage else ""
        planning["recovery"] = recovery
        planning["continue_label"] = (
            "Restart planning with current governance" if requires_replan
            else "Answer expert questions" if blocked_stage
            else f"Enter a correction for {failed_stage.get('title', 'expert')}" if requires_correction
            else "Open recovery options" if failed_stage
            else "Run remaining experts" if planning_status == "product_approved"
            else "Run remaining experts" if planning_status in {
                "system_architecture_approved", "program_design_approved",
            }
            else "Review System Architecture" if planning_status == "awaiting_system_architecture_approval"
            else "Review Program Design" if planning_status == "awaiting_program_design_approval"
            else "Review Product Review" if planning_status == "awaiting_product_approval"
            else "Review alignment" if planning_status == "awaiting_alignment_approval"
            else "Planning complete" if planning_status in {"alignment_approved", "published"}
            else "Continue planning"
        )
        factory = read_json(self.repo / ".factory" / "state.json", {"tickets": []})
        operation = self.operation_snapshot()
        prd = {key: value for key, value in self.prd().items() if key != "text"}
        evidence = self.evidence_files()
        monitor = read_json(self.repo / ".factory" / "monitor" / "report.json", {})
        config = self.session_config()
        project = self.project_contract()
        charter = self.factory_charter()
        factory["human_attention"] = human_attention_snapshot(
            self.repo,
            factory.get("tickets", []),
            review_limit=charter.get("max_awaiting_human_review", 3),
            blocked_limit=charter.get("max_blocked_for_human", 2),
            oldest_limit=charter.get("oldest_review_hours", 24),
            planning=planning,
        )
        supervisor = read_json(self.repo / ".factory" / "supervisor" / "state.json", {})
        if factory.get("supervisor_agent") == "disabled" or (
            not factory.get("supervisor_agent") and config.get("profile") == "lean"
        ):
            supervisor = {"enabled": False, "status": "disabled", "events": []}
        return {
            "repo": self.repo_info(),
            "config": config,
            "project": project,
            "charter": charter,
            "adapters": self.adapters(),
            "planning": planning,
            "factory": factory,
            "supervisor": supervisor,
            "operation": operation,
            "prd": prd,
            "evidence": evidence,
            "monitor": monitor,
            "journey": self.journey(
                planning, factory, operation, prd, evidence, config, supervisor,
                project, charter,
            ),
        }

    @staticmethod
    def _string(payload: dict, key: str, *, required=False, max_length=160) -> str:
        value = payload.get(key, "")
        if value is None:
            value = ""
        if not isinstance(value, str):
            raise InputError(f"{key.replace('_', ' ').title()} must be text.")
        value = value.strip()
        if required and not value:
            raise InputError(f"{key.replace('_', ' ').title()} is required.")
        if len(value) > max_length:
            raise InputError(f"{key.replace('_', ' ').title()} is too long.")
        return value

    @staticmethod
    def _positive_int(payload: dict, key: str, *, required=False) -> int | None:
        value = payload.get(key)
        if value in (None, ""):
            if required:
                raise InputError(f"{key.replace('_', ' ').title()} is required.")
            return None
        if isinstance(value, bool):
            raise InputError(f"{key.replace('_', ' ').title()} must be a positive number.")
        try:
            number = int(value)
        except (TypeError, ValueError) as exc:
            raise InputError(f"{key.replace('_', ' ').title()} must be a positive number.") from exc
        if number < 1:
            raise InputError(f"{key.replace('_', ' ').title()} must be a positive number.")
        return number

    def _plan_id(self, payload: dict) -> str:
        value = self._string(payload, "plan_id") or self.latest_plan_id()
        if not PLAN_ID.fullmatch(value):
            raise InputError("Choose a valid planning run first.")
        return value

    def _plan_uses_mock(self, plan_id: str) -> bool:
        manifest = read_json(self.repo / ".factory" / "plans" / plan_id / "manifest.json", {})
        if manifest.get("plan_id") != plan_id:
            raise InputError("Choose a valid planning run first.")
        return manifest.get("planning_agent") == "mock"

    def _blocking_decision_feedback(
        self, payload: dict, plan_id: str, stage_id: str,
    ) -> str | None:
        """Build compact revision feedback from the current blocking decisions."""
        decisions = payload.get("decisions")
        if decisions is None:
            return None
        if not isinstance(decisions, list):
            raise InputError("Decisions must be a list of text answers.")

        planning = read_json(self.repo / ".factory" / "planning-state.json", {})
        if planning.get("plan_id") != plan_id:
            raise InputError("The selected planning run is no longer current.")
        stage = next(
            (item for item in planning.get("stages", []) if item.get("id") == stage_id),
            None,
        )
        questions = stage.get("questions", []) if isinstance(stage, dict) else []
        if not questions or stage.get("status") != "blocked":
            raise InputError("This expert does not have blocking questions to answer.")
        if len(decisions) != len(questions):
            raise InputError("Answer every current blocking question before continuing.")

        answers = []
        for index, decision in enumerate(decisions, 1):
            if not isinstance(decision, str) or not decision.strip():
                raise InputError(f"Decision {index} is required.")
            answer = decision.strip()
            if len(answer) > 4000:
                raise InputError(f"Decision {index} is too long.")
            answers.append(answer)

        feedback = "\n".join([
            f"Resolve all {len(questions)} blocking questions in the rejected "
            f"{stage.get('title') or stage_id.replace('_', ' ')} artifact using these decisions:",
            "",
            *(f"{index}. {answer}" for index, answer in enumerate(answers, 1)),
        ])
        if len(feedback) > MAX_PLANNING_FEEDBACK:
            raise InputError("The combined decisions are too long.")
        return feedback

    def _mode_flags(self, payload: dict) -> list[str]:
        if payload.get("mode", "rehearsal") != "live":
            scenario = self._string(payload, "scenario") or "recipe-rebrand"
            if scenario not in SCENARIOS:
                raise InputError("Unknown rehearsal scenario.")
            return ["--mock", "--scenario", scenario]
        return []

    def _autonomous_flags(self, payload: dict) -> list[str]:
        """Require a fresh operator delegation for every Autonomous Demo start."""
        profile = self.session_config().get("profile") or "standard"
        opted_in = payload.get("allow_autonomous_merge") is True
        if profile == "autonomous-demo":
            if not opted_in:
                raise InputError(
                    "Autonomous Demo delegates final merge accountability to the "
                    "Supervisor and orchestrator. Review the warning and explicitly opt in."
                )
            return ["--allow-autonomous-merge"]
        if opted_in:
            raise InputError(
                "Autonomous merge opt-in is valid only for the Autonomous Demo profile."
            )
        return []

    def build_commands(self, action: str, payload: dict) -> tuple[str, list[list[str]]]:
        if action not in ACTION_REGISTRY:
            raise InputError("This control-center action is not registered.")
        base = [str(self.factory)]
        self._pending_activation = None
        mode = payload.get("mode", "rehearsal")
        mock = mode != "live"
        if action == "doctor":
            return "Check readiness", [base + ["doctor"] + (["--full"] if payload.get("full") else [])]
        if action == "init-project":
            if (self.repo / CONTRACT_PATH).is_file():
                raise InputError("This repository already has a Project Contract.")
            return "Initialize Project Contract", [base + ["init", "--repo", str(self.repo)]]
        if action == "approve-charter":
            charter = self.factory_charter()
            if not charter.get("configured") or not charter.get("valid"):
                raise InputError(charter.get("error") or "Create a valid Factory Charter first.")
            if charter.get("approved"):
                raise InputError("The current Factory Charter policy is already approved.")
            return "Approve Factory Charter", [
                base + ["approve-charter", "--repo", str(self.repo), "--yes"],
            ]
        if action == "publish-setup":
            charter = self.factory_charter()
            if not charter.get("approved"):
                raise InputError("Approve the exact Factory Charter before publishing setup.")
            return "Publish repository setup", [
                base + ["publish-setup", "--repo", str(self.repo), "--yes"],
            ]
        if action == "prepare-project":
            ProjectContract.load(self.repo, require=True)
            return "Prepare project", [base + ["prepare", "--repo", str(self.repo), "--yes"]]
        if action == "configure":
            command = base + ["configure"]
            commands = []
            repository = self._string(payload, "github_repository", max_length=240)
            if mode == "live" and not repository:
                repository = self.session_config().get("github_repository", "")
            if mode == "live" and not repository:
                raise InputError("Enter the GitHub repository URL before saving Live configuration.")
            if mode == "live":
                try:
                    requested = parse_github_repository(repository)
                    repository = requested.url
                except ValueError as exc:
                    raise InputError(str(exc)) from exc
                current_remote = repository_from_remote(
                    run_text(["git", "remote", "get-url", "origin"], self.repo)
                )
                if not current_remote or current_remote.slug.lower() != requested.slug.lower():
                    target = managed_checkout_path(self.repository_root, requested)
                    commands.append([
                        str(self.factory), "checkout", repository,
                        "--workspace-root", str(self.repository_root),
                    ])
                    command += ["--repo", str(target)]
                    self._pending_activation = target
                else:
                    command += ["--repo", str(self.repo)]
                command += ["--github-repository", repository]
            preset = self._string(payload, "preset")
            if preset:
                if preset not in PRESETS:
                    raise InputError("Unknown agent preset.")
                command += ["--preset", preset]
            profile = self._string(payload, "profile")
            if profile:
                if profile not in FACTORY_PROFILES:
                    raise InputError("Unknown factory profile.")
                command += ["--profile", profile]
            known = set(self.adapters())
            for field, flag in (
                ("agent", "--agent"),
                ("qa_agent", "--qa-agent"),
                ("supervisor_agent", "--supervisor-agent"),
                ("review_agent", "--review-agent"),
            ):
                value = self._string(payload, field)
                if value:
                    if not AGENT_NAME.fullmatch(value) or value not in known:
                        raise InputError(f"Unknown {field.replace('_', ' ')} adapter.")
                    command += [flag, value]
            planning = self._string(payload, "planning_agent")
            if planning:
                if planning not in PLANNING_AGENTS:
                    raise InputError("Planning must use Claude or Codex.")
                command += ["--planning-agent", planning]
            parallel = self._positive_int(payload, "max_parallel")
            project = self._positive_int(payload, "project_number")
            if parallel:
                command += ["--max-parallel", str(parallel)]
            if project:
                command += ["--project-number", str(project)]
            if "review_qa_tests" in payload:
                command.append("--review-qa-tests" if payload["review_qa_tests"] else "--no-review-qa-tests")
            if len(command) == 2:
                raise InputError("Choose a preset or at least one configuration value.")
            return "Save factory configuration", commands + [command]
        if action == "plan":
            if not self.prd_path.is_file():
                raise InputError("Save the PRD before starting Product Review.")
            profile = self.session_config().get("profile") or "standard"
            if profile not in FACTORY_PROFILES:
                raise InputError("Unknown factory profile.")
            command = (
                base + ["plan", str(self.prd_path), "--profile", profile]
                + self._autonomous_flags(payload)
            )
            if mock:
                command.append("--mock")
            return "Run Product Review", [command]
        if action == "restart-plan":
            plan = self._plan_id(payload)
            planning = read_json(self.repo / ".factory" / "planning-state.json", {})
            if planning.get("plan_id") != plan or planning.get("status") not in REPLAN_REQUIRED_STATUSES:
                raise InputError("This planning run does not require a full restart.")
            run_dir = self.repo / ".factory" / "plans" / plan
            manifest = read_json(run_dir / "manifest.json", {})
            source_prd = self.prd_path if self.prd_path.is_file() else run_dir / "source-prd.md"
            if not source_prd.is_file():
                raise InputError("The saved PRD is missing. Save it again before restarting planning.")
            profile = self.session_config().get("profile") or manifest.get("profile") or "standard"
            if profile not in FACTORY_PROFILES:
                raise InputError("The saved factory profile is no longer available.")
            command = base + ["plan", str(source_prd), "--profile", profile]
            planning_agent = manifest.get("planning_agent", "codex")
            if planning_agent == "mock":
                command.append("--mock")
            else:
                if planning_agent not in PLANNING_AGENTS:
                    raise InputError("The saved planning adapter is no longer available.")
                command += ["--planning-agent", planning_agent]
            limits = manifest.get("ticket_limits", {})
            if isinstance(limits.get("minimum"), int):
                command += ["--min-tickets", str(limits["minimum"])]
            if isinstance(limits.get("maximum"), int):
                command += ["--max-tickets", str(limits["maximum"])]
            command += self._autonomous_flags(payload)
            return "Restart planning with current governance", [command]
        if action == "revise-product":
            plan = self._plan_id(payload)
            plan_mock = self._plan_uses_mock(plan)
            feedback = self._blocking_decision_feedback(
                payload, plan, "product_review",
            ) or self._string(
                payload, "feedback", required=True,
                max_length=MAX_PLANNING_FEEDBACK,
            )
            feedback_path = self.runtime / "product-feedback.md"
            feedback_path.write_text(feedback + "\n")
            command = base + ["revise", plan, "product", "--feedback-file", str(feedback_path)]
            if plan_mock:
                command.append("--mock")
            return "Revise Product Review", [command]
        if action == "revise-stage":
            plan = self._plan_id(payload)
            plan_mock = self._plan_uses_mock(plan)
            stage = self._string(payload, "stage", required=True)
            alias = REVISION_STAGE_ALIASES.get(stage)
            if not alias or alias == "product":
                raise InputError("Choose a blocked technical planning expert.")
            feedback = self._blocking_decision_feedback(
                payload, plan, stage,
            ) or self._string(
                payload, "feedback", required=True,
                max_length=MAX_PLANNING_FEEDBACK,
            )
            feedback_path = self.runtime / f"{stage.replace('_', '-')}-feedback.md"
            feedback_path.write_text(feedback + "\n")
            revise = base + ["revise", plan, alias, "--feedback-file", str(feedback_path)]
            resume = base + ["continue-plan", plan]
            if plan_mock:
                revise.append("--mock")
                resume.append("--mock")
            title = stage.replace("_", " ").title()
            return f"Resolve {title} decisions", [revise, resume]
        if action == "approve-product":
            return "Approve product intent", [base + ["approve-product", self._plan_id(payload), "--yes"]]
        if action == "approve-stage":
            plan = self._plan_id(payload)
            stage = self._string(payload, "stage", required=True)
            aliases = {
                "system_architecture": ("architecture", "System Architecture"),
                "program_design": ("program", "Program Design"),
            }
            if stage not in aliases:
                raise InputError("Planning stage approval must be architecture or program.")
            alias, title = aliases[stage]
            return f"Approve {title}", [
                base + ["approve-stage", alias, plan, "--yes"],
            ]
        if action == "continue-plan":
            plan = self._plan_id(payload)
            command = base + ["continue-plan", plan]
            if self._plan_uses_mock(plan):
                command.append("--mock")
            else:
                planning_agent = self._string(payload, "planning_agent")
                if planning_agent:
                    if planning_agent not in PLANNING_AGENTS:
                        raise InputError("Planning retry must use Claude or Codex.")
                    command += ["--planning-agent", planning_agent]
            return "Run architecture and delivery planning", [command]
        if action == "publish-plan":
            plan = self._plan_id(payload)
            if self._plan_uses_mock(plan):
                scenario = self._string(payload, "scenario") or "recipe-rebrand"
                if scenario not in SCENARIOS:
                    raise InputError("Unknown rehearsal scenario.")
                return "Approve rehearsal tickets", [[str(self.factory), "approve-rehearsal", plan, "--yes", "--scenario", scenario]]
            command = base + ["approve", plan, "--yes"]
            project = self._positive_int(payload, "project_number") or self.session_config().get("project_number")
            title = self._string(payload, "project_title", max_length=80)
            if project:
                command += ["--project-number", str(project)]
            elif title:
                command += ["--new-project-title", title]
            return "Publish tickets to GitHub", [command]
        if action == "approve-tests":
            issue = self._positive_int(payload, "issue", required=True)
            return f"Approve tests for ticket #{issue}", [base + ["approve-tests", str(issue), "--yes"]]
        if action == "merge":
            issue = self._positive_int(payload, "issue", required=True)
            command = base + ["merge", str(issue), "--repo", str(self.repo), "--yes"]
            if mock:
                command.append("--mock")
            project = self._positive_int(payload, "project_number") or self.session_config().get("project_number")
            if project and not mock:
                command += ["--project-number", str(project)]
            return f"Merge exact revision for ticket #{issue}", [command]
        if action in {"run", "run-once", "dry-run"}:
            command = (
                base + ["run"] + self._mode_flags(payload)
                + self._autonomous_flags(payload)
            )
            if action == "run-once":
                command.append("--once")
            elif action == "dry-run":
                command.append("--dry-run")
            if payload.get("review_qa_tests"):
                command.append("--review-qa-tests")
            return {"run": "Run the factory", "run-once": "Run one scheduling cycle", "dry-run": "Preview execution waves"}[action], [command]
        if action == "retry":
            issue = self._positive_int(payload, "issue", required=True)
            command = base + ["retry", str(issue)]
            if mock:
                command.append("--mock")
            return f"Retry ticket #{issue}", [command]
        if action == "release-claim":
            if mock:
                raise InputError("Rehearsal Tickets do not use remote claims.")
            issue = self._positive_int(payload, "issue", required=True)
            owner = self._string(payload, "owner_run_id", required=True, max_length=64)
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", owner):
                raise InputError("The recorded claim owner is invalid.")
            reason = self._string(payload, "reason", required=True, max_length=300)
            return f"Release abandoned claim for ticket #{issue}", [[
                str(self.factory), "release-claim", str(issue),
                "--repo", str(self.repo),
                "--owner-run-id", owner,
                "--reason", reason,
                "--yes",
            ]]
        if action == "evidence":
            plan = self._plan_id(payload)
            if not self.canvas_path.is_file():
                raise InputError("Complete and save the Factory Canvas before exporting evidence.")
            output = self.runtime / f"evidence-{plan}"
            return "Create evidence packet", [
                base + ["evidence", plan, "--canvas", str(self.canvas_path), "--output", str(output)],
            ]
        if action in {"monitor", "publish-monitor"}:
            command = base + ["monitor", "--repo", str(self.repo), "--json"]
            if action == "publish-monitor":
                if mock:
                    raise InputError("Monitor publication requires a connected Live GitHub repository.")
                command.append("--publish")
                return "Publish monitor findings", [command]
            return "Preview repository health", [command]
        if action in {"reset-run", "reset-all"}:
            local_only = payload.get("local_only") is True
            if mode == "live" and not local_only:
                raise InputError("Live GitHub runs cannot be reset safely. Use a fresh workshop repository.")
            scenario = self._string(payload, "scenario") or "recipe-rebrand"
            if scenario not in SCENARIOS:
                raise InputError("Unknown rehearsal scenario.")
            command = [str(self.factory), "reset", "--repo", str(self.repo), "--scenario", scenario]
            if local_only:
                command.append("--local-state-only")
            if action == "reset-all":
                if self._string(payload, "confirm") != "START OVER":
                    raise InputError("Type START OVER to clear the workshop run.")
                command.append("--start-over")
                title = "Clear local Live Run state" if mode == "live" else "Start the workshop over"
                return title, [command]
            title = "Reset local Live Run state" if mode == "live" else "Reset ticket execution"
            return title, [command]
        raise InputError("This control-center action is not available.")

    def start(self, action: str, payload: dict) -> dict:
        title, commands = self.build_commands(action, payload)
        activation = self._pending_activation
        self._pending_activation = None
        operation_repo = self.repo
        with self.lock:
            if self.operation.get("status") in {"running", "stopping"} or (
                self.process and self.process.poll() is None
            ):
                raise InputError("Another factory operation is already running.")
            operation_id = uuid.uuid4().hex[:12]
            log = self.control_repo / ".factory" / "logs" / f"control-center-{operation_id}.log"
            self.operation = {
                "id": operation_id,
                "action": action,
                "title": title,
                "status": "running",
                "started_at": utc_now(),
                "finished_at": "",
                "exit_code": None,
                "command": " && ".join(shlex.join(command) for command in commands),
                "log": str(log),
                "error": "",
            }
            if activation is not None:
                self.operation["target_repo"] = str(activation)
            self._save_operation()
        worker = threading.Thread(
            target=self._run,
            args=(commands, log, operation_repo, activation),
            daemon=True,
        )
        with self.lock:
            self.worker = worker
        worker.start()
        return self.operation_snapshot()

    def _run(
        self,
        commands: list[list[str]],
        log: Path,
        operation_repo: Path,
        activation: Path | None,
    ):
        exit_code = 0
        failure = ""
        try:
            with log.open("w") as stream:
                for command in commands:
                    stream.write("$ " + shlex.join(command) + "\n\n")
                    stream.flush()
                    with self.lock:
                        self.process = subprocess.Popen(
                            command,
                            cwd=operation_repo,
                            text=True,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            start_new_session=True,
                            env={**os.environ, "PYTHONUNBUFFERED": "1"},
                        )
                        process = self.process
                        should_stop = self.operation.get("status") == "stopping"
                    if should_stop:
                        os.killpg(process.pid, signal.SIGTERM)
                    assert process.stdout is not None
                    for line in process.stdout:
                        stream.write(line)
                        stream.flush()
                    process.stdout.close()
                    exit_code = process.wait()
                    if exit_code:
                        break
        except (OSError, subprocess.SubprocessError) as exc:
            exit_code = 127
            failure = f"Could not start the factory command: {exc}"
        finally:
            with self.lock:
                status = "stopped" if self.operation.get("status") == "stopping" else ("succeeded" if exit_code == 0 else "failed")
                if status == "succeeded" and activation is not None:
                    try:
                        self._activate_repo(activation)
                    except InputError as exc:
                        status = "failed"
                        exit_code = 1
                        failure = str(exc)
                self.operation.update(status=status, finished_at=utc_now(), exit_code=exit_code)
                if failure:
                    self.operation["error"] = failure
                elif exit_code and status != "stopped":
                    self.operation["error"] = "The operation failed. Read the final log lines for the cause."
                self.process = None
                self.worker = None
                self._save_operation()

    def stop(self) -> dict:
        with self.lock:
            process = self.process
            if self.operation.get("status") != "running":
                raise InputError("No factory operation is running.")
            self.operation["status"] = "stopping"
            self._save_operation()
            if process and process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
        return self.operation_snapshot()

    def shutdown(self, timeout: float = 5.0):
        """Stop and join the active factory command before closing the server."""
        with self.lock:
            worker = self.worker
            process = self.process
            if self.operation.get("status") in {"running", "stopping"}:
                self.operation["status"] = "stopping"
                self._save_operation()
            if process and process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
        if worker and worker is not threading.current_thread():
            worker.join(timeout=timeout)
        with self.lock:
            process = self.process
        if process and process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            if worker and worker is not threading.current_thread():
                worker.join(timeout=1)

    def artifact(self, raw_path: str) -> str:
        path = PurePosixPath(raw_path)
        if path.is_absolute() or ".." in path.parts:
            raise InputError("Invalid artifact path.")
        normalized = path.as_posix()
        if normalized.startswith("./"):
            normalized = normalized[2:]
        allowed = (
            ".factory/logs/",
            ".factory/prompts/",
            ".factory/receipts/",
            ".factory/reviews/",
            ".factory/plans/",
            ".factory/control-center/",
        )
        if not normalized.startswith(allowed):
            raise InputError("Only factory evidence artifacts can be opened.")
        target = (self.repo / normalized).resolve()
        allowed_roots = [
            (self.repo / prefix.rstrip("/")).resolve()
            for prefix in allowed
        ]
        if not any(target.is_relative_to(root) for root in allowed_roots) or not target.is_file():
            raise InputError("Artifact not found.")
        data = target.read_bytes()
        if len(data) > MAX_ARTIFACT:
            data = data[-MAX_ARTIFACT:]
            return "… earlier content omitted …\n" + data.decode("utf-8", errors="replace")
        return data.decode("utf-8", errors="replace")

    def ticket_diff(self, issue: int) -> str:
        state = read_json(self.repo / ".factory" / "state.json", {"tickets": []})
        ticket = next((item for item in state.get("tickets", []) if int(item.get("number", -1)) == issue), None)
        if not ticket:
            raise InputError(f"Ticket #{issue} was not found.")
        worktree = self.repo.parent / f"{self.repo.name}-wt-{issue}"
        base = ticket.get("base_sha")
        branch = ticket.get("branch")
        cwd = worktree if worktree.is_dir() else self.repo
        target = "HEAD" if worktree.is_dir() else branch
        if (
            not isinstance(base, str)
            or not re.fullmatch(r"[a-f0-9]{7,64}", base)
            or not isinstance(target, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,255}", target)
        ):
            return "A Git diff is not available yet."
        command = ["git", "diff", "--no-ext-diff", "--unified=3", f"{base}..{target}", "--"]
        result = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
        if result.returncode:
            return result.stderr.strip() or "The ticket branch is no longer available."
        value = result.stdout
        return value[-MAX_ARTIFACT:] if len(value) > MAX_ARTIFACT else (value or "No committed changes yet.")


class Handler(BaseHTTPRequestHandler):
    server: "ControlCenterServer"

    def log_message(self, format, *args):
        return

    def _json(self, value, status=HTTPStatus.OK):
        data = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def _error(self, exc: Exception, status=HTTPStatus.BAD_REQUEST):
        self._json({"error": str(exc)}, status)

    def _payload(self) -> dict:
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise InputError("Invalid request length.") from exc
        if size > MAX_BODY:
            raise InputError("Request is too large.")
        try:
            value = json.loads(self.rfile.read(size) or b"{}")
        except json.JSONDecodeError as exc:
            raise InputError("Request must contain valid JSON.") from exc
        if not isinstance(value, dict):
            raise InputError("Request body must be an object.")
        return value

    def _trusted_request(self):
        host = self.headers.get("Host", "").split(":", 1)[0].strip("[]").lower()
        if host not in {"127.0.0.1", "localhost"}:
            raise InputError("The Control Center accepts requests only from this computer.")
        origin = self.headers.get("Origin")
        if origin:
            origin_host = urlparse(origin).hostname
            if origin_host not in {"127.0.0.1", "localhost"}:
                raise InputError("Cross-origin Control Center requests are not allowed.")

    def do_GET(self):
        parsed = urlparse(self.path)
        try:
            self._trusted_request()
            if parsed.path == "/api/snapshot":
                return self._json(self.server.center.snapshot())
            if parsed.path == "/api/prd":
                return self._json(self.server.center.prd())
            if parsed.path == "/api/canvas":
                return self._json(self.server.center.canvas())
            if parsed.path == "/api/artifact":
                raw = parse_qs(parsed.query).get("path", [""])[0]
                return self._json({"path": raw, "content": self.server.center.artifact(raw)})
            match = re.fullmatch(r"/api/tickets/(\d+)/diff", parsed.path)
            if match:
                issue = int(match.group(1))
                return self._json({"issue": issue, "content": self.server.center.ticket_diff(issue)})
            if parsed.path == "/api/events":
                return self._events()
            return self._asset(parsed.path)
        except InputError as exc:
            return self._error(exc)
        except Exception as exc:  # pragma: no cover - last-resort HTTP boundary
            return self._error(exc, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_PUT(self):
        try:
            self._trusted_request()
            if self.path == "/api/prd":
                return self._json(self.server.center.save_prd(self._payload().get("text")))
            if self.path == "/api/canvas":
                return self._json(self.server.center.save_canvas(self._payload().get("text")))
            return self._error(InputError("Unknown endpoint."), HTTPStatus.NOT_FOUND)
        except InputError as exc:
            return self._error(exc)

    def do_POST(self):
        parsed = urlparse(self.path)
        try:
            self._trusted_request()
            if parsed.path == "/api/stop":
                return self._json(self.server.center.stop(), HTTPStatus.ACCEPTED)
            match = re.fullmatch(r"/api/actions/([a-z-]+)", parsed.path)
            if match:
                return self._json(self.server.center.start(match.group(1), self._payload()), HTTPStatus.ACCEPTED)
            return self._error(InputError("Unknown endpoint."), HTTPStatus.NOT_FOUND)
        except InputError as exc:
            return self._error(exc)

    def _events(self):
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        previous = ""
        last_write = 0.0
        try:
            while True:
                data = json.dumps(self.server.center.snapshot())
                current = time.monotonic()
                if data != previous:
                    self.wfile.write(f"data: {data}\n\n".encode())
                    previous = data
                    last_write = current
                    self.wfile.flush()
                elif current - last_write >= 15:
                    self.wfile.write(b": keepalive\n\n")
                    last_write = current
                    self.wfile.flush()
                time.sleep(1)
        except (BrokenPipeError, ConnectionResetError):
            return

    def _asset(self, path: str):
        name = "index.html" if path in {"", "/"} else path.lstrip("/")
        pure = PurePosixPath(name)
        if pure.is_absolute() or ".." in pure.parts:
            return self._error(InputError("Invalid asset path."), HTTPStatus.NOT_FOUND)
        target = (self.server.center.assets / pure).resolve()
        if not target.is_relative_to(self.server.center.assets) or not target.is_file():
            return self._error(InputError("Page not found."), HTTPStatus.NOT_FOUND)
        data = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(data)


class ControlCenterServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, center: ControlCenter):
        super().__init__(address, Handler)
        self.center = center

    def handle_error(self, request, client_address):
        if isinstance(sys.exc_info()[1], (BrokenPipeError, ConnectionResetError)):
            return
        super().handle_error(request, client_address)


def serve(repo: Path, host="127.0.0.1", port=5050, open_browser=True):
    if host not in {"127.0.0.1", "localhost"}:
        raise InputError("The unauthenticated Control Center must bind to localhost.")
    center = ControlCenter(repo)
    server = ControlCenterServer((host, port), center)
    url = f"http://{host}:{server.server_port}"
    print(f"Factory Control Center: {url}", flush=True)
    print("Press Ctrl+C to stop.", flush=True)
    if open_browser:
        threading.Timer(0.35, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        center.shutdown()
        server.server_close()
