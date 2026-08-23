"""Read-only operational monitoring with optional idempotent GitHub publication."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from factory_charter import FactoryCharter, FactoryCharterError
from project_contract import ProjectContract, ProjectContractError


def _finding(kind: str, summary: str, detail: str, *, severity="warning") -> dict:
    identity = hashlib.sha256(f"{kind}\0{summary}".encode()).hexdigest()[:16]
    return {
        "id": identity, "kind": kind, "severity": severity,
        "summary": summary, "detail": detail,
    }


class FactoryMonitor:
    def __init__(self, repo: Path, backend=None):
        self.repo = repo.resolve()
        self.backend = backend

    def collect(self) -> dict:
        """Inspect state without modifying source, claims, Tickets, PRs, or branches."""
        before = self._git("status", "--porcelain")
        findings = []
        try:
            charter = FactoryCharter.load(self.repo, require_approved=True)
        except FactoryCharterError as exc:
            findings.append(_finding("charter-drift", "Factory Charter needs review", str(exc), severity="blocking"))
            charter = None
        try:
            ProjectContract.load(self.repo, require=True)
        except ProjectContractError as exc:
            findings.append(_finding("project-contract-drift", "Project Contract needs review", str(exc), severity="blocking"))

        state_path = self.repo / ".factory/state.json"
        try:
            state = json.loads(state_path.read_text()) if state_path.is_file() else {"tickets": []}
        except json.JSONDecodeError:
            state = {"tickets": []}
            findings.append(_finding("state", "Factory state is unreadable", "Repair or reset only the named local run.", severity="blocking"))
        attention = state.get("human_attention", {})
        if attention.get("dispatch_paused"):
            findings.append(_finding(
                "review-wait", "Human attention is blocking dispatch",
                attention.get("reason", "The human decision queue is full."),
            ))
        messages = []
        for ticket in state.get("tickets", []):
            for item in ((ticket.get("code_review") or {}).get("result") or {}).get("findings", []):
                message = " ".join(str(item.get("message", "")).lower().split())
                if message:
                    messages.append(message)
        for message, count in Counter(messages).items():
            if count >= 2:
                findings.append(_finding(
                    "repeated-verifier-finding",
                    f"Code review repeated the same finding {count} times",
                    message[:500],
                ))

        hotspots = Counter(
            line for line in self._git(
                "log", "-n", "50", "--pretty=format:", "--name-only",
            ).splitlines() if line.strip()
        )
        changed_hotspots = [
            {"path": path, "changes": count} for path, count in hotspots.most_common(10)
        ]
        ci = []
        advisories = []
        remote_tickets = []
        remote_claims = []
        limitations = []
        if self.backend:
            try:
                remote_tickets = self.backend.load(read_only=True)
                by_number = {int(item["number"]): item for item in remote_tickets}
                current_time = datetime.now(timezone.utc)
                for ticket in remote_tickets:
                    status = ticket.get("status")
                    if status not in {"Blocked", "QA Review", "In Review"}:
                        continue
                    updated_at = ticket.get("updatedAt") or ticket.get("updated_at")
                    if not updated_at:
                        continue
                    try:
                        updated = datetime.fromisoformat(str(updated_at).replace("Z", "+00:00"))
                        if updated.tzinfo is None:
                            updated = updated.replace(tzinfo=timezone.utc)
                        age_hours = (current_time - updated).total_seconds() / 3600
                    except ValueError:
                        continue
                    if age_hours < (charter.oldest_review_hours if charter else 24):
                        continue
                    number = int(ticket["number"])
                    if status in {"QA Review", "In Review"}:
                        findings.append(_finding(
                            "review-wait",
                            f"Ticket #{number} has waited for human review",
                            f"The remote Ticket has remained {status} for {age_hours:.1f} hours.",
                        ))
                    else:
                        findings.append(_finding(
                            "stale-ticket",
                            f"Blocked Ticket #{number} needs triage",
                            f"The remote Ticket has remained Blocked for {age_hours:.1f} hours.",
                        ))
                refs = self.backend._git(
                    "ls-remote", "origin", "refs/heads/factory-claims/*",
                ).stdout.splitlines()
                for line in refs:
                    match = re.search(r"refs/heads/factory-claims/ticket-(\d+)$", line)
                    if not match:
                        continue
                    number = int(match.group(1))
                    claim = self.backend.read_claim(number)
                    if not claim:
                        continue
                    remote_claims.append(claim)
                    ticket = by_number.get(number)
                    reason = ""
                    if not ticket:
                        reason = "The claim has no corresponding GitHub Ticket."
                    elif ticket.get("status") == "Done" or ticket.get("state") == "CLOSED":
                        reason = "The Ticket is complete but its remote claim remains."
                    else:
                        claimed_at = claim.get("claimed_at")
                        if charter and claimed_at:
                            try:
                                claimed = datetime.fromisoformat(claimed_at.replace("Z", "+00:00"))
                                age_hours = (datetime.now(timezone.utc) - claimed).total_seconds() / 3600
                                if age_hours >= charter.oldest_review_hours:
                                    reason = (
                                        f"The claim is {age_hours:.1f} hours old; the Charter threshold "
                                        f"is {charter.oldest_review_hours} hours."
                                    )
                            except ValueError:
                                reason = "The claim does not contain a valid claim time."
                    if reason:
                        findings.append(_finding(
                            "stale-claim", f"Remote claim for Ticket #{number} needs review",
                            reason + " Release it only after confirming the owning run is abandoned.",
                        ))
            except Exception as exc:
                limitations.append(f"Remote claims and Tickets could not be reconciled: {str(exc)[:500]}")
            try:
                ci = self.backend.json(
                    "run", "list", "--repo", f"{self.backend.owner}/{self.backend.name}",
                    "--limit", "10", "--json", "databaseId,status,conclusion,workflowName,url,headSha",
                )
                failed = [run for run in ci if run.get("conclusion") == "failure"]
                if failed:
                    findings.append(_finding(
                        "default-branch-ci", "Default-branch CI has failures",
                        f"{len(failed)} of the latest {len(ci)} recorded runs failed.", severity="blocking",
                    ))
            except Exception as exc:
                limitations.append(f"CI status could not be read: {str(exc)[:500]}")
            try:
                advisories = self.backend.json(
                    "api", f"repos/{self.backend.owner}/{self.backend.name}/dependabot/alerts",
                    "-f", "state=open",
                )
                if advisories:
                    findings.append(_finding(
                        "dependency-advisory", "Open dependency advisories need triage",
                        f"GitHub reports {len(advisories)} open alert(s).",
                    ))
            except Exception as exc:
                limitations.append(f"Dependency advisories could not be read: {str(exc)[:500]}")

        after = self._git("status", "--porcelain")
        if after != before:
            raise RuntimeError("Monitor modified the repository; its result was discarded")
        revision = self._git("rev-parse", "HEAD").strip()
        counts = Counter(item["kind"] for item in findings)
        return {
            "schema_version": 1,
            "version": "factory-monitor:v1",
            "mode": "read-only",
            "status": "attention" if findings else "healthy",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "default_revision": revision,
            "charter_sha256": charter.policy_sha256() if charter else "",
            "findings": findings,
            "counts": dict(sorted(counts.items())),
            "hotspots": changed_hotspots,
            "ci": ci,
            "advisory_count": len(advisories),
            "remote_ticket_count": len(remote_tickets),
            "remote_claims": remote_claims,
            "limitations": limitations,
        }

    def publish(self, report: dict) -> list[dict]:
        """Explicitly create/update finding Tickets; never repair in this run."""
        if not self.backend:
            raise ValueError("Monitor publication requires a connected GitHub repository")
        existing = self.backend.json(
            "issue", "list", "--repo", f"{self.backend.owner}/{self.backend.name}",
            "--state", "all", "--limit", "200", "--json", "number,title,body,url",
        )
        published = []
        for finding in report.get("findings", []):
            marker = f"<!-- factory-monitor:v1 id={finding['id']} -->"
            body = (
                f"{marker}\n## {finding['summary']}\n\n{finding['detail']}\n\n"
                "Monitor is read-only. Resolve this in a separate reviewed Ticket."
            )
            current = next((issue for issue in existing if marker in issue.get("body", "")), None)
            if current:
                self.backend.gh(
                    "issue", "edit", current["number"], "--repo",
                    f"{self.backend.owner}/{self.backend.name}", "--body", body,
                )
                published.append({"id": finding["id"], "mode": "updated", "url": current.get("url", "")})
            else:
                result = self.backend.gh(
                    "issue", "create", "--repo", f"{self.backend.owner}/{self.backend.name}",
                    "--title", f"[Factory Monitor] {finding['summary']}", "--body", body,
                )
                published.append({"id": finding["id"], "mode": "created", "url": result.stdout.strip()})
        return published

    def _git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", *args], cwd=self.repo, text=True, capture_output=True,
        )
        return result.stdout if result.returncode == 0 else ""
