"""Preflight diagnostics for a reliable Software (re)-Factory workshop."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from factory_contracts import profile as factory_profile
from factory_charter import FactoryCharter, FactoryCharterError
from github_repository import (
    GitHubRepositoryError,
    parse_github_repository,
    repository_from_remote,
)
from project_contract import CONTRACT_PATH, ProjectContract, ProjectContractError


@dataclass
class Check:
    level: str
    name: str
    detail: str


def command(args: list[str], cwd: Path, timeout: int = 15, env=None):
    try:
        return subprocess.run(
            args, cwd=cwd, text=True, capture_output=True, timeout=timeout, env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return type("CommandFailure", (), {"returncode": 127, "stdout": "", "stderr": str(exc)})()


def version_tuple(raw: str) -> tuple[int, ...]:
    digits = []
    for part in raw.strip().lstrip("v").split("."):
        number = "".join(character for character in part if character.isdigit())
        if not number:
            break
        digits.append(int(number))
    return tuple(digits)


def port_check(port: int) -> Check:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", port))
    except OSError:
        return Check("WARN", f"port {port}", "already in use; choose another workshop port")
    finally:
        sock.close()
    return Check("PASS", f"port {port}", "available")


def codex_candidates() -> list[str]:
    return list(dict.fromkeys(filter(None, [
        shutil.which("codex"),
        "/Applications/ChatGPT.app/Contents/Resources/codex",
    ])))


BASELINE_SUBJECT = "chore: establish factory workshop baseline"


REHEARSAL_ONLY_TESTS = (
    "demo-app/tests/test_device_mode.py",
    "demo-app/tests/test_rails.py",
    "demo-app/tests/test_tv_detail.py",
)


def baseline_check(repo: Path) -> Check:
    """Confirm factory-baseline holds the mobile workpiece, not a finished rehearsal.

    A baseline carrying rehearsal-era tests grades fresh tickets against a
    product they legitimately replaced, so every scenario stalls on gate
    failures the agent cannot fix.
    """
    tagged = command(["git", "rev-parse", "--verify", "--quiet", "refs/tags/factory-baseline^{commit}"], repo)
    revision = tagged.stdout.strip()
    if tagged.returncode != 0 or not revision:
        return Check("WARN", "factory baseline", "tag missing; run setup once")

    listing = command(["git", "ls-tree", "-r", "--name-only", revision, "--", "demo-app"], repo)
    if listing.returncode != 0:
        return Check("FAIL", "factory baseline", listing.stderr.strip() or "cannot read tagged tree")
    tracked = set(listing.stdout.split())
    stale = sorted(path for path in REHEARSAL_ONLY_TESTS if path in tracked)
    if not stale:
        return Check("PASS", "factory baseline", f"mobile workpiece at {revision[:7]}")

    recoverable = command(["git", "rev-list", "--max-count=1", f"--grep=^{BASELINE_SUBJECT}$", "HEAD"], repo)
    wanted = recoverable.stdout.strip()
    remedy = (
        "rerun setup_demo.sh to repoint it"
        if wanted and wanted != revision
        else "re-clone from origin; this checkout has no mobile baseline to restore"
    )
    return Check("FAIL", "factory baseline", f"{revision[:7]} still carries {', '.join(stale)}; {remedy}")


def required_agent_names(
    cfg: dict, profile_name: str, implementation_agent: str,
    qa_agent: str | None, supervisor_agent: str | None, planning_agent: str,
    review_agent: str | None = None,
) -> set[str | None]:
    roles = factory_profile(profile_name)["execution_roles"]
    required = {implementation_agent, planning_agent}
    if "qa" in roles:
        required.add(qa_agent or cfg.get("qa", {}).get("agent"))
    if "supervisor" in roles:
        required.add(supervisor_agent or cfg.get("supervisor", {}).get("agent"))
    if "code_review" in roles:
        required.add(review_agent or cfg.get("review", {}).get("agent"))
    return required


def run_doctor(
    repo: Path, cfg: dict, *, full=False, implementation_agent="codex",
    qa_agent=None, supervisor_agent=None, review_agent=None,
    planning_agent="codex", profile_name="standard", github_repository=None,
) -> int:
    checks: list[Check] = []
    try:
        project = ProjectContract.load(repo)
        contract_error = ""
    except ProjectContractError as exc:
        project = ProjectContract.detect(repo)
        contract_error = str(exc)
    configured_repository = None
    if github_repository:
        try:
            configured_repository = parse_github_repository(github_repository)
        except GitHubRepositoryError:
            pass

    missing_roots = [root for root in project.source_roots if root != "." and not (repo / root).exists()]
    checks.append(Check("FAIL" if missing_roots else "PASS", "workspace", ", ".join(missing_roots) if missing_roots else str(repo)))
    contract_path = repo / CONTRACT_PATH
    contract_level = "PASS" if contract_path.is_file() and not contract_error else ("FAIL" if full else "WARN")
    contract_detail = str(contract_path) if contract_level == "PASS" else contract_error or "run `factory init` and review the generated contract"
    checks.append(Check(contract_level, "Project Contract", contract_detail))
    try:
        charter = FactoryCharter.load(repo, require_approved=True)
        selected_profile = factory_profile(profile_name)
        governance = charter.governance(
            profile_name,
            explicit_autonomy=bool(selected_profile.get("requires_explicit_opt_in")),
        )
        charter_level = "PASS"
        charter_detail = (
            f"approved {governance['charter_sha256'][:12]} · "
            f"{governance['merge_authority']} merge · {governance['gate_level']} gates"
        )
    except (FactoryCharterError, ValueError) as exc:
        charter_level = "FAIL"
        charter_detail = str(exc)
    checks.append(Check(charter_level, "Factory Charter", charter_detail))

    git = command(["git", "rev-parse", "--show-toplevel"], repo)
    checks.append(Check("PASS" if git.returncode == 0 else "FAIL", "Git repository", git.stdout.strip() or git.stderr.strip()))
    if git.returncode == 0:
        dirty = command(["git", "status", "--porcelain"], repo).stdout.strip()
        checks.append(Check("FAIL" if dirty else "PASS", "clean checkout", dirty or "no uncommitted files"))
        branch = command(["git", "branch", "--show-current"], repo).stdout.strip()
        checks.append(Check("PASS" if branch else "FAIL", "current branch", branch or "detached HEAD"))
        if full:
            origin = command(["git", "remote", "get-url", "origin"], repo)
            checks.append(Check("PASS" if origin.returncode == 0 else "FAIL", "origin remote", origin.stdout.strip() or "not configured"))
            origin_repository = repository_from_remote(origin.stdout.strip())
            repository_matches = bool(
                configured_repository
                and origin_repository
                and configured_repository.slug.lower() == origin_repository.slug.lower()
            )
            detail = (
                configured_repository.url
                if repository_matches
                else "save the attendee repository URL in Connect or with `factory configure --github-repository URL`"
            )
            checks.append(Check("PASS" if repository_matches else "FAIL", "GitHub repository target", detail))
        if project.reset_command and any("setup_demo.sh" in item for item in project.reset_command):
            checks.append(baseline_check(repo))

    python_ok = sys.version_info >= (3, 11)
    checks.append(Check("PASS" if python_ok else "FAIL", "Python", f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"))
    venv_python = repo / ".factory/venv/bin/python"
    checks.append(Check(
        "PASS", "execution Python",
        str(venv_python) if venv_python.is_file() else sys.executable,
    ))
    if full:
        for tool in project.required_tools:
            if tool in {"python", "python3"}:
                found = sys.executable
            else:
                found = shutil.which(tool)
            checks.append(Check("PASS" if found else "FAIL", f"tool: {tool}", found or "not found"))

    gh = shutil.which("gh") if full else None
    if full:
        checks.append(Check("PASS" if gh else "FAIL", "GitHub CLI", gh or "install gh"))
    if full and gh:
        auth = command([gh, "auth", "status"], repo)
        auth_text = (auth.stdout + auth.stderr).strip()
        checks.append(Check("PASS" if auth.returncode == 0 else "FAIL", "GitHub authentication", "authenticated" if auth.returncode == 0 else auth_text))
        scope_ok = "project" in auth_text.lower()
        checks.append(Check("PASS" if scope_ok else "FAIL", "GitHub Projects scope", "project scope present" if scope_ok else "run gh auth refresh -s project"))
        target = [configured_repository.slug] if configured_repository else []
        view = command([gh, "repo", "view", *target, "--json", "nameWithOwner,defaultBranchRef"], repo)
        if view.returncode == 0:
            repo_details = json.loads(view.stdout)
            default = (repo_details.get("defaultBranchRef") or {}).get("name") or "main"
            current = command(["git", "branch", "--show-current"], repo).stdout.strip()
            checks.append(Check(
                "PASS" if project.default_branch == default else "FAIL",
                "Project Contract branch",
                f"contract `{project.default_branch}`; GitHub `{default}`",
            ))
            checks.append(Check("PASS" if current == default else "FAIL", "default branch", f"local `{current}`; GitHub `{default}`"))
            remote = command(["git", "ls-remote", "origin", f"refs/heads/{default}"], repo)
            remote_sha = remote.stdout.split()[0] if remote.returncode == 0 and remote.stdout.split() else ""
            local_sha = command(["git", "rev-parse", "HEAD"], repo).stdout.strip()
            checks.append(Check("PASS" if remote_sha == local_sha else "FAIL", "branch synchronization", "local HEAD matches GitHub" if remote_sha == local_sha else f"local {local_sha[:8]} vs remote {remote_sha[:8] or 'unknown'}"))
            owner = repo_details["nameWithOwner"].split("/", 1)[0]
            projects = command([gh, "project", "list", "--owner", owner, "--format", "json"], repo)
            checks.append(Check("PASS" if projects.returncode == 0 else "FAIL", "GitHub Project access", "accessible" if projects.returncode == 0 else projects.stderr.strip()))

            reviewer_token = os.environ.get("FACTORY_REVIEW_GH_TOKEN", "").strip()
            if reviewer_token and "code_review" in factory_profile(profile_name)["execution_roles"]:
                author = command([gh, "api", "user", "--jq", ".login"], repo)
                reviewer = command(
                    [gh, "api", "user", "--jq", ".login"], repo,
                    env={**os.environ, "GH_TOKEN": reviewer_token},
                )
                distinct = (
                    author.returncode == 0 and reviewer.returncode == 0
                    and author.stdout.strip() != reviewer.stdout.strip()
                )
                detail = (
                    f"{reviewer.stdout.strip()} can submit formal reviews"
                    if distinct else "token must belong to a different GitHub account"
                )
                checks.append(Check("PASS" if distinct else "WARN", "GitHub reviewer identity", detail))
            elif "code_review" in factory_profile(profile_name)["execution_roles"]:
                checks.append(Check(
                    "WARN", "GitHub reviewer identity",
                    "FACTORY_REVIEW_GH_TOKEN not set; self-reviews use a labelled Factory comment",
                ))
        else:
            checks.append(Check("FAIL", "GitHub repository", view.stderr.strip() or "no connected repository"))

    if full:
        required_agents = required_agent_names(
            cfg, profile_name, implementation_agent, qa_agent,
            supervisor_agent, planning_agent, review_agent,
        )
        for name in ("codex", "claude", "cursor"):
            if name == "codex":
                available = False
                detail = "not found or not signed in"
                for candidate in codex_candidates():
                    status = command([candidate, "login", "status"], repo)
                    help_result = command([candidate, "exec", "--help"], repo)
                    if status.returncode == 0 and help_result.returncode == 0:
                        available, detail = True, candidate
                        break
            elif name == "claude":
                found = shutil.which("claude")
                if found:
                    status = command([found, "auth", "status", "--text"], repo)
                    help_result = command([found, "--help"], repo)
                    structured = "--json-schema" in help_result.stdout + help_result.stderr
                    available = status.returncode == 0 and (planning_agent != "claude" or structured)
                    if status.returncode:
                        detail = "not signed in; run claude auth login"
                    elif planning_agent == "claude" and not structured:
                        detail = "update Claude Code; --json-schema is required for planning"
                    else:
                        detail = found
                else:
                    available, detail = False, "not installed"
            else:
                found = shutil.which("cursor-agent")
                available, detail = bool(found), found or "not installed"
            required_agent = name in required_agents
            checks.append(Check("PASS" if available else ("FAIL" if required_agent else "WARN"), f"{name} adapter", detail))

        for name in sorted(required_agents - {"codex", "claude", "cursor", None}):
            registered = name in cfg.get("agents", {})
            detail = (
                "registered in factory/factory.toml; run the adapter command once to verify its own authentication"
                if registered else "not registered in factory/factory.toml [agents]"
            )
            checks.append(Check("PASS" if registered else "FAIL", f"{name} adapter", detail))

        for name in sorted(item for item in required_agents if item):
            capability = cfg.get("agent_capabilities", {}).get(name)
            if not capability:
                checks.append(Check(
                    "FAIL", f"{name} execution boundary",
                    "missing [agent_capabilities] declaration",
                ))
                continue
            read_only = "native read-only" if capability.supports_read_only else "mutation detection only"
            detail = (
                f"{capability.execution_environment}; {capability.filesystem_mode}; "
                f"roots {', '.join(capability.allowed_working_roots)}; "
                f"network {capability.network_expectation}; {read_only}"
            )
            checks.append(Check(
                "PASS" if capability.supports_read_only else "WARN",
                f"{name} execution boundary", detail,
            ))

    checks.extend(port_check(port) for port in (*project.ports, 5050))

    qa = cfg.get("qa", {})
    roots = qa.get("test_roots")
    patterns = qa.get("test_file_patterns", list(project.test_file_patterns))
    qa_valid = (
        qa.get("agent") in cfg.get("agents", {})
        and isinstance(qa.get("max_retries"), int)
        and qa.get("max_retries") >= 0
        and isinstance(roots, list) and bool(roots)
        and all(
            isinstance(root, str) and root
            and not PurePosixPath(root).is_absolute()
            and ".." not in PurePosixPath(root).parts
            for root in roots
        )
        and isinstance(patterns, list) and bool(patterns)
        and all(isinstance(pattern, str) and "{ticket}" in pattern for pattern in patterns)
    )
    checks.append(Check("PASS" if qa_valid else "FAIL", "QA configuration", "valid" if qa_valid else "invalid agent, retries, or test roots"))
    gates = cfg.get("gate", [])
    valid_gates = bool(gates) and all(gate.get("name") and gate.get("cmd") for gate in gates)
    checks.append(Check("PASS" if valid_gates else "FAIL", "verification gates", f"{len(gates)} configured" if valid_gates else "invalid or empty gate list"))
    if full and valid_gates:
        python = str(venv_python) if venv_python.is_file() else sys.executable
        for gate in gates:
            rendered = project.render_command(gate["cmd"], python=python)
            result = command(["/bin/sh", "-c", rendered], repo, timeout=300)
            checks.append(Check("PASS" if result.returncode == 0 else "FAIL", f"gate: {gate['name']}", "passed" if result.returncode == 0 else (result.stdout + result.stderr)[-500:].strip()))

    width = max(len(check.name) for check in checks)
    for check in checks:
        print(f"[{check.level:<4}] {check.name:<{width}}  {check.detail}")
    counts = {level: sum(check.level == level for check in checks) for level in ("PASS", "WARN", "FAIL")}
    print(f"\nDoctor: {counts['PASS']} passed, {counts['WARN']} warnings, {counts['FAIL']} failures")
    return 1 if counts["FAIL"] else 0
