"""Causal red/green evidence for QA-owned Acceptance Tests.

The module deliberately owns only two judgments: how to run the exact accepted
test files, and whether a bounded runner result is a behavior assertion or an
execution problem. The orchestrator owns lifecycle decisions and persistence.
"""

from __future__ import annotations

import re
import shlex
from pathlib import PurePosixPath


_COLLECTION_MARKERS = (
    "error collecting",
    "collection error",
    "modulenotfounderror",
    "importerror",
    "cannot find module",
    "syntaxerror",
    "no tests ran",
    "no test files found",
    "test suite failed to run",
)
_ASSERTION_MARKERS = (
    "assertionerror",
    "err_assertion",
    "assert ",
    "not ok",
    "expected:",
    "received:",
    "failed ",
    " failures",
)


def focused_test_command(paths: list[str], python: str) -> str:
    """Return a shell-safe command that runs only the accepted QA files."""
    if not paths:
        raise ValueError("focused Acceptance Test command requires at least one test file")
    suffixes = {PurePosixPath(path).suffix.lower() for path in paths}
    quoted = " ".join(shlex.quote(path) for path in sorted(paths))
    if suffixes == {".py"}:
        return f"{shlex.quote(python)} -m pytest -q {quoted}"
    if suffixes <= {".js", ".cjs", ".mjs"}:
        return f"node --test {quoted}"
    if len(suffixes) > 1:
        raise ValueError("focused Acceptance Tests must use one supported test runner")
    raise ValueError(
        "no supported focused test runner for "
        + ", ".join(sorted(suffixes))
        + "; use Python pytest or Node.js test files"
    )


def classify_focused_result(exit_code: int, output: str) -> str:
    """Classify runner output without mistaking broken infrastructure for red."""
    lowered = output.lower()
    skipped = bool(
        re.search(r"\b[1-9]\d*\s+skipped\b", lowered)
        or re.search(r"#\s*skipped\s+[1-9]\d*\b", lowered)
    )
    if skipped:
        return "skipped"
    if exit_code == 0:
        return "pass"
    if exit_code == 124 or "timed out" in lowered:
        return "timeout"
    if exit_code == 127 or "command not found" in lowered:
        return "command_error"
    if any(marker in lowered for marker in _COLLECTION_MARKERS):
        return "collection_error"
    if exit_code == 1 and any(marker in lowered for marker in _ASSERTION_MARKERS):
        return "behavior_assertion"
    return "unrelated_failure"
