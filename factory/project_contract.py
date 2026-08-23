"""Generic repository contract consumed by every factory role.

The public interface is intentionally small: detect, load, write, and context.
Repository-specific setup, QA placement, gates, tools, and reset configuration
stay behind this module instead of leaking technology checks into callers.
"""

from __future__ import annotations

import json
import re
import shlex
import string
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


CONTRACT_PATH = Path("factory.project.toml")
IGNORED_PARTS = {
    ".factory", ".git", ".hg", ".svn", ".tox", ".venv", "venv",
    "node_modules", "vendor", "dist", "build", "coverage", "__pycache__",
}
COMMON_SOURCE_ROOTS = ("src", "app", "lib", "packages", "cmd", "internal", "server", "client")
COMMON_TEST_NAMES = {"tests", "test", "__tests__", "spec"}
DEFAULT_TEST_PATTERNS = (
    "test_ticket_{ticket}*.py",
    "ticket-{ticket}*.test.js",
    "ticket-{ticket}*.test.ts",
    "ticket-{ticket}*.test.tsx",
    "ticket_{ticket}_test.go",
    "ticket_{ticket}_test.rs",
    "Ticket{ticket}*Test.java",
)
GATE_LEVELS = {"fast", "full", "deep"}


def _gate_level(name: str) -> str:
    lowered = name.lower()
    if any(word in lowered for word in ("security", "mutation", "architecture", "deep")):
        return "deep"
    if any(word in lowered for word in ("test", "build", "integration", "e2e")):
        return "full"
    return "fast"


class ProjectContractError(ValueError):
    pass


def _relative_path(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProjectContractError(f"{label} must contain non-empty paths")
    raw = value.strip()
    path = PurePosixPath(raw)
    normalized = path.as_posix()
    if "\\" in raw or path.is_absolute() or ".." in path.parts or not normalized:
        raise ProjectContractError(f"{label} must stay inside the repository: {value}")
    return normalized


def _strings(value, label: str, *, allow_empty=False) -> tuple[str, ...]:
    if not isinstance(value, list) or (not value and not allow_empty):
        raise ProjectContractError(f"{label} must be a {'possibly empty ' if allow_empty else 'non-empty '}list")
    if not all(isinstance(item, str) and item.strip() for item in value):
        raise ProjectContractError(f"{label} must contain non-empty strings")
    return tuple(item.strip() for item in value)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, text=True, capture_output=True, check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def _package_manager(repo: Path) -> str:
    if (repo / "pnpm-lock.yaml").is_file():
        return "pnpm"
    if (repo / "yarn.lock").is_file():
        return "yarn"
    return "npm"


def _npm_command(manager: str, script: str) -> str:
    return f"{manager} {script}" if manager == "yarn" else f"{manager} run {script}"


def _validate_placeholders(command: str, allowed: set[str], label: str) -> str:
    try:
        fields = {
            name for _, name, _, _ in string.Formatter().parse(command) if name
        }
    except ValueError as exc:
        raise ProjectContractError(f"{label} contains invalid placeholders: {exc}") from exc
    unknown = fields - allowed
    if unknown:
        raise ProjectContractError(
            f"{label} contains unsupported placeholders: {', '.join(sorted(unknown))}"
        )
    return command


@dataclass(frozen=True)
class ProjectContract:
    repo: Path
    name: str
    default_branch: str
    source_roots: tuple[str, ...]
    protected_paths: tuple[str, ...]
    required_tools: tuple[str, ...]
    setup_commands: tuple[str, ...]
    ports: tuple[int, ...]
    test_roots: tuple[str, ...]
    test_file_patterns: tuple[str, ...]
    gates: tuple[dict, ...]
    reset_command: tuple[str, ...] = ()
    reset_start_over_flag: str = "--start-over"
    path: Path | None = None
    detected: bool = False

    @classmethod
    def load(cls, repo: Path, *, require=False) -> "ProjectContract":
        repo = repo.resolve()
        path = repo / CONTRACT_PATH
        if path.is_file():
            try:
                value = tomllib.loads(path.read_text())
            except (OSError, tomllib.TOMLDecodeError) as exc:
                raise ProjectContractError(f"cannot read Project Contract at {path}: {exc}") from exc
            return cls._from_dict(repo, value, path)
        legacy = repo / "factory" / "factory.toml"
        if legacy.is_file() and not require:
            supplied = tomllib.loads(legacy.read_text())
            detected = cls.detect(repo)
            qa = supplied.get("qa", {})
            gates = supplied.get("gate") or list(detected.gates)
            return cls(
                **{
                    **detected.__dict__,
                    "test_roots": tuple(qa.get("test_roots") or detected.test_roots),
                    "gates": tuple({
                        "name": gate["name"],
                        "cmd": gate.get("cmd") or gate.get("command"),
                        "required": bool(gate.get("required", True)),
                        "level": gate.get("level") or _gate_level(gate["name"]),
                    } for gate in gates),
                }
            )
        if require:
            raise ProjectContractError(
                f"Project Contract not found at {path}. Run `factory init --repo {repo}`."
            )
        return cls.detect(repo)

    @classmethod
    def _from_dict(cls, repo: Path, value: dict, path: Path) -> "ProjectContract":
        if value.get("schema_version") != 1:
            raise ProjectContractError("Project Contract schema_version must be 1")
        project = value.get("project")
        environment = value.get("environment")
        qa = value.get("qa")
        if not all(isinstance(section, dict) for section in (project, environment, qa)):
            raise ProjectContractError("Project Contract requires project, environment, and qa tables")
        name = project.get("name")
        branch = project.get("default_branch")
        if not isinstance(name, str) or not name.strip():
            raise ProjectContractError("project.name is required")
        if not isinstance(branch, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,255}", branch):
            raise ProjectContractError("project.default_branch is invalid")
        source_roots = tuple(_relative_path(item, "project.source_roots") for item in _strings(project.get("source_roots"), "project.source_roots"))
        protected_paths = tuple(_relative_path(item, "project.protected_paths") for item in _strings(project.get("protected_paths", []), "project.protected_paths", allow_empty=True))
        required_tools = _strings(environment.get("required_tools"), "environment.required_tools")
        setup_commands = tuple(
            _validate_placeholders(item, {"python", "repo"}, "environment.setup")
            for item in _strings(environment.get("setup", []), "environment.setup", allow_empty=True)
        )
        raw_ports = environment.get("ports", [])
        if not isinstance(raw_ports, list) or not all(isinstance(port, int) and not isinstance(port, bool) and 1 <= port <= 65535 for port in raw_ports):
            raise ProjectContractError("environment.ports must contain valid port numbers")
        test_roots = tuple(_relative_path(item, "qa.test_roots") for item in _strings(qa.get("test_roots"), "qa.test_roots"))
        patterns = _strings(qa.get("test_file_patterns"), "qa.test_file_patterns")
        if any("/" in pattern or ".." in pattern or "{ticket}" not in pattern for pattern in patterns):
            raise ProjectContractError("qa.test_file_patterns must be filenames containing {ticket}")
        raw_gates = value.get("gate")
        if not isinstance(raw_gates, list) or not raw_gates:
            raise ProjectContractError("Project Contract requires at least one verification gate")
        gates = []
        for gate in raw_gates:
            command = gate.get("cmd") or gate.get("command") if isinstance(gate, dict) else None
            if not isinstance(gate, dict) or not re.fullmatch(r"[a-z][a-z0-9-]{0,47}", str(gate.get("name", ""))) or not isinstance(command, str) or not command.strip():
                raise ProjectContractError("each gate requires a lowercase name and command")
            gates.append({
                "name": gate["name"],
                "cmd": _validate_placeholders(
                    command.strip(), {"python", "repo"}, f"gate {gate['name']} command",
                ),
                "required": bool(gate.get("required", True)),
                "level": gate.get("level") or _gate_level(gate["name"]),
            })
            if gates[-1]["level"] not in GATE_LEVELS:
                raise ProjectContractError("gate level must be fast, full, or deep")
        names = [gate["name"] for gate in gates]
        if len(names) != len(set(names)):
            raise ProjectContractError("verification gate names must be unique")
        reset = value.get("reset", {})
        if not isinstance(reset, dict):
            raise ProjectContractError("reset must be a table")
        reset_command = tuple(
            _validate_placeholders(item, {"scenario"}, "reset.command")
            for item in _strings(reset.get("command", []), "reset.command", allow_empty=True)
        )
        start_flag = reset.get("start_over_flag", "--start-over")
        if not isinstance(start_flag, str) or not start_flag.startswith("--"):
            raise ProjectContractError("reset.start_over_flag must be a command flag")
        return cls(
            repo=repo,
            name=name.strip(),
            default_branch=branch,
            source_roots=source_roots,
            protected_paths=protected_paths,
            required_tools=required_tools,
            setup_commands=setup_commands,
            ports=tuple(raw_ports),
            test_roots=test_roots,
            test_file_patterns=patterns,
            gates=tuple(gates),
            reset_command=reset_command,
            reset_start_over_flag=start_flag,
            path=path,
        )

    @classmethod
    def detect(cls, repo: Path, *, name: str | None = None) -> "ProjectContract":
        repo = repo.resolve()
        remote_head = _git(repo, "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD")
        if remote_head.startswith("origin/"):
            branch = remote_head.removeprefix("origin/")
        elif _git(repo, "show-ref", "--verify", "--hash", "refs/heads/main"):
            branch = "main"
        elif _git(repo, "show-ref", "--verify", "--hash", "refs/heads/master"):
            branch = "master"
        else:
            branch = _git(repo, "symbolic-ref", "--quiet", "--short", "HEAD") or "main"
        source_roots = tuple(item for item in COMMON_SOURCE_ROOTS if (repo / item).is_dir())
        if not source_roots:
            source_roots = (".",)
        test_roots = []
        for path in sorted(repo.rglob("*")):
            if not path.is_dir() or path.name not in COMMON_TEST_NAMES:
                continue
            relative = path.relative_to(repo)
            if len(relative.parts) <= 3 and not set(relative.parts) & IGNORED_PARTS:
                test_roots.append(relative.as_posix())
        if not test_roots:
            test_roots = ["tests"]
        tools = ["git"]
        setup = []
        gates = []

        def add_gate(name: str, command: str, *, required: bool, level: str | None = None):
            base = name
            suffix = 2
            names = {gate["name"] for gate in gates}
            while name in names:
                name = f"{base}-{suffix}"
                suffix += 1
            gates.append({
                "name": name, "cmd": command, "required": required,
                "level": level or _gate_level(name),
            })
        detected_name = name or repo.name
        package = repo / "package.json"
        if package.is_file():
            try:
                package_value = json.loads(package.read_text())
            except json.JSONDecodeError as exc:
                raise ProjectContractError(f"package.json is invalid: {exc}") from exc
            detected_name = name or package_value.get("name") or detected_name
            manager = _package_manager(repo)
            tools.append(manager)
            setup.append(f"{manager} ci" if manager == "npm" and (repo / "package-lock.json").is_file() else f"{manager} install")
            scripts = package_value.get("scripts", {})
            if not isinstance(scripts, dict):
                raise ProjectContractError("package.json scripts must be an object")
            for script, gate_name in (("test", "tests"), ("lint", "lint"), ("typecheck", "typecheck"), ("build", "build")):
                if script in scripts:
                    add_gate(
                        gate_name, _npm_command(manager, script),
                        required=script in {"test", "build"},
                    )
        pyproject = repo / "pyproject.toml"
        requirements = repo / "requirements.txt"
        if pyproject.is_file() or requirements.is_file() or any(repo.glob("**/*.py")):
            tools.append("python3")
            if pyproject.is_file():
                try:
                    pyproject_value = tomllib.loads(pyproject.read_text())
                    project_table = pyproject_value.get("project", {})
                    if not isinstance(project_table, dict):
                        raise ProjectContractError("pyproject.toml project must be a table")
                    detected_name = name or project_table.get("name") or detected_name
                except tomllib.TOMLDecodeError as exc:
                    raise ProjectContractError(f"pyproject.toml is invalid: {exc}") from exc
            if requirements.is_file():
                setup.append("{python} -m pip install -r requirements.txt")
            python_test_roots = [
                root for root in test_roots
                if (repo / root).is_dir() and (
                    any((repo / root).rglob("test_*.py"))
                    or any((repo / root).rglob("*_test.py"))
                )
            ]
            if python_test_roots:
                if not any(gate["name"] == "tests" for gate in gates):
                    targets = " ".join(shlex.quote(root) for root in python_test_roots)
                    add_gate("tests", f"{{python}} -m pytest -q {targets}", required=True)
        if (repo / "go.mod").is_file():
            tools.append("go")
            add_gate("tests", "go test ./...", required=True)
        if (repo / "Cargo.toml").is_file():
            tools.append("cargo")
            add_gate("tests", "cargo test", required=True)
        if not gates:
            add_gate("repository-integrity", "git diff --check", required=True)
        return cls(
            repo=repo,
            name=str(detected_name),
            default_branch=branch,
            source_roots=tuple(dict.fromkeys(source_roots)),
            protected_paths=(".github/workflows",),
            required_tools=tuple(dict.fromkeys(tools)),
            setup_commands=tuple(dict.fromkeys(setup)),
            ports=(),
            test_roots=tuple(dict.fromkeys(test_roots)),
            test_file_patterns=DEFAULT_TEST_PATTERNS,
            gates=tuple(gates),
            detected=True,
        )

    def write(self, *, force=False) -> Path:
        path = self.repo / CONTRACT_PATH
        if path.exists() and not force:
            raise ProjectContractError(f"Project Contract already exists: {path}")
        def values(items):
            return "[" + ", ".join(json.dumps(item) for item in items) + "]"
        lines = [
            "# Repository-specific configuration for the Software (re)-Factory.",
            "schema_version = 1",
            "",
            "[project]",
            f"name = {json.dumps(self.name)}",
            f"default_branch = {json.dumps(self.default_branch)}",
            f"source_roots = {values(self.source_roots)}",
            f"protected_paths = {values(self.protected_paths)}",
            "",
            "[environment]",
            f"required_tools = {values(self.required_tools)}",
            f"setup = {values(self.setup_commands)}",
            "ports = [" + ", ".join(str(port) for port in self.ports) + "]",
            "",
            "[qa]",
            f"test_roots = {values(self.test_roots)}",
            f"test_file_patterns = {values(self.test_file_patterns)}",
        ]
        for gate in self.gates:
            lines += [
                "", "[[gate]]", f"name = {json.dumps(gate['name'])}",
                f"cmd = {json.dumps(gate['cmd'])}",
                f"required = {str(gate.get('required', True)).lower()}",
                f"level = {json.dumps(gate.get('level') or _gate_level(gate['name']))}",
            ]
        if self.reset_command:
            lines += [
                "", "[reset]", f"command = {values(self.reset_command)}",
                f"start_over_flag = {json.dumps(self.reset_start_over_flag)}",
            ]
        path.write_text("\n".join(lines) + "\n")
        return path

    def context(self, *, max_files=240) -> str:
        tracked = _git(self.repo, "ls-files").splitlines()
        if not tracked:
            tracked = [
                path.relative_to(self.repo).as_posix()
                for path in self.repo.rglob("*") if path.is_file()
            ]
        files = sorted(
            path for path in tracked
            if path and not set(PurePosixPath(path).parts) & IGNORED_PARTS
        )[:max_files]
        value = {
            "name": self.name,
            "default_branch": self.default_branch,
            "source_roots": list(self.source_roots),
            "test_roots": list(self.test_roots),
            "protected_paths": list(self.protected_paths),
            "setup_commands": list(self.setup_commands),
            "verification_gates": list(self.gates),
            "representative_files": files,
            "inventory_truncated": len(tracked) > len(files),
        }
        return json.dumps(value, indent=2)

    def reset_argv(self, scenario: str, *, start_over=False) -> list[str] | None:
        if not self.reset_command:
            return None
        command = [item.format(scenario=scenario) for item in self.reset_command]
        if start_over:
            command.append(self.reset_start_over_flag)
        return command

    def render_command(self, command: str, *, python: str) -> str:
        """Render the only placeholders accepted by setup and verification commands."""
        return command.format(
            python=shlex.quote(python), repo=shlex.quote(str(self.repo)),
        )
