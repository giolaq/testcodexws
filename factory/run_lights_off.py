#!/usr/bin/env python3
"""Launch the workshop control agent without invoking factory orchestration."""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

from orchestrator import resolve_codex_cli


def agent_command(agent: str, prompt: str) -> list[str]:
    if agent == "codex":
        return [
            resolve_codex_cli(), "exec", "--sandbox", "workspace-write",
            "--ephemeral", prompt,
        ]

    executable_name = "cursor-agent" if agent == "cursor" else "claude"
    executable = shutil.which(executable_name)
    if not executable:
        raise RuntimeError(f"{executable_name} is not installed or not on PATH")
    if agent == "claude":
        return [executable, "-p", prompt, "--permission-mode", "acceptEdits"]
    return [executable, "-p", prompt]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run one autonomous agent as the lights-off workshop control.",
    )
    parser.add_argument("--agent", choices=["codex", "claude", "cursor"], default="codex")
    parser.add_argument(
        "--prompt",
        type=Path,
        help="Prompt file (defaults to the TableStory control prompt)",
    )
    args = parser.parse_args()

    repo = Path(__file__).resolve().parent.parent
    prompt_path = args.prompt or (
        repo / "factory/scenarios/recipe-rebrand/lights-off-prompt.md"
    )
    if not prompt_path.is_absolute():
        prompt_path = repo / prompt_path
    if not prompt_path.is_file():
        parser.error(f"prompt file not found: {prompt_path}")

    print(f"Starting the {args.agent} lights-off control. Do not intervene while it runs.", flush=True)
    return subprocess.run(
        agent_command(args.agent, prompt_path.read_text()), cwd=repo,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
