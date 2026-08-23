#!/usr/bin/env python3
"""Deterministic supervisor adapter for credential-free Rehearsal Runs."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("prompt")
    args = parser.parse_args()
    text = Path(args.prompt).read_text()
    merge_match = re.search(
        r"<merge-supervisor-input>\s*(\{.*\})\s*</merge-supervisor-input>", text, re.DOTALL,
    )
    if merge_match:
        value = json.loads(merge_match.group(1))
        print(json.dumps({
            "schema_version": 1,
            "summary": "The candidate is approved and every required gate passed; merge it.",
            "action": "MERGE",
            "ticket": value["ticket"],
            "pull_request": value["pull_request"],
            "candidate_head": value["candidate_head"],
        }))
        return
    match = re.search(r"<supervisor-input>\s*(\{.*\})\s*</supervisor-input>", text, re.DOTALL)
    if not match:
        raise SystemExit("supervisor input not found")
    value = json.loads(match.group(1))
    ready = sorted(value["ready_tickets"], key=lambda ticket: ticket["number"])
    selected = ready[: int(value["max_parallel"])]
    print(json.dumps({
        "schema_version": 1,
        "summary": f"Dispatch {len(selected)} dependency-ready ticket(s) in number order.",
        "dispatch": [
            {
                "ticket": ticket["number"],
                "instruction": (
                    "Stay within this Ticket, preserve its declared dependencies, and report verification "
                    "and unresolved risks through the required Handoff Receipt."
                ),
            }
            for ticket in selected
        ],
        "block": [],
    }))


if __name__ == "__main__":
    main()
