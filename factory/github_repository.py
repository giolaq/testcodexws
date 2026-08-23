"""Validate and connect the local checkout to one explicit GitHub repository."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


OWNER = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})"
NAME = r"[A-Za-z0-9._-]{1,100}"
SLUG = re.compile(rf"(?P<owner>{OWNER})/(?P<name>{NAME})")
HTTPS = re.compile(rf"https://github\.com/(?P<slug>{OWNER}/{NAME})(?:/)?")
SSH = re.compile(rf"git@github\.com:(?P<slug>{OWNER}/{NAME})")
SSH_URL = re.compile(rf"ssh://git@github\.com/(?P<slug>{OWNER}/{NAME})(?:/)?")


class GitHubRepositoryError(ValueError):
    """A repository URL is invalid or cannot be connected safely."""


@dataclass(frozen=True)
class GitHubRepository:
    slug: str
    url: str
    remote_url: str


def parse_github_repository(raw: str) -> GitHubRepository:
    """Return a canonical repository identity from a GitHub URL or owner/name."""
    if not isinstance(raw, str) or not raw.strip():
        raise GitHubRepositoryError("GitHub repository URL is required.")
    value = raw.strip()
    ssh = value.startswith("git@") or value.startswith("ssh://")
    candidate = value[:-4] if value.endswith(".git") else value
    match = HTTPS.fullmatch(candidate) or SSH.fullmatch(candidate) or SSH_URL.fullmatch(candidate)
    if match:
        slug = match.group("slug")
    elif SLUG.fullmatch(candidate):
        slug = candidate
        ssh = False
    else:
        raise GitHubRepositoryError(
            "Use a GitHub repository URL such as https://github.com/OWNER/REPOSITORY."
        )
    owner, name = slug.split("/", 1)
    if ".." in name or name in {".", ".."}:
        raise GitHubRepositoryError("GitHub repository name is invalid.")
    canonical_slug = f"{owner}/{name}"
    return GitHubRepository(
        slug=canonical_slug,
        url=f"https://github.com/{canonical_slug}",
        remote_url=(
            f"git@github.com:{canonical_slug}.git"
            if ssh else f"https://github.com/{canonical_slug}.git"
        ),
    )


def repository_from_remote(remote: str) -> GitHubRepository | None:
    try:
        return parse_github_repository(remote)
    except GitHubRepositoryError:
        return None


def _run(command: list[str], repo: Path, *, runner=None):
    invoke = runner or subprocess.run
    return invoke(command, cwd=repo, text=True, capture_output=True)


def _accessible_repository(repo: Path, raw: str, *, runner=None) -> tuple[GitHubRepository, GitHubRepository]:
    requested = parse_github_repository(raw)
    if not shutil.which("gh"):
        raise GitHubRepositoryError("GitHub CLI not found. Install `gh`, then run `gh auth login`.")
    auth = _run(["gh", "auth", "status"], repo, runner=runner)
    if auth.returncode:
        raise GitHubRepositoryError("GitHub CLI is not authenticated. Run `gh auth login`.")
    viewed = _run(
        ["gh", "repo", "view", requested.slug, "--json", "nameWithOwner"],
        repo,
        runner=runner,
    )
    if viewed.returncode:
        raise GitHubRepositoryError(
            viewed.stderr.strip() or viewed.stdout.strip() or "GitHub repository is not accessible."
        )
    try:
        canonical = parse_github_repository(json.loads(viewed.stdout)["nameWithOwner"])
    except (KeyError, json.JSONDecodeError) as exc:
        raise GitHubRepositoryError("GitHub returned an invalid repository identity.") from exc
    return requested, canonical


def managed_checkout_path(workspace_root: Path, repository: GitHubRepository) -> Path:
    """Return a traversal-safe checkout path owned by the local Control Center."""
    root = workspace_root.resolve()
    owner, name = repository.slug.split("/", 1)
    target = (root / owner.lower() / name.lower()).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:  # Defensive: repository parsing already rejects traversal.
        raise GitHubRepositoryError("Managed repository path escaped its workspace root.") from exc
    return target


def checkout_github_repository(
    workspace_root: Path,
    raw: str,
    *,
    runner=None,
) -> dict:
    """Clone or reuse one explicit GitHub repository in an isolated workspace."""
    workspace_root = workspace_root.resolve()
    workspace_root.mkdir(parents=True, exist_ok=True)
    _, canonical = _accessible_repository(workspace_root, raw, runner=runner)
    target = managed_checkout_path(workspace_root, canonical)
    if target.exists():
        if not (target / ".git").exists():
            raise GitHubRepositoryError(
                f"Managed checkout path exists but is not a Git repository: {target}"
            )
        current = _run(["git", "remote", "get-url", "origin"], target, runner=runner)
        connected = repository_from_remote(current.stdout.strip()) if current.returncode == 0 else None
        if not connected or connected.slug.lower() != canonical.slug.lower():
            raise GitHubRepositoryError(
                f"Managed checkout has an unexpected origin: {target}. Remove or rename it, then retry."
            )
        action = "reused"
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        cloned = _run(["gh", "repo", "clone", canonical.slug, str(target)], workspace_root, runner=runner)
        if cloned.returncode:
            raise GitHubRepositoryError(
                cloned.stderr.strip() or cloned.stdout.strip() or "Could not clone the GitHub repository."
            )
        if not (target / ".git").exists():
            raise GitHubRepositoryError("GitHub clone completed without creating a Git checkout.")
        action = "cloned"
    return {
        "slug": canonical.slug,
        "url": canonical.url,
        "path": str(target),
        "action": action,
    }


def connect_github_repository(repo: Path, raw: str, *, runner=None) -> dict:
    """Verify that a local checkout belongs to the explicitly selected repository.

    The URL is an explicit operator choice. Existing SSH/HTTPS transport is
    preserved when ``origin`` already names the same repository. A different
    origin is rejected: changing it would make the factory operate on source
    from one repository while writing issues and pull requests to another.
    """
    repo = repo.resolve()
    requested, canonical = _accessible_repository(repo, raw, runner=runner)

    remote_url = (
        f"git@github.com:{canonical.slug}.git"
        if requested.remote_url.startswith("git@")
        else f"https://github.com/{canonical.slug}.git"
    )
    current = _run(["git", "remote", "get-url", "origin"], repo, runner=runner)
    current_repository = repository_from_remote(current.stdout.strip()) if current.returncode == 0 else None
    if current.returncode != 0:
        changed = _run(
            ["git", "remote", "add", "origin", remote_url], repo, runner=runner,
        )
        action = "added"
    elif not current_repository or current_repository.slug.lower() != canonical.slug.lower():
        current_label = current_repository.url if current_repository else current.stdout.strip()
        raise GitHubRepositoryError(
            "This checkout belongs to a different GitHub repository "
            f"({current_label or 'unknown'}). Open the Control Center for {canonical.url} "
            "in a separate checkout; origin was not changed."
        )
    else:
        changed = None
        action = "unchanged"
    if changed is not None and changed.returncode:
        raise GitHubRepositoryError(changed.stderr.strip() or "Could not configure the origin remote.")
    return {"slug": canonical.slug, "url": canonical.url, "origin": action}
