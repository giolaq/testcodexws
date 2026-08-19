"""Local, attendee-specific defaults for the factory CLI.

The file lives under ``.factory/`` so it is never committed. Repository policy
continues to live in ``factory/factory.toml``; this module stores only the
operator choices that would otherwise be repeated on every command.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

from factory_contracts import PROFILES


CONFIG_PATH = Path(".factory/local.toml")
PLANNING_AGENTS = {"claude", "codex"}
FACTORY_PROFILES = set(PROFILES)
AGENT_NAME = re.compile(r"[a-z][a-z0-9_-]{0,31}")
PRESETS = {
    "claude-workshop": {
        "profile": "standard",
        "agent": "claude",
        "qa_agent": "claude",
        "planning_agent": "claude",
        "review_qa_tests": True,
        "max_parallel": 1,
    },
    "codex-workshop": {
        "profile": "standard",
        "agent": "codex",
        "qa_agent": "codex",
        "planning_agent": "codex",
        "review_qa_tests": True,
        "max_parallel": 1,
    },
}


def config_path(repo: Path) -> Path:
    return repo.resolve() / CONFIG_PATH


def validate_session_config(value: dict) -> dict:
    if not isinstance(value, dict):
        raise ValueError("local factory configuration must be a TOML table")
    preset = value.get("preset")
    if preset is not None and preset not in PRESETS:
        raise ValueError(f"unknown factory preset: {preset}")
    if "profile" in value and value["profile"] not in FACTORY_PROFILES:
        raise ValueError("profile must be lean, standard, or assured")
    for key in ("agent", "qa_agent"):
        if key in value and (
            not isinstance(value[key], str) or not AGENT_NAME.fullmatch(value[key])
        ):
            raise ValueError(f"{key} must be a lowercase registered adapter name")
    if "planning_agent" in value and value["planning_agent"] not in PLANNING_AGENTS:
        raise ValueError("planning_agent must be claude or codex")
    if "review_qa_tests" in value and not isinstance(value["review_qa_tests"], bool):
        raise ValueError("review_qa_tests must be true or false")
    for key in ("max_parallel", "project_number"):
        invalid = (
            key in value
            and (
                not isinstance(value[key], int)
                or isinstance(value[key], bool)
                or value[key] < 1
            )
        )
        if invalid:
            raise ValueError(f"{key} must be a positive integer")
    return value


def load_session_config(repo: Path) -> dict:
    path = config_path(repo)
    if not path.is_file():
        return {}
    try:
        return validate_session_config(tomllib.loads(path.read_text()))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"cannot read local factory configuration at {path}: {exc}") from exc


def write_session_config(repo: Path, value: dict) -> Path:
    value = validate_session_config(dict(value))
    path = config_path(repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    order = (
        "preset", "profile", "agent", "qa_agent", "planning_agent",
        "review_qa_tests", "max_parallel", "project_number",
    )
    lines = ["# Attendee-specific defaults. This file is ignored by Git."]
    for key in order:
        if key not in value:
            continue
        item = value[key]
        if isinstance(item, bool):
            rendered = str(item).lower()
        elif isinstance(item, int):
            rendered = str(item)
        else:
            rendered = json.dumps(item)
        lines.append(f"{key} = {rendered}")
    path.write_text("\n".join(lines) + "\n")
    return path


def configure_session(
    repo: Path, preset: str | None = None, project_number: int | None = None,
    *, agent: str | None = None, qa_agent: str | None = None,
    planning_agent: str | None = None, review_qa_tests: bool | None = None,
    max_parallel: int | None = None, profile: str | None = None,
) -> tuple[Path, dict]:
    if preset is not None and preset not in PRESETS:
        raise ValueError(f"unknown factory preset: {preset}")
    existing = load_session_config(repo)
    value = dict(existing)
    if preset is not None:
        value = {"preset": preset, **PRESETS[preset]}
    if profile is not None:
        if profile not in FACTORY_PROFILES:
            raise ValueError(f"unknown factory profile: {profile}")
        value["profile"] = profile
        if max_parallel is None:
            value["max_parallel"] = 1
    overrides = {
        "agent": agent,
        "qa_agent": qa_agent,
        "planning_agent": planning_agent,
        "review_qa_tests": review_qa_tests,
        "max_parallel": max_parallel,
    }
    value.update({key: item for key, item in overrides.items() if item is not None})
    if project_number is not None:
        value["project_number"] = project_number
    elif existing.get("project_number"):
        value["project_number"] = existing["project_number"]
    return write_session_config(repo, value), value


def remember_project(repo: Path, project_number: int) -> Path:
    value = load_session_config(repo)
    value["project_number"] = project_number
    return write_session_config(repo, value)


def render_session_config(value: dict) -> str:
    labels = (
        ("Profile", value.get("profile", "standard").title()),
        ("Project", f"#{value['project_number']}" if value.get("project_number") else "automatic"),
        ("Planning", value.get("planning_agent", "codex").title()),
        ("Implementation", value.get("agent", "codex").title()),
        ("QA", value.get("qa_agent", "codex").title()),
        ("Test approval", "Required" if value.get("review_qa_tests") else "Not required"),
        ("Parallel jobs", str(value.get("max_parallel", 1))),
    )
    return "Factory configuration\n" + "\n".join(f"  {label + ':':<16}{item}" for label, item in labels)
