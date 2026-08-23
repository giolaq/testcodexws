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


def resolve_repository(repo: Path, supplied: str | None) -> str:
    command = ["repo", "view"]
    if supplied:
        command.append(supplied)
    result = gh(*command, "--json", "nameWithOwner", cwd=repo, check=False)
    if result.returncode:
        if not supplied and "no git remotes found" in (result.stderr + result.stdout).lower():
            raise SystemExit(
                "No GitHub repository is connected to this checkout.\n"
                "Either add an origin remote, or rerun with "
                "`--github-repo OWNER/REPOSITORY`."
            )
        raise SystemExit(result.stderr.strip() or result.stdout.strip())
    return json.loads(result.stdout)["nameWithOwner"]


def main():
    parser = argparse.ArgumentParser(description="Seed a deterministic Software (re)-Factory scenario")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--github-repo", metavar="OWNER/REPOSITORY")
    parser.add_argument("--agent", default="codex", help="registered implementation adapter name")
    parser.add_argument("--scenario", choices=["tv", "recipe-rebrand"], default="tv")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    scenario = repo / "factory/scenarios" / args.scenario / "tickets.json"
    bundled = Path(__file__).with_name("scenarios") / args.scenario / "tickets.json"
    legacy = repo / "factory/seed/tickets.json"
    source = scenario if scenario.is_file() else bundled if bundled.is_file() else legacy
    if not source.is_file():
        raise SystemExit(f"No deterministic scenario found for {args.scenario}.")
    tickets = json.loads(source.read_text())
    if args.dry_run:
        for ticket in tickets:
            print(f"#{ticket['number']} {ticket['title']}")
        return
    gh("auth", "status", cwd=repo)
    repository = resolve_repository(repo, args.github_repo)
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
