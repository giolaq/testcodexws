"""Preflight diagnostics for a reliable Software (re)-Factory workshop."""

from __future__ import annotations

import json
import shutil
import socket
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


@dataclass
class Check:
    level: str
    name: str
    detail: str


def command(args: list[str], cwd: Path, timeout: int = 15):
    try:
        return subprocess.run(args, cwd=cwd, text=True, capture_output=True, timeout=timeout)
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


def run_doctor(repo: Path, cfg: dict, *, full=False, implementation_agent="codex", qa_agent=None) -> int:
    checks: list[Check] = []

    required = ["factory/orchestrator.py", "factory/factory.toml", "demo-app/app.py"]
    missing = [path for path in required if not (repo / path).is_file()]
    checks.append(Check("FAIL" if missing else "PASS", "workspace", ", ".join(missing) if missing else str(repo)))

    git = command(["git", "rev-parse", "--show-toplevel"], repo)
    checks.append(Check("PASS" if git.returncode == 0 else "FAIL", "Git repository", git.stdout.strip() or git.stderr.strip()))
    if git.returncode == 0:
        dirty = command(["git", "status", "--porcelain"], repo).stdout.strip()
        checks.append(Check("FAIL" if dirty else "PASS", "clean checkout", dirty or "no uncommitted files"))
        branch = command(["git", "branch", "--show-current"], repo).stdout.strip()
        checks.append(Check("PASS" if branch else "FAIL", "current branch", branch or "detached HEAD"))
        origin = command(["git", "remote", "get-url", "origin"], repo)
        checks.append(Check("PASS" if origin.returncode == 0 else "FAIL", "origin remote", origin.stdout.strip() or "not configured"))
        baseline = command(["git", "rev-parse", "--verify", "refs/tags/factory-baseline"], repo)
        checks.append(Check("PASS" if baseline.returncode == 0 else "WARN", "factory baseline", "available" if baseline.returncode == 0 else "tag missing; run setup once"))

    python_ok = sys.version_info >= (3, 11)
    checks.append(Check("PASS" if python_ok else "FAIL", "Python", f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"))
    node = command(["node", "--version"], repo)
    node_ok = node.returncode == 0 and version_tuple(node.stdout) >= (20,)
    checks.append(Check("PASS" if node_ok else "FAIL", "Node", node.stdout.strip() or "Node 20+ not found"))

    venv_python = repo / ".factory/venv/bin/python"
    if venv_python.is_file():
        imports = command([str(venv_python), "-c", "import flask, pytest"], repo)
        checks.append(Check("PASS" if imports.returncode == 0 else "FAIL", "Python environment", "Flask and pytest available" if imports.returncode == 0 else imports.stderr.strip()))
    else:
        checks.append(Check("FAIL", "Python environment", "run ./setup_demo.sh to create .factory/venv"))

    gh = shutil.which("gh")
    checks.append(Check("PASS" if gh else "FAIL", "GitHub CLI", gh or "install gh"))
    repo_details = None
    if gh:
        auth = command([gh, "auth", "status"], repo)
        auth_text = (auth.stdout + auth.stderr).strip()
        checks.append(Check("PASS" if auth.returncode == 0 else "FAIL", "GitHub authentication", "authenticated" if auth.returncode == 0 else auth_text))
        scope_ok = "project" in auth_text.lower()
        checks.append(Check("PASS" if scope_ok else "FAIL", "GitHub Projects scope", "project scope present" if scope_ok else "run gh auth refresh -s project"))
        view = command([gh, "repo", "view", "--json", "nameWithOwner,defaultBranchRef"], repo)
        if view.returncode == 0:
            repo_details = json.loads(view.stdout)
            default = (repo_details.get("defaultBranchRef") or {}).get("name") or "main"
            current = command(["git", "branch", "--show-current"], repo).stdout.strip()
            checks.append(Check("PASS" if current == default else "FAIL", "default branch", f"local `{current}`; GitHub `{default}`"))
            remote = command(["git", "ls-remote", "origin", f"refs/heads/{default}"], repo)
            remote_sha = remote.stdout.split()[0] if remote.returncode == 0 and remote.stdout.split() else ""
            local_sha = command(["git", "rev-parse", "HEAD"], repo).stdout.strip()
            checks.append(Check("PASS" if remote_sha == local_sha else "FAIL", "branch synchronization", "local HEAD matches GitHub" if remote_sha == local_sha else f"local {local_sha[:8]} vs remote {remote_sha[:8] or 'unknown'}"))
            owner = repo_details["nameWithOwner"].split("/", 1)[0]
            projects = command([gh, "project", "list", "--owner", owner, "--format", "json"], repo)
            checks.append(Check("PASS" if projects.returncode == 0 else "FAIL", "GitHub Project access", "accessible" if projects.returncode == 0 else projects.stderr.strip()))
        else:
            checks.append(Check("FAIL", "GitHub repository", view.stderr.strip() or "no connected repository"))

    required_agents = {implementation_agent, qa_agent or cfg.get("qa", {}).get("agent")}
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
        else:
            binary = "claude" if name == "claude" else "cursor-agent"
            found = shutil.which(binary)
            available, detail = bool(found), found or "not installed"
        required_agent = name in required_agents
        checks.append(Check("PASS" if available else ("FAIL" if required_agent else "WARN"), f"{name} adapter", detail))

    checks.extend(port_check(port) for port in (5000, 5050, 8000))

    qa = cfg.get("qa", {})
    roots = qa.get("test_roots")
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
    )
    checks.append(Check("PASS" if qa_valid else "FAIL", "QA configuration", "valid" if qa_valid else "invalid agent, retries, or test roots"))
    gates = cfg.get("gate", [])
    valid_gates = bool(gates) and all(gate.get("name") and gate.get("cmd") for gate in gates)
    checks.append(Check("PASS" if valid_gates else "FAIL", "verification gates", f"{len(gates)} configured" if valid_gates else "invalid or empty gate list"))
    if full and valid_gates:
        python = str(venv_python) if venv_python.is_file() else sys.executable
        for gate in gates:
            rendered = gate["cmd"].format(python=python, repo=str(repo))
            result = command(["/bin/sh", "-c", rendered], repo, timeout=300)
            checks.append(Check("PASS" if result.returncode == 0 else "FAIL", f"gate: {gate['name']}", "passed" if result.returncode == 0 else (result.stdout + result.stderr)[-500:].strip()))

    width = max(len(check.name) for check in checks)
    for check in checks:
        print(f"[{check.level:<4}] {check.name:<{width}}  {check.detail}")
    counts = {level: sum(check.level == level for check in checks) for level in ("PASS", "WARN", "FAIL")}
    print(f"\nDoctor: {counts['PASS']} passed, {counts['WARN']} warnings, {counts['FAIL']} failures")
    return 1 if counts["FAIL"] else 0
