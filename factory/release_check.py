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
MARKDOWN_LINK_PATTERN = re.compile(r"!?\[[^\]]*\]\((?:<)?([^)>\s]+)(?:>)?\)")
WEBSITE_ASSET_PATTERN = re.compile(r'(?:src|href)=["\']/(?!/)([^"\'?#]+)')


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, text=True, capture_output=True,
    )
    if result.returncode:
        raise ValueError(result.stderr.strip() or "not a Git repository")
    return result.stdout


def _tracked_files(repo: Path) -> list[str]:
    return [value for value in _git(repo, "ls-files", "-z").split("\0") if value]


def participant_link_failures(repo: Path, tracked: list[str]) -> list[str]:
    """Check local participant links without requiring network access."""
    failures = []
    for raw in tracked:
        participant_markdown = (
            raw == "README.md"
            or raw == "workshop-guide/README.md"
            or (raw.startswith("factory/") and raw.endswith(".md"))
        )
        if not participant_markdown:
            continue
        source = repo / raw
        if not source.is_file():
            continue
        for link in MARKDOWN_LINK_PATTERN.findall(source.read_text()):
            if link.startswith(("http://", "https://", "mailto:", "#")):
                continue
            target = link.split("#", 1)[0].split("?", 1)[0]
            if not target:
                continue
            candidate = (source.parent / target).resolve()
            try:
                candidate.relative_to(repo.resolve())
            except ValueError:
                failures.append(f"participant link escapes repository: {raw} -> {link}")
                continue
            if not candidate.exists():
                failures.append(f"broken participant link: {raw} -> {link}")
    page = repo / "workshop-guide/app/page.tsx"
    if page.is_file():
        for asset in WEBSITE_ASSET_PATTERN.findall(page.read_text()):
            candidate = repo / "workshop-guide/public" / asset
            if not candidate.is_file():
                failures.append(f"missing website asset: /{asset}")
    return failures


def audit_release(repo: Path) -> tuple[list[str], list[str]]:
    """Return local failures and the remaining publication checklist."""
    failures: list[str] = []
    manual = [
        "Run the full Python suite plus website build, tests, structural accessibility checks, and lint.",
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
    failures.extend(participant_link_failures(repo, tracked))
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

Version: 2

## Use case
Validate one bounded software-factory delivery path before workshop release.

## Factory Profile
Standard, because the change needs independent Acceptance Tests, code-review rework, and a revision-bound merge.

## Consequence tier
Shared workshop behavior with reversible but attendee-visible failure.

## Merge authority
The release owner performs the exact-revision human merge.

## Review capacity
At most three human decisions wait; the oldest decision is handled first.

## Load-bearing paths
Factory policy, orchestration, tests, and attendee instructions require full verification.

## Gate budget
Use full gates for the core path and deep gates only for selected release risks.

## Durable remote record
Issues, pull requests, claims, reviews, and sanitized run summaries remain on GitHub.

## Monitoring owner
The release owner reviews Monitor findings and approves any follow-up Ticket.

## Agent Roles
Product, architecture, program design, slices, QA, implementation, verification, and review.

## Human Gates
Product intent, alignment, and Acceptance Tests.

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
    review_retry = next((ticket for ticket in tickets if ticket.get("number") == 1), None)
    if not review_retry or review_retry.get("attempt") != 2:
        failures.append("the deterministic code-review comment did not return once to implementation")
    required_roles = {
        "supervisor", "qa", "implementation", "verification", "code_review", "human_review",
    }
    for ticket in tickets:
        number = ticket.get("number", "?")
        roles = {receipt.get("role") for receipt in ticket.get("_loaded_receipts", [])}
        missing_roles = sorted(required_roles - roles)
        if missing_roles:
            failures.append(
                f"ticket #{number} is missing Standard role receipts: {', '.join(missing_roles)}"
            )
        if ticket.get("code_review", {}).get("result", {}).get("decision") != "APPROVE":
            failures.append(f"ticket #{number} has no Code Review Agent approval")
        evidence = ticket.get("qa_evidence", {})
        if evidence.get("red", {}).get("result") != "RED PROVED":
            failures.append(f"ticket #{number} has no RED PROVED evidence")
        if evidence.get("red", {}).get("classification") != "behavior_assertion":
            failures.append(f"ticket #{number} RED evidence is not a behavior assertion")
        if evidence.get("green", {}).get("result") != "GREEN PROVED":
            failures.append(f"ticket #{number} has no GREEN PROVED evidence")
        if evidence.get("green", {}).get("classification") != "pass":
            failures.append(f"ticket #{number} GREEN evidence did not pass")
        if not evidence.get("focused_test_command") or not evidence.get("focused_test_command_sha256"):
            failures.append(f"ticket #{number} has no accepted focused test command")
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
        run_command = [
            *factory, "run", "--mock", "--scenario", "recipe-rebrand",
            "--profile", "standard", "--max-parallel", "1", "--once",
        ]
        for _ in range(20):
            _checked(run_command, checkout, timeout=300)
            current = json.loads((checkout / ".factory/state.json").read_text())
            for ticket in current.get("tickets", []):
                if ticket.get("status") == "In Review":
                    _checked([
                        *factory, "merge", str(ticket["number"]), "--mock", "--yes",
                    ], checkout, timeout=60)
            current = json.loads((checkout / ".factory/state.json").read_text())
            if current.get("tickets") and all(
                ticket.get("status") == "Done" for ticket in current["tickets"]
            ):
                break
        else:
            raise RuntimeError("Standard Rehearsal did not reach the human merge-ready path")

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
        monitor_head = _git(checkout, "rev-parse", "HEAD").strip()
        monitor_status = _git(checkout, "status", "--porcelain")
        _checked([*factory, "monitor", "--json"], checkout, timeout=None)
        monitor_path = checkout / ".factory/monitor/report.json"
        if not monitor_path.is_file():
            raise RuntimeError("Standard Rehearsal did not create a Monitor preview")
        monitor = json.loads(monitor_path.read_text())
        if monitor.get("version") != "factory-monitor:v1":
            raise RuntimeError("Standard Rehearsal Monitor report has no versioned identity")
        if (
            _git(checkout, "rev-parse", "HEAD").strip() != monitor_head
            or _git(checkout, "status", "--porcelain") != monitor_status
        ):
            raise RuntimeError("read-only Monitor changed the candidate checkout")
        canvas = _write_completed_canvas(checkout, "release-rehearsal-canvas.md")
        packet, _ = _export_and_validate_evidence(checkout, factory, plan_id, canvas)
        return (
            f"Standard Rehearsal PASS ({plan_id}, {len(state['tickets'])} tickets, "
            f"{packet.relative_to(checkout)}, Monitor {monitor.get('status', 'unknown')})"
        )


def _continue_live_smoke_plan(repo: Path, factory: list[str], plan_id: str) -> None:
    """Repair one mechanical slice-count violation, then fail closed."""
    command = [*factory, "continue-plan", plan_id]
    try:
        _checked(command, repo, timeout=None)
        return
    except RuntimeError:
        manifest_path = repo / ".factory/plans" / plan_id / "manifest.json"
        if not manifest_path.is_file():
            raise
        manifest = json.loads(manifest_path.read_text())
        record = manifest.get("stages", {}).get("vertical_slices", {})
        validation_error = str(record.get("validation_error") or "")
        repairable = (
            record.get("status") == "blocked"
            and record.get("failure_kind") == "validation"
            and record.get("same_failure_count") == 1
            and re.fullmatch(
                r"vertical slices expert returned \d+ tickets; expected 1-1",
                validation_error,
            )
        )
        if not repairable:
            raise

    feedback = (
        f"The deterministic validator rejected the artifact: {validation_error}. "
        "Return exactly one vertical slice. That one ticket must deliver the endpoint "
        "and carry the independent Acceptance Test evidence; the QA role authors the "
        "protected test during that ticket's workflow, not as a separate ticket. "
        "Preserve the approved requirement, contract, and program-element traceability."
    )
    _checked([
        *factory, "revise", plan_id, "slices", "--feedback", feedback,
    ], repo, timeout=None)
    _checked(command, repo, timeout=None)


def run_live_github_smoke(repo: Path, confirmed: bool) -> str:
    """Exercise live Claude delivery and deterministic review rework in a disposable repo."""
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
        "--supervisor-agent",
        "claude",
        "--review-agent",
        "mock-review",
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
Human approval for this disposable smoke explicitly covers adding the Acceptance Test under `demo-app/tests/`.

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
    _continue_live_smoke_plan(repo, factory, plan_id)
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
    issue = backend.json(
        "issue", "view", str(number), "--repo", repository, "--json", "body",
    )
    smoke_marker = "factory-release-smoke:review-rework"
    body = str(issue.get("body") or "").rstrip() + f"\n\n{smoke_marker}\n"
    edited = backend.gh(
        "issue", "edit", str(number), "--repo", repository, "--body", body,
        check=False,
    )
    if edited.returncode:
        raise RuntimeError("live smoke could not mark its disposable review-rework Ticket")

    run_command = [
        *factory,
        "run",
        "--profile",
        "standard",
        "--agent",
        "claude",
        "--qa-agent",
        "claude",
        "--supervisor-agent",
        "claude",
        "--review-agent",
        "mock-review",
        "--release-smoke-review",
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
        raise RuntimeError("Claude implementation did not reach the human exact-revision merge gate")
    if ticket.get("attempt", 0) < 2:
        raise RuntimeError("live smoke did not return Code Review feedback to implementation")
    if ticket.get("qa_evidence", {}).get("red", {}).get("result") != "RED PROVED" or ticket.get("qa_evidence", {}).get("green", {}).get("result") != "GREEN PROVED":
        raise RuntimeError("live smoke is missing causal RED/GREEN proof")
    if not ticket.get("remote_claim", {}).get("claim_sha"):
        raise RuntimeError("live smoke is missing its remote Ticket claim")
    if not ticket.get("remote_run_summary", {}).get("url"):
        raise RuntimeError("live smoke is missing its sanitized remote run summary")
    _checked([
        *factory, "merge", str(number), "--project-number",
        str(publication["project_number"]), "--yes",
    ], repo, timeout=None)
    state = json.loads(state_path.read_text())
    ticket = next(item for item in state["tickets"] if item["number"] == number)
    if ticket.get("status") != "Done":
        raise RuntimeError("human exact-revision merge did not complete")
    receipt_roles = {
        json.loads((repo / reference).read_text()).get("role")
        for reference in ticket.get("receipts", [])
        if (repo / reference).is_file()
    }
    if not {
        "supervisor", "qa", "implementation", "verification", "code_review", "human_review",
    } <= receipt_roles:
        raise RuntimeError("live smoke is missing required Handoff Receipts")
    if ticket.get("code_review", {}).get("result", {}).get("decision") != "APPROVE":
        raise RuntimeError("live smoke is missing Code Review Agent approval")
    review_receipts = [
        receipt
        for receipt in (
            json.loads((repo / reference).read_text())
            for reference in ticket.get("receipts", [])
            if (repo / reference).is_file()
        )
        if receipt.get("role") == "code_review"
    ]
    review_decisions = [
        receipt.get("output_revisions", {}).get("decision")
        for receipt in review_receipts
    ]
    if review_decisions[:2] != ["REQUEST_CHANGES", "APPROVE"]:
        raise RuntimeError(
            "live smoke did not preserve the Code Review request-changes and approval sequence"
        )
    reviewed_heads = [
        receipt.get("output_revisions", {}).get("reviewed_commit")
        for receipt in review_receipts[:2]
    ]
    if len(set(reviewed_heads)) != 2 or not all(reviewed_heads):
        raise RuntimeError("live smoke review feedback did not produce and re-review a new PR head")
    if ticket.get("merge_executed_by") != "human":
        raise RuntimeError("live smoke is missing the accountable human merge decision")
    _checked([*factory, "monitor", "--json"], repo, timeout=None)
    canvas = _write_completed_canvas(repo, f"live-smoke-{run_id}-canvas.md")
    packet, _ = _export_and_validate_evidence(
        repo, factory, plan_id, canvas, [issue_url, pr_url],
    )
    _checked([
        *factory, "reset", "--local-state-only", "--scenario", "recipe-rebrand",
    ], repo, timeout=None)
    _checked(run_command, repo, timeout=None)
    recovered_state = json.loads(state_path.read_text())
    recovered = next(item for item in recovered_state["tickets"] if item["number"] == number)
    if (
        recovered.get("status") != "Done"
        or recovered.get("pr_url") != pr_url
        or recovered.get("remote_run_summary", {}).get("recovered") is not True
        or not recovered.get("remote_claim", {}).get("claim_sha")
    ):
        raise RuntimeError("fresh local state did not reconstruct the merged PR and remote claim")
    return (
        f"Claude delivery + deterministic review-rework GitHub smoke PASS (Project #{publication['project_number']}, "
        f"issue #{number}, {pr_url}, {packet.relative_to(repo)}, remote recovery PASS)"
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
