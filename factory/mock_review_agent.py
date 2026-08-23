#!/usr/bin/env python3
"""Deterministic Code Review Agent used by the credential-free rehearsal."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


parser = argparse.ArgumentParser()
parser.add_argument("ticket", type=int)
parser.add_argument("prompt")
parser.add_argument("--attempt", type=int, default=1)
args = parser.parse_args()

assignment = Path(args.prompt).read_text()
demonstrate_comments = "Deliver searchable recipe data and API contracts" in assignment
if args.ticket == 1 and args.attempt == 1 and demonstrate_comments:
    result = {
        "schema_version": 2,
        "decision": "REQUEST_CHANGES",
        "summary": "The recipe loader does not reject duplicate recipe identifiers.",
        "findings": [{
            "severity": "blocking",
            "path": "demo-app/recipe_api.py",
            "line": 12,
            "message": "Reject duplicate recipe IDs before building lookup tables so the API contract remains deterministic.",
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
