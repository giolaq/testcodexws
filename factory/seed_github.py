#!/usr/bin/env python3
"""Create the workshop backlog in a fresh GitHub repository using `gh`."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path


def gh(*args, cwd: Path, check=True):
    result = subprocess.run(["gh", *args], cwd=cwd, text=True, capture_output=True)
    if check and result.returncode:
        raise SystemExit(result.stderr.strip() or result.stdout.strip())
    return result


def main():
    parser = argparse.ArgumentParser(description="Seed the Pocket Cinema TV-refactor issues")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--agent", choices=["claude", "codex", "cursor"], default="codex")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    tickets = json.loads((repo / "factory/seed/tickets.json").read_text())
    if args.dry_run:
        for ticket in tickets:
            print(f"#{ticket['number']} {ticket['title']}")
        return
    gh("auth", "status", cwd=repo)
    repository = json.loads(gh("repo", "view", "--json", "nameWithOwner", cwd=repo).stdout)["nameWithOwner"]
    gh("label", "create", "agent-ready", "--repo", repository, "--color", "c9f75f", "--description", "Ready for factory dispatch", "--force", cwd=repo)
    existing = json.loads(gh("issue", "list", "--repo", repository, "--state", "all", "--limit", "200", "--json", "number,title", cwd=repo).stdout)
    by_title = {issue["title"]: int(issue["number"]) for issue in existing}
    number_map = {}
    for ticket in tickets:
        body = ticket["body"].replace("agent: mock", f"agent: {args.agent}")
        body = re.sub(r"#(\d+)", lambda match: f"#{number_map.get(int(match.group(1)), int(match.group(1)))}", body)
        if ticket["title"] in by_title:
            actual = by_title[ticket["title"]]
            gh("issue", "edit", str(actual), "--repo", repository, "--body", body, "--add-label", "agent-ready", cwd=repo)
            print(f"Reused #{actual}: {ticket['title']}")
        else:
            result = gh(
                "issue", "create", "--repo", repository, "--title", ticket["title"],
                "--body", body, "--label", "agent-ready", cwd=repo,
            )
            url = result.stdout.strip().splitlines()[-1]
            actual = int(url.rsplit("/", 1)[-1])
            print(f"Created #{actual}: {ticket['title']}")
        number_map[int(ticket["number"])] = actual


if __name__ == "__main__":
    main()
