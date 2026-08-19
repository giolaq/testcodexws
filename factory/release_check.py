"""Local checks required before publishing a workshop release."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

from factory_contracts import WORKSHOP_VERSION
from sensitive_data import contains_credentials


VERSION_FILES = (
    "factory/factory_contracts.py",
    "factory/WORKSHOP_OUTLINE.md",
    "factory/FACILITATOR.md",
    "workshop-guide/app/page.tsx",
)
GENERATED_PARTS = {"__pycache__", ".pytest_cache", ".next", "dist", ".wrangler"}
GENERATED_PREFIXES = (".factory/", "workshop-guide/node_modules/")
_OBSOLETE_TERMS = (
    "lights" + r"[- ]off",
    "control" + " experiment",
    "run_" + "lights_off",
    "two delivery" + " systems",
)
OBSOLETE_PATTERN = re.compile("|".join(_OBSOLETE_TERMS), re.IGNORECASE)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, text=True, capture_output=True,
    )
    if result.returncode:
        raise ValueError(result.stderr.strip() or "not a Git repository")
    return result.stdout


def _tracked_files(repo: Path) -> list[str]:
    return [value for value in _git(repo, "ls-files", "-z").split("\0") if value]


def audit_release(repo: Path) -> tuple[list[str], list[str]]:
    """Return local failures and the remaining publication checklist."""
    failures: list[str] = []
    manual = [
        "Run `factory release-check --rehearsal` from the frozen checkout.",
        "Run `factory release-check --live-smoke --confirm-disposable-repo` in a disposable GitHub repository with Claude configured.",
        "Check participant-facing links from the frozen checkout.",
        "Verify the deployed website displays the frozen workshop version.",
        f"Create and verify Git tag {WORKSHOP_VERSION}, then enable public/template settings.",
    ]
    tracked = _tracked_files(repo)
    dirty = _git(repo, "status", "--porcelain").strip()
    if dirty:
        failures.append("working tree is not clean")

    for raw in tracked:
        path = Path(raw)
        if raw.startswith(GENERATED_PREFIXES) or any(part in GENERATED_PARTS for part in path.parts):
            failures.append(f"generated or local state is tracked: {raw}")

    for raw in tracked:
        path = repo / raw
        if not path.is_file() or path.stat().st_size > 1_000_000:
            continue
        try:
            text = path.read_text()
        except UnicodeDecodeError:
            continue
        if contains_credentials(text):
            failures.append(f"possible credential in tracked file: {raw}")
        participant_surface = (
            raw == "README.md"
            or (raw.startswith("factory/") and raw.endswith(".md"))
            or raw.startswith("workshop-guide/app/")
        )
        if participant_surface and OBSOLETE_PATTERN.search(text):
            failures.append(f"obsolete control language remains: {raw}")

    for raw in VERSION_FILES:
        path = repo / raw
        if raw not in tracked or not path.is_file():
            failures.append(f"version identity file is missing or untracked: {raw}")
        elif WORKSHOP_VERSION not in path.read_text():
            failures.append(f"{raw} does not display {WORKSHOP_VERSION}")
    return list(dict.fromkeys(failures)), manual


def _checked(command: list[str], cwd: Path, timeout: int | None = 180) -> str:
    result = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    if result.returncode:
        rendered = " ".join(command)
        raise RuntimeError(f"{rendered}\n{result.stdout}{result.stderr}".strip())
    return result.stdout


def _write_completed_canvas(repo: Path, name: str) -> Path:
    path = repo / ".factory" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("""# Factory Canvas

Version: 1

## Use case
Validate one bounded software-factory delivery path before workshop release.

## Factory Profile
Standard, because the change needs independent Acceptance Tests and human review.

## Agent Roles
Product, architecture, program design, slices, QA, implementation, verification, and review.

## Human Gates
Product intent, alignment, Acceptance Tests, and pull-request merge.

## Execution environment
An isolated Git worktree in a disposable clean checkout or GitHub repository.

## Required evidence
Planning trace, protected tests, successful gates, receipts, links, and the sanitized packet.

## Recovery policy
Retry bounded deterministic failures; block unresolved live failures for diagnosis.

## First Vertical Slice
One user-visible change traced from the PRD through merged evidence.

## Peer review
The release owner reviews this automated Canvas with the frozen workshop checklist.
""")
    return path


def _export_and_validate_evidence(
    repo: Path,
    factory: list[str],
    plan_id: str,
    canvas: Path,
    expected_links: list[str] | None = None,
) -> tuple[Path, Path]:
    _checked([
        *factory,
        "evidence",
        plan_id,
        "--canvas",
        str(canvas.relative_to(repo)),
    ], repo, timeout=None)
    output = repo / ".factory/evidence" / plan_id
    packet_path = output / "evidence-packet.md"
    manifest_path = output / "manifest.json"
    if not packet_path.is_file() or not manifest_path.is_file():
        raise RuntimeError("Evidence Packet or integrity manifest was not exported")
    packet = packet_path.read_text()
    evidence_manifest = json.loads(manifest_path.read_text())
    if contains_credentials(packet + manifest_path.read_text()):
        raise RuntimeError("Evidence Packet contains a possible credential")
    actual_hash = hashlib.sha256(packet.encode()).hexdigest()
    if evidence_manifest.get("packet_sha256") != actual_hash:
        raise RuntimeError("Evidence Packet hash does not match its manifest")
    for link in expected_links or []:
        if link not in packet:
            raise RuntimeError(f"Evidence Packet is missing delivery link: {link}")
    if "## Factory Canvas" not in packet or "## Handoff Receipts" not in packet:
        raise RuntimeError("Evidence Packet is missing the Canvas or Handoff Receipts")
    return packet_path, manifest_path


def validate_standard_rehearsal(manifest: dict, state: dict) -> list[str]:
    """Return failures for the observable Standard workshop journey."""
    failures = []
    approvals = manifest.get("approvals", {})
    if not approvals.get("product"):
        failures.append("Product Review approval was not recorded")
    if not approvals.get("alignment"):
        failures.append("alignment approval was not recorded")
    if not manifest.get("revisions"):
        failures.append("Product Review rejection and revision were not recorded")
    if not manifest.get("rehearsal", {}).get("tickets_path"):
        failures.append("approved Vertical Slices were not materialized for rehearsal")
    tickets = state.get("tickets", [])
    if not tickets or any(ticket.get("status") != "Done" for ticket in tickets):
        failures.append("not every rehearsal ticket reached Done")
    retry = next((ticket for ticket in tickets if ticket.get("number") == 3), None)
    if not retry or retry.get("attempt") != 2:
        failures.append("the deterministic mobile ticket did not demonstrate one retry")
    required_roles = {"qa", "implementation", "verification", "human_review"}
    for ticket in tickets:
        number = ticket.get("number", "?")
        roles = {receipt.get("role") for receipt in ticket.get("_loaded_receipts", [])}
        missing_roles = sorted(required_roles - roles)
        if missing_roles:
            failures.append(
                f"ticket #{number} is missing Standard role receipts: {', '.join(missing_roles)}"
            )
        gates = ticket.get("gate_results", [])
        if not gates:
            failures.append(f"ticket #{number} has no verification gate results")
        required_gates = [gate for gate in gates if gate.get("required")]
        if gates and not required_gates:
            failures.append(f"ticket #{number} has no required verification gate result")
        failed_required = [
            gate.get("name", "unnamed")
            for gate in required_gates
            if gate.get("exit_code") != 0
        ]
        if failed_required:
            failures.append(
                f"ticket #{number} has failed required gates: {', '.join(failed_required)}"
            )
    return failures


def run_clean_standard_rehearsal(repo: Path) -> str:
    """Clone committed HEAD and execute the complete deterministic Standard path."""
    with tempfile.TemporaryDirectory(prefix="factory-release-") as directory:
        checkout = Path(directory) / "checkout"
        _checked(["git", "clone", "--local", "--no-hardlinks", str(repo), str(checkout)], repo)
        _checked(["git", "config", "user.name", "Factory Release Check"], checkout)
        _checked(["git", "config", "user.email", "factory-release@example.invalid"], checkout)
        _checked(["git", "rev-parse", "--verify", "factory-baseline^{commit}"], checkout)
        _checked(["git", "restore", "--source=factory-baseline", "--staged", "--worktree", "--", "demo-app"], checkout)
        if _git(checkout, "status", "--porcelain", "--", "demo-app").strip():
            _checked(["git", "commit", "-m", "chore: reset release rehearsal baseline"], checkout)

        factory = [sys.executable, "factory/orchestrator.py"]
        _checked([*factory, "plan", "recipe-app-prd.md", "--mock"], checkout)
        latest = json.loads((checkout / ".factory/plans/latest.json").read_text())
        plan_id = latest["plan_id"]
        _checked([
            *factory,
            "revise",
            plan_id,
            "product",
            "--feedback",
            "Require automated Escape and Backspace checks that preserve mode=tv and restore focus.",
            "--mock",
        ], checkout)
        _checked([*factory, "review", "product", plan_id], checkout)
        _checked([*factory, "approve-product", plan_id, "--yes"], checkout)
        _checked([*factory, "continue-plan", plan_id, "--mock"], checkout)
        _checked([*factory, "review", "alignment", plan_id], checkout)
        _checked([*factory, "approve-rehearsal", plan_id, "--yes"], checkout)
        _checked([
            *factory,
            "run",
            "--mock",
            "--scenario",
            "recipe-rebrand",
            "--profile",
            "standard",
            "--max-parallel",
            "1",
            "--once",
        ], checkout, timeout=300)

        plan_dir = checkout / ".factory/plans" / plan_id
        manifest = json.loads((plan_dir / "manifest.json").read_text())
        state = json.loads((checkout / ".factory/state.json").read_text())
        for ticket in state.get("tickets", []):
            ticket["_loaded_receipts"] = [
                json.loads((checkout / reference).read_text())
                for reference in ticket.get("receipts", [])
                if (checkout / reference).is_file()
            ]
        failures = validate_standard_rehearsal(manifest, state)
        if failures:
            raise RuntimeError("; ".join(failures))
        canvas = _write_completed_canvas(checkout, "release-rehearsal-canvas.md")
        packet, _ = _export_and_validate_evidence(checkout, factory, plan_id, canvas)
        return (
            f"Standard Rehearsal PASS ({plan_id}, {len(state['tickets'])} tickets, "
            f"{packet.relative_to(checkout)})"
        )


def run_live_github_smoke(repo: Path, confirmed: bool) -> str:
    """Exercise the Claude golden path in an explicitly disposable GitHub repo."""
    if not confirmed:
        raise ValueError("live smoke requires --confirm-disposable-repo")
    if not shutil.which("gh"):
        raise RuntimeError("GitHub CLI is required for the live smoke test")

    from github_backend import GitHubBackend

    backend = GitHubBackend(repo)
    backend.preflight()
    run_id = uuid.uuid4().hex[:10]
    repository = f"{backend.owner}/{backend.name}"
    factory = [sys.executable, "factory/orchestrator.py"]
    _checked([
        *factory,
        "doctor",
        "--full",
        "--planning-agent",
        "claude",
        "--agent",
        "claude",
        "--qa-agent",
        "claude",
    ], repo, timeout=None)
    prd = repo / ".factory" / f"live-smoke-{run_id}.md"
    prd.parent.mkdir(parents=True, exist_ok=True)
    prd.write_text("""# Factory live smoke

## Problem
The release needs objective proof that the external Claude delivery path works.

## Desired behavior
Add one reversible `GET /api/factory-smoke` endpoint to the demo application.
It returns JSON with exactly `status: ready` and does not change existing routes.

## Scope
Implement and test only this endpoint. Keep the change offline and deterministic.

## Success evidence
An independent Acceptance Test proves the status code, JSON payload, and an existing route regression.
The implementation passes every configured gate and is merged through a pull request.
""")
    _checked([
        *factory,
        "plan",
        str(prd.relative_to(repo)),
        "--profile",
        "standard",
        "--planning-agent",
        "claude",
        "--default-agent",
        "claude",
        "--min-tickets",
        "1",
        "--max-tickets",
        "1",
    ], repo, timeout=None)
    plan_id = json.loads((repo / ".factory/plans/latest.json").read_text())["plan_id"]
    _checked([*factory, "review", "product", plan_id], repo, timeout=None)
    _checked([*factory, "approve-product", plan_id, "--yes"], repo, timeout=None)
    _checked([*factory, "continue-plan", plan_id], repo, timeout=None)
    _checked([*factory, "review", "alignment", plan_id], repo, timeout=None)
    project_title = f"Factory release smoke {run_id}"
    _checked([
        *factory,
        "approve",
        plan_id,
        "--new-project-title",
        project_title,
        "--yes",
    ], repo, timeout=None)
    slices_path = repo / ".factory/plans" / plan_id / "04-vertical-slices.json"
    slices = json.loads(slices_path.read_text())
    publication = slices.get("publication", {})
    if not publication.get("project_number") or len(publication.get("issues", {})) != 1:
        raise RuntimeError("live smoke did not create a Project and publish one planned Ticket")
    number = next(iter(publication["issues"].values()))

    run_command = [
        *factory,
        "run",
        "--profile",
        "standard",
        "--agent",
        "claude",
        "--qa-agent",
        "claude",
        "--review-qa-tests",
        "--max-parallel",
        "1",
        "--once",
    ]
    _checked(run_command, repo, timeout=None)
    state_path = repo / ".factory/state.json"
    state = json.loads(state_path.read_text())
    ticket = next(item for item in state["tickets"] if item["number"] == number)
    if ticket.get("status") != "QA Review" or not ticket.get("qa_tests"):
        raise RuntimeError("Claude QA did not produce protected Acceptance Tests for review")
    _checked([*factory, "approve-tests", str(number), "--yes"], repo, timeout=None)
    _checked(run_command, repo, timeout=None)
    state = json.loads(state_path.read_text())
    ticket = next(item for item in state["tickets"] if item["number"] == number)
    issue_url = ticket.get("issue_url", "")
    pr_url = ticket.get("pr_url", "")
    if ticket.get("status") != "In Review" or not issue_url or not pr_url:
        raise RuntimeError("Claude implementation did not reach pull-request review")
    receipt_roles = {
        json.loads((repo / reference).read_text()).get("role")
        for reference in ticket.get("receipts", [])
        if (repo / reference).is_file()
    }
    if not {"qa", "implementation", "verification", "human_review"} <= receipt_roles:
        raise RuntimeError("live smoke is missing required Handoff Receipts")
    _checked([
        "gh", "pr", "merge", pr_url, "--repo", repository, "--merge", "--delete-branch",
    ], repo, timeout=None)
    _checked(run_command, repo, timeout=None)
    state = json.loads(state_path.read_text())
    ticket = next(item for item in state["tickets"] if item["number"] == number)
    if ticket.get("status") != "Done":
        raise RuntimeError("merged pull request did not synchronize to Done")
    canvas = _write_completed_canvas(repo, f"live-smoke-{run_id}-canvas.md")
    packet, _ = _export_and_validate_evidence(
        repo, factory, plan_id, canvas, [issue_url, pr_url],
    )
    return (
        f"Claude live GitHub smoke PASS (Project #{publication['project_number']}, "
        f"issue #{number}, {pr_url}, {packet.relative_to(repo)})"
    )


def render_release_check(
    repo: Path,
    *,
    rehearsal: bool = False,
    live_smoke: bool = False,
    confirm_disposable_repo: bool = False,
) -> int:
    failures, manual = audit_release(repo)
    results = []
    if not failures and rehearsal:
        try:
            results.append(run_clean_standard_rehearsal(repo))
        except Exception as exc:
            failures.append(f"clean Standard Rehearsal failed: {exc}")
    if not failures and live_smoke:
        try:
            results.append(run_live_github_smoke(repo, confirm_disposable_repo))
        except Exception as exc:
            failures.append(f"live GitHub smoke failed: {exc}")
    if failures:
        print("Local release audit: FAIL")
        for failure in failures:
            print(f"- {failure}")
    else:
        print(f"Local release audit: PASS ({WORKSHOP_VERSION})")
    for result in results:
        print(f"- {result}")
    print("\nRelease checklist:")
    for item in manual:
        print(f"- {item}")
    return 1 if failures else 0
