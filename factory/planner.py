"""PRD-to-ticket planning and the explicit human approval gate."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from github_backend import GitHubBackend

AGENT_NAME = re.compile(r"[a-z][a-z0-9_-]{0,31}")


def validate_plan(plan: dict) -> list[str]:
    """Validate the editable plan and return ticket keys in dependency order."""
    if plan.get("plan_version") not in {1, 2}:
        raise ValueError("plan_version must be 1 or 2")
    project = plan.get("project")
    if not isinstance(project, dict) or not project.get("name") or not project.get("summary"):
        raise ValueError("project requires a name and summary")
    if not isinstance(plan.get("open_questions"), list):
        raise ValueError("open_questions must be a list")
    tickets = plan.get("tickets")
    if not isinstance(tickets, list) or not tickets:
        raise ValueError("the plan must contain at least one ticket")
    by_key = {}
    for ticket in tickets:
        key = ticket.get("key")
        if not isinstance(key, str) or not re.fullmatch(r"[A-Z][A-Z0-9_-]{0,15}", key):
            raise ValueError(f"invalid ticket key: {key!r}")
        if key in by_key:
            raise ValueError(f"duplicate ticket key: {key}")
        if not ticket.get("title") or not ticket.get("spec"):
            raise ValueError(f"{key} requires a title and spec")
        criteria = ticket.get("acceptance_criteria")
        if not isinstance(criteria, list) or not criteria or not all(isinstance(item, str) and item.strip() for item in criteria):
            raise ValueError(f"{key} requires at least one acceptance criterion")
        if not isinstance(ticket.get("dependencies"), list):
            raise ValueError(f"{key} dependencies must be a list")
        if not isinstance(ticket.get("agent"), str) or not AGENT_NAME.fullmatch(ticket["agent"]):
            raise ValueError(f"{key} agent must be a lowercase registered adapter name")
        by_key[key] = ticket
    for key, ticket in by_key.items():
        unknown = set(ticket["dependencies"]) - set(by_key)
        if unknown:
            raise ValueError(f"{key} has unknown dependencies: {', '.join(sorted(unknown))}")
        if key in ticket["dependencies"]:
            raise ValueError(f"{key} cannot depend on itself")
    ordered, temporary, permanent = [], set(), set()
    def visit(key):
        if key in temporary:
            raise ValueError(f"dependency cycle includes {key}")
        if key in permanent:
            return
        temporary.add(key)
        for dependency in by_key[key]["dependencies"]:
            visit(dependency)
        temporary.remove(key); permanent.add(key); ordered.append(key)
    for key in by_key:
        visit(key)
    return ordered


def dependency_waves(plan: dict) -> list[list[str]]:
    """Group a validated plan into the parallel waves used by the scheduler."""
    validate_plan(plan)
    remaining = {ticket["key"]: set(ticket["dependencies"]) for ticket in plan["tickets"]}
    completed, waves = set(), []
    while remaining:
        ready = [key for key, dependencies in remaining.items() if dependencies <= completed]
        if not ready:  # validate_plan already gives the more specific cycle error
            raise ValueError("ticket graph cannot be scheduled")
        waves.append(ready)
        completed.update(ready)
        for key in ready:
            remaining.pop(key)
    return waves


def render_review(plan: dict) -> str:
    lines = [f"# Ticket plan — {plan['project']['name']}", "", plan["project"]["summary"], ""]
    lines += [f"Plan ID: `{plan['plan_id']}`", f"Source: `{plan['source_prd']}`", ""]
    if plan["open_questions"]:
        lines += ["## Open questions", ""] + [f"- {question}" for question in plan["open_questions"]] + [""]
    lines += ["## Dependency map", "", "```mermaid", "flowchart LR"]
    node_ids = {ticket["key"]: f"N{index}" for index, ticket in enumerate(plan["tickets"])}
    for ticket in plan["tickets"]:
        title = ticket["title"].replace('"', "'")
        lines.append(f'  {node_ids[ticket["key"]]}["{ticket["key"]}: {title}"]')
        for dependency in ticket["dependencies"]:
            lines.append(f"  {node_ids[dependency]} --> {node_ids[ticket['key']]}")
    lines += ["```", "", "## Parallel waves", ""]
    for index, wave in enumerate(dependency_waves(plan), 1):
        lines.append(f"{index}. " + ", ".join(wave))
    lines += ["", "## Proposed tickets", ""]
    for ticket in plan["tickets"]:
        dependencies = ", ".join(ticket["dependencies"]) or "None"
        lines += [
            f"### {ticket['key']} — {ticket['title']}", "", ticket["spec"], "",
            f"**Agent:** {ticket['agent']}  ", f"**Depends on:** {dependencies}", "",
            "**Acceptance criteria**", "",
            *[f"- [ ] {criterion}" for criterion in ticket["acceptance_criteria"]], "",
        ]
    lines += [
        "## Human approval", "",
        "Edit the companion JSON file if needed. Clear every open question, then run:", "",
        f"`./factory/factory approve {plan['_plan_path']}`", "",
        "No issue or coding agent is created until that command is explicitly confirmed.", "",
    ]
    return "\n".join(lines)


def show_plan(plan: dict):
    print(f"\n{plan['project']['name']} — {plan['project']['summary']}")
    print(f"{'KEY':<8} {'AGENT':<8} {'DEPENDS':<18} TITLE")
    for ticket in plan["tickets"]:
        dependencies = ",".join(ticket["dependencies"]) or "—"
        print(f"{ticket['key']:<8} {ticket['agent']:<8} {dependencies:<18} {ticket['title']}")
    if plan["open_questions"]:
        print("\nOpen questions:")
        for question in plan["open_questions"]:
            print(f"- {question}")
    print("\nTicket details:")
    for ticket in plan["tickets"]:
        print(f"\n[{ticket['key']}] {ticket['title']}")
        print(ticket["spec"])
        print("Acceptance criteria:")
        for criterion in ticket["acceptance_criteria"]:
            print(f"  - {criterion}")


def issue_body(ticket: dict, numbers: dict[str, int], plan_id: str) -> str:
    dependencies = [numbers[key] for key in ticket["dependencies"]]
    dependency_section = "\n## Dependencies\nDepends-on: " + ", ".join(f"#{number}" for number in dependencies) + "\n" if dependencies else ""
    criteria = "\n".join(f"- [ ] {item}" for item in ticket["acceptance_criteria"])
    return (
        f"## Spec\n{ticket['spec']}\n\n## Acceptance criteria\n{criteria}\n"
        f"{dependency_section}\n## Agent\nagent: {ticket['agent']}\n\n"
        f"<!-- factory-plan:{plan_id}:{ticket['key']} -->"
    )


def approve_plan(
    repo: Path, plan_path: Path, project_number: int | None, assume_yes: bool,
    new_project_title: str | None = None,
) -> str:
    if project_number is not None and new_project_title:
        raise ValueError("use either --project-number or --new-project-title, not both")
    plan_path = plan_path.resolve()
    plan = json.loads(plan_path.read_text())
    order = validate_plan(plan)
    show_plan(plan)
    if plan["open_questions"]:
        raise ValueError("resolve and remove every open question before approval")
    if not assume_yes:
        try:
            answer = input(f"\nPublish these {len(plan['tickets'])} tickets to GitHub? Type APPROVE: ")
        except EOFError as exc:
            raise ValueError("interactive approval required; rerun in a terminal or pass --yes") from exc
        if answer != "APPROVE":
            raise ValueError("approval cancelled; no GitHub issues were changed")
    backend = GitHubBackend(repo, project_number)
    backend.preflight()
    if new_project_title:
        created_project = backend.json(
            "project", "create", "--owner", backend.owner,
            "--title", new_project_title, "--format", "json",
        )
        backend.project_number = int(created_project["number"])
        print(f"Created fresh GitHub Project #{backend.project_number}: {new_project_title}")
    repository = f"{backend.owner}/{backend.name}"
    backend.gh(
        "label", "create", "agent-ready", "--repo", repository, "--color", "c9f75f",
        "--description", "Ready for factory dispatch", "--force",
    )
    existing = backend.json(
        "issue", "list", "--repo", repository, "--state", "all", "--limit", 500,
        "--json", "number,title,body,url",
    )
    marker = re.compile(rf"<!-- factory-plan:{re.escape(plan['plan_id'])}:([^ ]+) -->")
    numbers = {}
    for issue in existing:
        match = marker.search(issue.get("body") or "")
        if match:
            numbers[match.group(1)] = int(issue["number"])
    by_key = {ticket["key"]: ticket for ticket in plan["tickets"]}
    created = set()
    for key in order:
        if key in numbers:
            continue
        ticket = by_key[key]
        result = backend.gh(
            "issue", "create", "--repo", repository, "--title", ticket["title"],
            "--body", issue_body(ticket, numbers, plan["plan_id"]), "--label", "agent-ready",
        )
        numbers[key] = int(result.stdout.strip().splitlines()[-1].rsplit("/", 1)[-1])
        created.add(numbers[key])
        print(f"Created #{numbers[key]}: {ticket['title']}")
    for key in order:  # apply any human edits and final dependency numbers
        ticket = by_key[key]
        backend.gh(
            "issue", "edit", numbers[key], "--repo", repository, "--title", ticket["title"],
            "--body", issue_body(ticket, numbers, plan["plan_id"]), "--add-label", "agent-ready",
        )
    remote = {ticket["number"]: ticket for ticket in backend.load()}
    for key in order:
        number = numbers[key]
        if number in created:
            status = "Backlog" if by_key[key]["dependencies"] else "Ready"
            backend.set_status(remote[number], status, "Approved ticket plan")
    project = backend.json("project", "view", backend.project_number, "--owner", backend.owner, "--format", "json")
    plan["publication"] = {
        "approved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "repository": repository, "project_number": backend.project_number,
        "issues": numbers,
    }
    plan_path.write_text(json.dumps(plan, indent=2) + "\n")
    print(f"Published {len(numbers)} tickets: {project['url']}")
    print("Review the GitHub board, then start with `./factory/factory run`.")
    return project["url"]
