"""Small `gh`-CLI backend for issues, Projects v2 status, and pull requests."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

STATES = ["Backlog", "Ready", "In Progress", "Verifying", "In Review", "Done", "Blocked"]
COLORS = ["GRAY", "BLUE", "YELLOW", "ORANGE", "PURPLE", "GREEN", "RED"]


class GitHubError(RuntimeError):
    pass


class GitHubBackend:
    def __init__(self, repo: Path, project_number=None):
        self.repo = repo
        self.project_number = project_number
        self.owner = self.name = self.project_id = self.field_id = None
        self.options, self.items = {}, {}

    def gh(self, *args, input_data=None, check=True, cwd=None):
        result = subprocess.run(
            ["gh", *map(str, args)], cwd=cwd or self.repo, text=True, capture_output=True,
            input=json.dumps(input_data) if input_data else None,
        )
        if check and result.returncode:
            raise GitHubError(result.stderr.strip() or result.stdout.strip())
        return result

    def json(self, *args):
        result = self.gh(*args)
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise GitHubError(f"gh returned invalid JSON for {' '.join(map(str, args))}") from exc

    def preflight(self):
        if not shutil.which("gh"):
            raise GitHubError("GitHub CLI not found. Install `gh`, then run `gh auth login`.")
        if self.gh("auth", "status", check=False).returncode:
            raise GitHubError("GitHub CLI is not authenticated. Run `gh auth login`.")
        result = self.gh("repo", "view", "--json", "nameWithOwner", check=False)
        if result.returncode:
            if "no git remotes found" in (result.stderr + result.stdout).lower():
                raise GitHubError(
                    "No GitHub repository is connected. Add an origin remote before running the factory."
                )
            raise GitHubError(result.stderr.strip() or result.stdout.strip())
        repo = json.loads(result.stdout)["nameWithOwner"]
        self.owner, self.name = repo.split("/", 1)

    def ensure_project(self):
        projects = self.json("project", "list", "--owner", self.owner, "--format", "json").get("projects", [])
        project = next((p for p in projects if p.get("number") == self.project_number), None)
        if not project and self.project_number is None:
            project = next((p for p in projects if p.get("title") == "Software (re)-Factory"), None)
        if not project:
            if self.project_number:
                raise GitHubError(f"Project #{self.project_number} was not found for {self.owner}")
            project = self.json("project", "create", "--owner", self.owner, "--title", "Software (re)-Factory", "--format", "json")
        self.project_number, self.project_id = int(project["number"]), project["id"]
        fields = self.json("project", "field-list", self.project_number, "--owner", self.owner, "--format", "json").get("fields", [])
        field = next((f for f in fields if f.get("name") == "Status"), None)
        if not field:
            field = self.json(
                "project", "field-create", self.project_number, "--owner", self.owner, "--name", "Status",
                "--data-type", "SINGLE_SELECT", "--single-select-options", ",".join(STATES), "--format", "json",
            )
        if [o["name"] for o in field.get("options", [])] != STATES:
            self._set_status_options(field["id"], field.get("options", []))
            fields = self.json("project", "field-list", self.project_number, "--owner", self.owner, "--format", "json").get("fields", [])
            field = next(f for f in fields if f.get("name") == "Status")
        self.field_id = field["id"]
        self.options = {o["name"]: o["id"] for o in field["options"]}

    def _set_status_options(self, field_id, existing):
        query = """mutation($field:ID!,$options:[ProjectV2SingleSelectFieldOptionInput!]!){
          updateProjectV2Field(input:{fieldId:$field,singleSelectOptions:$options}){projectV2Field{... on ProjectV2SingleSelectField{id}}}}
        """
        existing_ids = {option["name"]: option["id"] for option in existing}
        options = []
        for name, color in zip(STATES, COLORS):
            option = {"name": name, "color": color, "description": "Factory pipeline state"}
            if name in existing_ids:
                option["id"] = existing_ids[name]
            options.append(option)
        payload = {"query": query, "variables": {"field": field_id, "options": options}}
        self.gh("api", "graphql", "--input", "-", input_data=payload)

    def load(self, read_only=False):
        self.preflight()
        if read_only:
            issues = self.json(
                "issue", "list", "--repo", f"{self.owner}/{self.name}", "--state", "all", "--limit", 200,
                "--json", "number,title,body,state,url,labels",
            )
            for issue in issues:
                labels = [label["name"] for label in issue.get("labels", [])]
                state_label = next((label[6:].replace("-", " ").title() for label in labels if label.startswith("state:")), "Backlog")
                issue.update(status=state_label if state_label in STATES else "Backlog", labels=labels, pr_url="")
            return issues
        self.ensure_project()
        issues = self.json(
            "issue", "list", "--repo", f"{self.owner}/{self.name}", "--state", "all", "--limit", 200,
            "--json", "number,title,body,state,url,labels",
        )
        raw_items = self.json("project", "item-list", self.project_number, "--owner", self.owner, "--limit", 500, "--format", "json").get("items", [])
        for item in raw_items:
            content = item.get("content", {})
            if content.get("type") == "Issue" and content.get("number"):
                self.items[int(content["number"])] = item["id"]
        tickets = []
        for issue in issues:
            number = int(issue["number"])
            if number not in self.items:
                item = self.json(
                    "project", "item-add", self.project_number, "--owner", self.owner,
                    "--url", issue["url"], "--format", "json",
                )
                self.items[number] = item["id"]
            status = next((i.get("status") for i in raw_items if i.get("content", {}).get("number") == number), None) or "Backlog"
            labels = [label["name"] for label in issue.get("labels", [])]
            pr = self.existing_pr(number)
            tickets.append({**issue, "status": status if status in STATES else "Backlog", "labels": labels, "pr_url": pr.get("url", "") if pr else ""})
        self._ensure_labels()
        return tickets

    def _ensure_labels(self):
        for status in STATES:
            name = "state:" + status.lower().replace(" ", "-")
            self.gh("label", "create", name, "--repo", f"{self.owner}/{self.name}", "--color", "6e7781", "--force", check=False)

    def set_status(self, ticket, status, note=""):
        item = self.items.get(ticket["number"])
        if not item:
            return
        self.gh(
            "project", "item-edit", "--id", item, "--project-id", self.project_id,
            "--field-id", self.field_id, "--single-select-option-id", self.options[status],
        )
        state_labels = [label for label in ticket.get("labels", []) if label.startswith("state:")]
        for label in state_labels:
            self.gh("issue", "edit", ticket["number"], "--repo", f"{self.owner}/{self.name}", "--remove-label", label, check=False)
        new_label = "state:" + status.lower().replace(" ", "-")
        self.gh("issue", "edit", ticket["number"], "--repo", f"{self.owner}/{self.name}", "--add-label", new_label)
        ticket["labels"] = [l for l in ticket.get("labels", []) if not l.startswith("state:")] + [new_label]
        if status == "Blocked" and note:
            self.gh("issue", "comment", ticket["number"], "--repo", f"{self.owner}/{self.name}", "--body", f"Factory blocked this ticket:\n\n```text\n{ticket.get('failure', note)[-3000:]}\n```")

    def existing_pr(self, number):
        prs = self.json(
            "pr", "list", "--repo", f"{self.owner}/{self.name}", "--state", "all", "--limit", 100,
            "--json", "number,title,url,state,mergedAt,headRefName",
        )
        return next((p for p in prs if p["headRefName"].startswith(f"factory/{number}-")), None)

    def publish(self, ticket, worktree: Path):
        pushed = subprocess.run(
            ["git", "push", "-u", "origin", ticket["branch"]], cwd=worktree,
            text=True, capture_output=True,
        )
        if pushed.returncode:
            raise GitHubError(pushed.stderr.strip() or pushed.stdout.strip())
        existing = self.existing_pr(ticket["number"])
        if existing:
            return existing["url"]
        result = self.gh(
            "pr", "create", "--repo", f"{self.owner}/{self.name}",
            "--title", f"#{ticket['number']}: {ticket['title']}", "--body", f"Closes #{ticket['number']}",
            cwd=worktree,
        )
        url = result.stdout.strip().splitlines()[-1]
        self.gh("issue", "comment", ticket["number"], "--repo", f"{self.owner}/{self.name}", "--body", f"Factory opened {url}")
        return url

    def is_merged(self, ticket):
        pr = self.existing_pr(ticket["number"])
        if not pr or not pr.get("mergedAt"):
            return False
        self.gh("issue", "close", ticket["number"], "--repo", f"{self.owner}/{self.name}", check=False)
        return True
