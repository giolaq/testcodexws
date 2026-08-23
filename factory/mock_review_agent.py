#!/usr/bin/env python3
"""Deterministic Code Review Agent used by the credential-free rehearsal."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


parser = argparse.ArgumentParser()
parser.add_argument("ticket", type=int)
parser.add_argument("prompt")
parser.add_argument("--attempt", type=int, default=1)
args = parser.parse_args()

assignment = Path(args.prompt).read_text()
recipe_demo = "Deliver searchable recipe data and API contracts" in assignment
live_smoke = "factory-release-smoke:review-rework" in assignment
demonstrate_comments = args.attempt == 1 and (
    (args.ticket == 1 and recipe_demo) or live_smoke
)
changed_section = re.search(
    r"(?ms)^## Changed paths\s*\n(?P<body>.*?)(?=^## |\Z)", assignment,
)
changed_paths = re.findall(r"`([^`]+)`", changed_section.group("body")) if changed_section else []
review_path = next(
    (path for path in changed_paths if "/tests/" not in f"/{path}/" and not Path(path).name.startswith("test_")),
    changed_paths[0] if changed_paths else "demo-app/recipe_api.py",
)
if demonstrate_comments:
    if live_smoke:
        summary = "The endpoint implementation needs one maintainability correction before release."
        message = "Add a concise explanatory comment or docstring for the new endpoint contract, then rerun verification."
        line = 1
    else:
        summary = "The recipe loader does not reject duplicate recipe identifiers."
        message = "Reject duplicate recipe IDs before building lookup tables so the API contract remains deterministic."
        line = 12
    result = {
        "schema_version": 2,
        "decision": "REQUEST_CHANGES",
        "summary": summary,
        "findings": [{
            "severity": "blocking",
            "path": review_path,
            "line": line,
            "message": message,
        }],
    }
else:
    result = {
        "schema_version": 2,
        "decision": "APPROVE",
        "summary": "The candidate diff is ticket-scoped, covered by the recorded gates, and approved for Supervisor merge review.",
        "findings": [],
    }

print(json.dumps(result))
