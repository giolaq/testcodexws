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


PLAN_ID = re.compile(r"[a-f0-9]{8,64}")
ADAPTER = re.compile(r"[a-z][a-z0-9_-]{0,31}")
PROFILES = {"lean", "standard", "assured"}
PRESETS = {"claude-workshop", "codex-workshop"}
SCENARIOS = {"recipe-rebrand", "tv"}
DEFAULT_AGENTS = {"claude", "codex", "cursor", "mock", "mock-qa"}
MAX_BODY = 256_000
MAX_ARTIFACT = 512_000


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


def run_text(command: list[str], cwd: Path) -> str:
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else ""


class InputError(ValueError):
    """A safe, user-visible API validation failure."""


class ControlCenter:
    def __init__(self, repo: Path):
        self.repo = repo.resolve()
        self.factory = self.repo / "factory" / "factory"
        self.assets = self.repo / "factory" / "control_center"
        self.runtime = self.repo / ".factory" / "control-center"
        self.runtime.mkdir(parents=True, exist_ok=True)
        (self.repo / ".factory" / "logs").mkdir(parents=True, exist_ok=True)
        self.prd_path = self.runtime / "workshop-prd.md"
        self.operation_path = self.runtime / "operation.json"
        self.canvas_path = self.runtime / "factory-canvas.md"
        self.lock = threading.RLock()
        self.process: subprocess.Popen | None = None
        self.operation: dict = read_json(self.operation_path, {})
        if self.operation.get("status") == "running":
            self.operation.update(
                status="interrupted",
                finished_at=utc_now(),
                error="The control center restarted while this operation was running.",
            )
            self._save_operation()

    def _save_operation(self):
        temp = self.operation_path.with_suffix(".tmp")
        temp.write_text(json.dumps(self.operation, indent=2) + "\n")
        os.replace(temp, self.operation_path)

    def adapters(self) -> list[str]:
        names = set(DEFAULT_AGENTS)
        path = self.repo / "factory" / "factory.toml"
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
        github = ""
        if remote:
            match = re.search(r"github\.com[/:]([^/]+/[^/]+?)(?:\.git)?$", remote)
            if match:
                github = "https://github.com/" + match.group(1)
        return {
            "name": self.repo.name,
            "path": str(self.repo),
            "branch": branch or "detached",
            "remote": remote,
            "github_url": github,
            "dirty": dirty,
        }

    def session_config(self) -> dict:
        path = self.repo / ".factory" / "local.toml"
        try:
            return tomllib.loads(path.read_text())
        except (OSError, tomllib.TOMLDecodeError):
            return {}

    def prd(self) -> dict:
        source = self.prd_path if self.prd_path.is_file() else self.repo / "recipe-app-prd.md"
        text = source.read_text() if source.is_file() else "# Product requirements document\n\n"
        return {"path": str(source.relative_to(self.repo)), "text": text, "saved": self.prd_path.is_file()}

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
                candidates.append({
                    "path": str(path.relative_to(self.repo)),
                    "name": path.name,
                    "size": path.stat().st_size,
                    "updated_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(timespec="seconds"),
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
        value["output"] = tail_text(self.repo / log) if log else ""
        return value

    def snapshot(self) -> dict:
        return {
            "server_time": utc_now(),
            "repo": self.repo_info(),
            "config": self.session_config(),
            "adapters": self.adapters(),
            "profiles": sorted(PROFILES),
            "planning": read_json(self.repo / ".factory" / "planning-state.json", {}),
            "factory": read_json(self.repo / ".factory" / "state.json", {"tickets": []}),
            "operation": self.operation_snapshot(),
            "prd": {key: value for key, value in self.prd().items() if key != "text"},
            "evidence": self.evidence_files(),
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

    def _mode_flags(self, payload: dict) -> list[str]:
        if payload.get("mode", "rehearsal") != "live":
            scenario = self._string(payload, "scenario") or "recipe-rebrand"
            if scenario not in SCENARIOS:
                raise InputError("Unknown rehearsal scenario.")
            return ["--mock", "--scenario", scenario]
        return []

    def build_commands(self, action: str, payload: dict) -> tuple[str, list[list[str]]]:
        base = [str(self.factory)]
        mode = payload.get("mode", "rehearsal")
        mock = mode != "live"
        if action == "doctor":
            return "Check readiness", [base + ["doctor"] + (["--full"] if payload.get("full") else [])]
        if action == "configure":
            command = base + ["configure"]
            preset = self._string(payload, "preset")
            if preset:
                if preset not in PRESETS:
                    raise InputError("Unknown agent preset.")
                command += ["--preset", preset]
            profile = self._string(payload, "profile")
            if profile:
                if profile not in PROFILES:
                    raise InputError("Unknown factory profile.")
                command += ["--profile", profile]
            known = set(self.adapters())
            for field, flag in (("agent", "--agent"), ("qa_agent", "--qa-agent")):
                value = self._string(payload, field)
                if value:
                    if not ADAPTER.fullmatch(value) or value not in known:
                        raise InputError(f"Unknown {field.replace('_', ' ')} adapter.")
                    command += [flag, value]
            planning = self._string(payload, "planning_agent")
            if planning:
                if planning not in {"claude", "codex"}:
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
            return "Save factory configuration", [command]
        if action == "plan":
            if not self.prd_path.is_file():
                raise InputError("Save the PRD before starting Product Review.")
            profile = self._string(payload, "profile") or "standard"
            if profile not in PROFILES:
                raise InputError("Unknown factory profile.")
            command = base + ["plan", str(self.prd_path), "--profile", profile]
            if mock:
                command.append("--mock")
            return "Run Product Review", [command]
        if action == "revise-product":
            plan = self._plan_id(payload)
            feedback = self._string(payload, "feedback", required=True, max_length=4000)
            feedback_path = self.runtime / "product-feedback.md"
            feedback_path.write_text(feedback + "\n")
            command = base + ["revise", plan, "product", "--feedback-file", str(feedback_path)]
            if mock:
                command.append("--mock")
            return "Revise Product Review", [command]
        if action == "approve-product":
            return "Approve product intent", [base + ["approve-product", self._plan_id(payload), "--yes"]]
        if action == "continue-plan":
            command = base + ["continue-plan", self._plan_id(payload)]
            if mock:
                command.append("--mock")
            return "Run architecture and delivery planning", [command]
        if action == "publish-plan":
            plan = self._plan_id(payload)
            if mock:
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
        if action in {"run", "run-once", "dry-run"}:
            command = base + ["run"] + self._mode_flags(payload)
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
        if action == "evidence":
            plan = self._plan_id(payload)
            if not self.canvas_path.is_file():
                raise InputError("Complete and save the Factory Canvas before exporting evidence.")
            output = self.runtime / f"evidence-{plan}"
            return "Create evidence packet", [
                base + ["evidence", plan, "--canvas", str(self.canvas_path), "--output", str(output)],
            ]
        raise InputError("This control-center action is not available.")

    def start(self, action: str, payload: dict) -> dict:
        title, commands = self.build_commands(action, payload)
        with self.lock:
            if self.operation.get("status") in {"running", "stopping"} or (
                self.process and self.process.poll() is None
            ):
                raise InputError("Another factory operation is already running.")
            operation_id = uuid.uuid4().hex[:12]
            log = self.repo / ".factory" / "logs" / f"control-center-{operation_id}.log"
            self.operation = {
                "id": operation_id,
                "action": action,
                "title": title,
                "status": "running",
                "started_at": utc_now(),
                "finished_at": "",
                "exit_code": None,
                "command": " && ".join(shlex.join(command) for command in commands),
                "log": str(log.relative_to(self.repo)),
                "error": "",
            }
            self._save_operation()
        thread = threading.Thread(target=self._run, args=(commands, log), daemon=True)
        thread.start()
        return self.operation_snapshot()

    def _run(self, commands: list[list[str]], log: Path):
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
                            cwd=self.repo,
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
                self.operation.update(status=status, finished_at=utc_now(), exit_code=exit_code)
                if failure:
                    self.operation["error"] = failure
                elif exit_code and status != "stopped":
                    self.operation["error"] = "The operation failed. Read the final log lines for the cause."
                self.process = None
                self._save_operation()

    def stop(self) -> dict:
        with self.lock:
            process = self.process
            if self.operation.get("status") != "running":
                raise InputError("No factory operation is running.")
            self.operation["status"] = "stopping"
            self._save_operation()
            if process and process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
        return self.operation_snapshot()

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
        try:
            while True:
                data = json.dumps(self.server.center.snapshot())
                self.wfile.write(f"data: {data}\n\n".encode())
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
        server.server_close()
