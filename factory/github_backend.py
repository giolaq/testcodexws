"""Small `gh`-CLI backend for issues, Projects v2 status, and pull requests."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from github_repository import parse_github_repository, repository_from_remote
from session_config import load_session_config
from run_summary import parse_factory_run_summary

STATES = ["Backlog", "Ready", "In Progress", "QA Review", "Verifying", "In Review", "Done", "Blocked"]
COLORS = ["GRAY", "BLUE", "YELLOW", "PINK", "ORANGE", "PURPLE", "GREEN", "RED"]


class GitHubError(RuntimeError):
    pass


class GitHubBackend:
    def __init__(self, repo: Path, project_number=None, repository=None):
        self.repo = repo
        self.project_number = project_number
        if repository is None:
            repository = load_session_config(repo).get("github_repository")
        self.repository = parse_github_repository(repository) if repository else None
        self.owner = self.name = self.default_branch = self.project_id = self.field_id = None
        self.options, self.items = {}, {}
        self._project_items_loaded = False

    def gh(self, *args, input_data=None, check=True, cwd=None, env=None):
        result = subprocess.run(
            ["gh", *map(str, args)], cwd=cwd or self.repo, text=True, capture_output=True,
            input=json.dumps(input_data) if input_data else None,
            env=env,
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
        target = [self.repository.slug] if self.repository else []
        result = self.gh(
            "repo", "view", *target, "--json", "nameWithOwner,defaultBranchRef", check=False,
        )
        if result.returncode:
            if "no git remotes found" in (result.stderr + result.stdout).lower():
                raise GitHubError(
                    "No GitHub repository is connected. Add an origin remote before running the factory."
                )
            raise GitHubError(result.stderr.strip() or result.stdout.strip())
        details = json.loads(result.stdout)
        repo = details["nameWithOwner"]
        self.owner, self.name = repo.split("/", 1)
        if self.repository:
            origin = subprocess.run(
                ["git", "remote", "get-url", "origin"], cwd=self.repo,
                text=True, capture_output=True,
            )
            connected = repository_from_remote(origin.stdout.strip()) if origin.returncode == 0 else None
            if not connected or connected.slug.lower() != repo.lower():
                raise GitHubError(
                    "The local origin does not match the configured GitHub repository. "
                    "Reconnect it in the Control Center."
                )
        self.default_branch = (details.get("defaultBranchRef") or {}).get("name") or "main"

    @staticmethod
    def claim_ref(number: int) -> str:
        return f"refs/heads/factory-claims/ticket-{int(number)}"

    def _git(self, *args: str, input_text: str | None = None, env=None, check=True):
        result = subprocess.run(
            ["git", *args], cwd=self.repo, text=True, capture_output=True,
            input=input_text, env=env,
        )
        if check and result.returncode:
            raise GitHubError(result.stderr.strip() or result.stdout.strip())
        return result

    def read_claim(self, number: int) -> dict | None:
        """Read the durable owner of a deterministic remote Ticket claim."""
        ref = self.claim_ref(number)
        listing = self._git("ls-remote", "origin", ref).stdout.strip()
        if not listing:
            return None
        claim_sha = listing.split()[0]
        self._git("fetch", "--quiet", "origin", ref)
        message = self._git("show", "-s", "--format=%B", claim_sha).stdout
        marker = next((line for line in message.splitlines() if line.startswith("factory-claim:v1 ")), "")
        try:
            value = json.loads(marker.removeprefix("factory-claim:v1 "))
        except json.JSONDecodeError as exc:
            raise GitHubError(f"Remote claim for Ticket #{number} has invalid metadata") from exc
        if value.get("ticket") != int(number) or not value.get("run_id"):
            raise GitHubError(f"Remote claim for Ticket #{number} has invalid ownership metadata")
        return {**value, "claim_sha": claim_sha, "ref": ref}

    def claim_ticket(self, ticket: dict, run_id: str, base_revision: str) -> dict:
        """Atomically claim a Ticket; the first non-force remote push wins."""
        number = int(ticket["number"])
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", run_id):
            raise GitHubError("Factory run ID is invalid for a remote claim")
        if not re.fullmatch(r"[a-f0-9]{7,64}", base_revision):
            raise GitHubError("Ticket base revision is invalid for a remote claim")
        existing = self.read_claim(number)
        if existing:
            return {
                **existing,
                "owned": existing["run_id"] == run_id,
                "resumed": existing["run_id"] == run_id,
                "owner_run_id": existing["run_id"],
            }
        payload = {
            "ticket": number,
            "run_id": run_id,
            "base_revision": base_revision,
            "claimed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        tree = self._git("rev-parse", f"{base_revision}^{{tree}}").stdout.strip()
        identity_env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "Software (re)-Factory",
            "GIT_AUTHOR_EMAIL": "factory@example.invalid",
            "GIT_COMMITTER_NAME": "Software (re)-Factory",
            "GIT_COMMITTER_EMAIL": "factory@example.invalid",
        }
        claim_sha = self._git(
            "commit-tree", tree, "-p", base_revision,
            input_text="factory-claim:v1 " + json.dumps(payload, sort_keys=True) + "\n",
            env=identity_env,
        ).stdout.strip()
        ref = self.claim_ref(number)
        pushed = self._git("push", "origin", f"{claim_sha}:{ref}", check=False)
        if pushed.returncode:
            winner = self.read_claim(number)
            if winner:
                return {
                    **winner,
                    "owned": winner["run_id"] == run_id,
                    "resumed": winner["run_id"] == run_id,
                    "owner_run_id": winner["run_id"],
                }
            raise GitHubError(pushed.stderr.strip() or pushed.stdout.strip())
        record = {**payload, "claim_sha": claim_sha, "ref": ref}
        if self.owner and self.name:
            self.gh(
                "issue", "comment", number, "--repo", f"{self.owner}/{self.name}",
                "--body", (
                    "<!-- factory-claim:v1 -->\n"
                    f"Factory run `{run_id}` claimed this Ticket at base `{base_revision}`.\n"
                    f"Claimed at `{payload['claimed_at']}`.\n"
                    f"Remote claim: `{ref}`"
                ),
                check=False,
            )
        return {**record, "owned": True, "resumed": False, "owner_run_id": run_id}

    def release_claim(self, number: int, run_id: str, *, reason: str) -> dict:
        """Release only a claim owned by this run after an explicit operator action."""
        reason = " ".join(reason.split())[:300]
        if not reason:
            raise GitHubError("Releasing a remote claim requires an audit reason")
        claim = self.read_claim(number)
        if not claim:
            return {"released": False, "reason": "claim not found"}
        if claim["run_id"] != run_id:
            raise GitHubError(
                f"Ticket #{number} is owned by {claim['run_id']}; run {run_id} cannot release it"
            )
        result = self._git("push", "origin", f":{claim['ref']}", check=False)
        if result.returncode:
            raise GitHubError(result.stderr.strip() or result.stdout.strip())
        if self.owner and self.name:
            self.gh(
                "issue", "comment", number, "--repo", f"{self.owner}/{self.name}",
                "--body", (
                    "<!-- factory-claim-release:v1 -->\n"
                    f"Operator released Factory run `{run_id}` claim. Reason: {reason}"
                ),
                check=False,
            )
        return {"released": True, "ticket": int(number), "run_id": run_id, "reason": reason}

    def publish_run_summary(self, number: int, run_id: str, body: str) -> dict:
        """Create or update the one durable sanitized summary for this run/Ticket."""
        marker = f"<!-- factory-run:v1 ticket={int(number)} run={run_id} -->"
        if marker not in body:
            raise GitHubError("Factory Run summary is missing its versioned identity marker")
        comments = self.json(
            "api", f"repos/{self.owner}/{self.name}/issues/{int(number)}/comments", "--paginate",
        )
        existing = next(
            (item for item in comments if marker in str(item.get("body", ""))), None,
        )
        if existing:
            result = self.json(
                "api", "--method", "PATCH", existing["url"], "-f", f"body={body}",
            )
            return {"mode": "updated", "url": result.get("html_url", existing.get("html_url", ""))}
        result = self.json(
            "api", "--method", "POST",
            f"repos/{self.owner}/{self.name}/issues/{int(number)}/comments",
            "-f", f"body={body}",
        )
        return {"mode": "created", "url": result.get("html_url", "")}

    def read_run_summary(self, number: int) -> dict | None:
        """Read the newest valid sanitized Factory Run summary for a Ticket."""
        comments = self.json(
            "api", f"repos/{self.owner}/{self.name}/issues/{int(number)}/comments", "--paginate",
        )
        ordered = sorted(
            comments,
            key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""),
            reverse=True,
        )
        for comment in ordered:
            payload = parse_factory_run_summary(str(comment.get("body", "")), ticket=int(number))
            if payload is not None:
                return payload
        return None

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
                "--json", "number,title,body,state,url,labels,updatedAt",
            )
            for issue in issues:
                labels = [label["name"] for label in issue.get("labels", [])]
                state_label = next((label[6:].replace("-", " ").title() for label in labels if label.startswith("state:")), "Backlog")
                issue.update(status=state_label if state_label in STATES else "Backlog", labels=labels, pr_url="")
            return issues
        self.ensure_project()
        issues = self.json(
            "issue", "list", "--repo", f"{self.owner}/{self.name}", "--state", "all", "--limit", 200,
            "--json", "number,title,body,state,url,labels,updatedAt",
        )
        raw_items = self._load_project_items()
        tickets = []
        for issue in issues:
            number = int(issue["number"])
            if number not in self.items:
                continue
            status = next((i.get("status") for i in raw_items if i.get("content", {}).get("number") == number), None) or "Backlog"
            labels = [label["name"] for label in issue.get("labels", [])]
            pr = self.existing_pr(number)
            summary = self.read_run_summary(number)
            tickets.append({
                **issue,
                "status": status if status in STATES else "Backlog",
                "labels": labels,
                "pr_url": pr.get("url", "") if pr else "",
                "pull_request": pr or {},
                "remote_run_summary": summary or {},
            })
        self._ensure_labels()
        return tickets

    def _load_project_items(self):
        raw_items = self.json(
            "project", "item-list", self.project_number, "--owner", self.owner,
            "--limit", 500, "--format", "json",
        ).get("items", [])
        self.items = {}
        for item in raw_items:
            content = item.get("content", {})
            if content.get("type") == "Issue" and content.get("number"):
                self.items[int(content["number"])] = item["id"]
        self._project_items_loaded = True
        return raw_items

    def add_issue_to_project(self, number: int, url: str) -> bool:
        """Add one explicitly approved Ticket without importing repository backlog."""
        if self.project_id is None:
            self.ensure_project()
        if not self._project_items_loaded:
            self._load_project_items()
        number = int(number)
        if number in self.items:
            return False
        item = self.json(
            "project", "item-add", self.project_number, "--owner", self.owner,
            "--url", url, "--format", "json",
        )
        self.items[number] = item["id"]
        return True

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
            "--json", "number,title,url,state,mergedAt,mergeCommit,headRefName,headRefOid,baseRefName,reviewDecision",
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

    def submit_agent_review(self, pr_url: str, decision: str, body: str) -> dict:
        """Publish an agent decision, with an explicit self-review fallback.

        GitHub rejects formal reviews when the authenticated account authored the
        PR. In that common workshop setup, retain the same evidence as a comment
        and mark it as an internal Factory decision rather than pretending it
        satisfies branch-protection review requirements.
        """
        flag = "--approve" if decision == "APPROVE" else "--request-changes"
        reviewer_token = os.environ.get("FACTORY_REVIEW_GH_TOKEN", "").strip()
        review_options = {"check": False}
        if reviewer_token:
            review_options["env"] = {**os.environ, "GH_TOKEN": reviewer_token}
        official = self.gh("pr", "review", pr_url, flag, "--body", body, **review_options)
        if official.returncode == 0:
            return {"published": True, "official": True, "mode": "github-review"}
        fallback_body = (
            body
            + "\n\n> GitHub did not accept this as a formal review, usually because the workshop "
            "operator authored the PR. This remains a validated Factory decision and does not "
            "satisfy branch-protection approval requirements."
        )
        comment = self.gh("pr", "comment", pr_url, "--body", fallback_body, check=False)
        if comment.returncode:
            detail = (official.stderr or official.stdout or comment.stderr or comment.stdout).strip()
            raise GitHubError(f"Could not publish Code Review Agent decision: {detail}")
        return {
            "published": True,
            "official": False,
            "mode": "factory-comment",
            "warning": (official.stderr or official.stdout).strip(),
        }

    def merge_pr(self, pr_url: str):
        result = self.gh("pr", "merge", pr_url, "--merge", check=False)
        if result.returncode:
            try:
                merged = self.json("pr", "view", pr_url, "--json", "mergedAt")
            except GitHubError:
                merged = {}
            if not merged.get("mergedAt"):
                raise GitHubError(result.stderr.strip() or result.stdout.strip())

    def assert_pr_head(self, pr_url: str, expected_head: str):
        value = self.json("pr", "view", pr_url, "--json", "headRefOid")
        if value.get("headRefOid") != expected_head:
            raise GitHubError(
                "Pull request head changed after Code Review Agent approval; review the new revision before merge."
            )

    def merged_pr(self, ticket):
        pr = self.existing_pr(ticket["number"])
        if not pr or not pr.get("mergedAt"):
            return None
        return pr

    def close_issue(self, ticket):
        """Close the Issue only after the orchestrator validates the merged revision."""
        self.gh(
            "issue", "close", ticket["number"],
            "--repo", f"{self.owner}/{self.name}", check=False,
        )

    def is_merged(self, ticket):
        return self.merged_pr(ticket) is not None
