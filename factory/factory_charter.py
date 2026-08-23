"""Human-owned Factory Charter with hash-bound approval.

The public interface is deliberately small: create a conservative draft, load
and validate the repository Charter, approve its exact policy, classify paths,
and render the governed controls for a run. Callers do not parse Charter TOML or
reimplement approval semantics.
"""

from __future__ import annotations

import hashlib
import json
import re
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath

from project_contract import ProjectContract


CHARTER_PATH = Path("factory.charter.toml")
CONSEQUENCE_TIERS = {"low", "shared", "load-bearing"}
MERGE_AUTHORITIES = {"human", "supervisor"}
EXISTING_TEST_POLICIES = {"protect", "review", "allow"}
PLANNING_APPROVALS = {
    "product_review", "system_architecture", "program_design", "alignment",
}
GATE_LEVELS = {"fast", "full", "deep"}


class FactoryCharterError(ValueError):
    pass


def _path(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FactoryCharterError(f"{label} must contain non-empty repository paths")
    raw = value.strip()
    parsed = PurePosixPath(raw)
    if "\\" in raw or parsed.is_absolute() or ".." in parsed.parts:
        raise FactoryCharterError(f"{label} must stay inside the repository: {value}")
    return parsed.as_posix()


def _strings(value, label: str, *, allow_empty=False) -> tuple[str, ...]:
    if not isinstance(value, list) or (not value and not allow_empty):
        qualifier = "possibly empty" if allow_empty else "non-empty"
        raise FactoryCharterError(f"{label} must be a {qualifier} list")
    if not all(isinstance(item, str) and item.strip() for item in value):
        raise FactoryCharterError(f"{label} must contain non-empty strings")
    return tuple(item.strip() for item in value)


def _positive_int(value, label: str, *, allow_zero=False) -> int:
    minimum = 0 if allow_zero else 1
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise FactoryCharterError(f"{label} must be an integer >= {minimum}")
    return value


def _matches(path: str, configured: str) -> bool:
    if configured == ".":
        return True
    return path == configured or path.startswith(configured.rstrip("/") + "/")


@dataclass(frozen=True)
class FactoryCharter:
    repo: Path
    schema_version: int
    consequence_tier: str
    merge_authority: str
    existing_tests: str
    planning_approvals: tuple[str, ...]
    gate_level: str
    max_retries: int
    max_diff_lines: int
    max_awaiting_human_review: int
    max_blocked_for_human: int
    oldest_review_hours: int
    load_bearing_paths: tuple[str, ...]
    editable_paths: tuple[str, ...]
    never_modify: tuple[str, ...]
    requires_human_approval: tuple[str, ...]
    stop_conditions: tuple[str, ...]
    approved: bool = False
    approved_policy_sha256: str = ""
    path: Path | None = None

    @classmethod
    def draft(cls, repo: Path, project: ProjectContract) -> "FactoryCharter":
        repo = repo.resolve()
        load_bearing = tuple(dict.fromkeys((
            CHARTER_PATH.as_posix(),
            "factory.project.toml",
            ".github/workflows",
            "migrations",
            "auth",
            "security",
            *project.protected_paths,
        )))
        review_required = tuple(dict.fromkeys((
            "factory.project.toml",
            "AGENTS.md",
            "CLAUDE.md",
            ".agents",
            ".codex",
            ".github/workflows",
            "migrations",
            "auth",
            "security",
            *project.test_roots,
            *project.protected_paths,
        )))
        return cls(
            repo=repo,
            schema_version=1,
            consequence_tier="shared",
            merge_authority="human",
            existing_tests="review",
            planning_approvals=("product_review", "alignment"),
            gate_level="full",
            max_retries=2,
            max_diff_lines=800,
            max_awaiting_human_review=3,
            max_blocked_for_human=2,
            oldest_review_hours=24,
            load_bearing_paths=load_bearing,
            editable_paths=tuple(dict.fromkeys(project.source_roots)),
            never_modify=(CHARTER_PATH.as_posix(), ".env", ".secrets"),
            requires_human_approval=review_required,
            stop_conditions=(
                "A required gate is missing, skipped, or fails.",
                "A proposed change touches a never-modify path.",
                "The human review queue reaches its configured capacity.",
                "The requested work exceeds the approved Ticket or diff budget.",
                "The Charter is silent about a load-bearing change.",
            ),
            path=repo / CHARTER_PATH,
        )

    @classmethod
    def load(cls, repo: Path, *, require_approved=False) -> "FactoryCharter":
        repo = repo.resolve()
        path = repo / CHARTER_PATH
        if not path.is_file():
            raise FactoryCharterError(
                f"Factory Charter not found at {path}. Run `factory init --repo {repo}`."
            )
        try:
            value = tomllib.loads(path.read_text())
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise FactoryCharterError(f"cannot read Factory Charter at {path}: {exc}") from exc
        charter = cls._from_dict(repo, path, value)
        if require_approved:
            charter.assert_approved()
        return charter

    @classmethod
    def _from_dict(cls, repo: Path, path: Path, value: dict) -> "FactoryCharter":
        if value.get("schema_version") != 1:
            raise FactoryCharterError("Factory Charter schema_version must be 1")
        policy = value.get("policy")
        limits = value.get("limits")
        paths = value.get("paths")
        if not all(isinstance(section, dict) for section in (policy, limits, paths)):
            raise FactoryCharterError("Factory Charter requires policy, limits, and paths tables")

        tier = policy.get("consequence_tier")
        merge = policy.get("merge_authority")
        tests = policy.get("existing_tests")
        gate = policy.get("gate_level")
        if tier not in CONSEQUENCE_TIERS:
            raise FactoryCharterError("policy.consequence_tier must be low, shared, or load-bearing")
        if merge not in MERGE_AUTHORITIES:
            raise FactoryCharterError("policy.merge_authority must be human or supervisor")
        if tests not in EXISTING_TEST_POLICIES:
            raise FactoryCharterError("policy.existing_tests must be protect, review, or allow")
        if gate not in GATE_LEVELS:
            raise FactoryCharterError("policy.gate_level must be fast, full, or deep")
        approvals = _strings(policy.get("planning_approvals"), "policy.planning_approvals")
        unknown_approvals = set(approvals) - PLANNING_APPROVALS
        if unknown_approvals:
            raise FactoryCharterError(
                "policy.planning_approvals contains unknown gates: "
                + ", ".join(sorted(unknown_approvals))
            )
        stop_conditions = _strings(policy.get("stop_conditions"), "policy.stop_conditions")
        if paths.get("editable") is None:
            raise FactoryCharterError(
                "Factory Charter predates paths.editable; add the repository's "
                "agent-editable roots, then review and reapprove the Charter"
            )

        approved = value.get("approved", False)
        approved_hash = value.get("approved_policy_sha256", "")
        if not isinstance(approved, bool):
            raise FactoryCharterError("approved must be true or false")
        if not isinstance(approved_hash, str) or (
            approved_hash and not re.fullmatch(r"[a-f0-9]{64}", approved_hash)
        ):
            raise FactoryCharterError("approved_policy_sha256 must be empty or a sha256 hash")

        charter = cls(
            repo=repo,
            schema_version=1,
            consequence_tier=tier,
            merge_authority=merge,
            existing_tests=tests,
            planning_approvals=approvals,
            gate_level=gate,
            max_retries=_positive_int(limits.get("max_retries"), "limits.max_retries", allow_zero=True),
            max_diff_lines=_positive_int(limits.get("max_diff_lines"), "limits.max_diff_lines"),
            max_awaiting_human_review=_positive_int(
                limits.get("max_awaiting_human_review"),
                "limits.max_awaiting_human_review",
            ),
            max_blocked_for_human=_positive_int(
                limits.get("max_blocked_for_human"),
                "limits.max_blocked_for_human",
            ),
            oldest_review_hours=_positive_int(
                limits.get("oldest_review_hours"), "limits.oldest_review_hours",
            ),
            load_bearing_paths=tuple(
                _path(item, "paths.load_bearing")
                for item in _strings(paths.get("load_bearing"), "paths.load_bearing")
            ),
            editable_paths=tuple(
                _path(item, "paths.editable")
                for item in _strings(paths.get("editable"), "paths.editable")
            ),
            never_modify=tuple(
                _path(item, "paths.never_modify")
                for item in _strings(paths.get("never_modify"), "paths.never_modify")
            ),
            requires_human_approval=tuple(
                _path(item, "paths.requires_human_approval")
                for item in _strings(
                    paths.get("requires_human_approval"),
                    "paths.requires_human_approval",
                )
            ),
            stop_conditions=stop_conditions,
            approved=approved,
            approved_policy_sha256=approved_hash,
            path=path,
        )
        if CHARTER_PATH.as_posix() not in charter.never_modify:
            raise FactoryCharterError("paths.never_modify must include factory.charter.toml")
        return charter

    def policy_payload(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "policy": {
                "consequence_tier": self.consequence_tier,
                "merge_authority": self.merge_authority,
                "existing_tests": self.existing_tests,
                "planning_approvals": list(self.planning_approvals),
                "gate_level": self.gate_level,
                "stop_conditions": list(self.stop_conditions),
            },
            "limits": {
                "max_retries": self.max_retries,
                "max_diff_lines": self.max_diff_lines,
                "max_awaiting_human_review": self.max_awaiting_human_review,
                "max_blocked_for_human": self.max_blocked_for_human,
                "oldest_review_hours": self.oldest_review_hours,
            },
            "paths": {
                "load_bearing": list(self.load_bearing_paths),
                "editable": list(self.editable_paths),
                "never_modify": list(self.never_modify),
                "requires_human_approval": list(self.requires_human_approval),
            },
        }

    def policy_sha256(self) -> str:
        encoded = json.dumps(self.policy_payload(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode()).hexdigest()

    def assert_approved(self) -> None:
        if not self.approved or not self.approved_policy_sha256:
            raise FactoryCharterError(
                "Factory Charter is not approved. Review it, then run `factory approve-charter --yes`."
            )
        if self.approved_policy_sha256 != self.policy_sha256():
            raise FactoryCharterError(
                "Factory Charter changed after approval. Review it, then run `factory approve-charter --yes` again."
            )

    def approve(self) -> "FactoryCharter":
        approved = replace(
            self,
            approved=True,
            approved_policy_sha256=self.policy_sha256(),
        )
        approved.write(force=True)
        return approved

    def write(self, *, force=False) -> Path:
        path = self.repo / CHARTER_PATH
        if path.exists() and not force:
            raise FactoryCharterError(f"Factory Charter already exists: {path}")

        def values(items: tuple[str, ...]) -> str:
            return "[" + ", ".join(json.dumps(item) for item in items) + "]"

        lines = [
            "# Human-owned policy for the Software (re)-Factory.",
            "# Agents may read this file but must never modify it.",
            f"schema_version = {self.schema_version}",
            f"approved = {str(self.approved).lower()}",
            f"approved_policy_sha256 = {json.dumps(self.approved_policy_sha256)}",
            "",
            "[policy]",
            f"consequence_tier = {json.dumps(self.consequence_tier)}",
            f"merge_authority = {json.dumps(self.merge_authority)}",
            f"existing_tests = {json.dumps(self.existing_tests)}",
            f"planning_approvals = {values(self.planning_approvals)}",
            f"gate_level = {json.dumps(self.gate_level)}",
            f"stop_conditions = {values(self.stop_conditions)}",
            "",
            "[limits]",
            f"max_retries = {self.max_retries}",
            f"max_diff_lines = {self.max_diff_lines}",
            f"max_awaiting_human_review = {self.max_awaiting_human_review}",
            f"max_blocked_for_human = {self.max_blocked_for_human}",
            f"oldest_review_hours = {self.oldest_review_hours}",
            "",
            "[paths]",
            f"load_bearing = {values(self.load_bearing_paths)}",
            f"editable = {values(self.editable_paths)}",
            f"never_modify = {values(self.never_modify)}",
            f"requires_human_approval = {values(self.requires_human_approval)}",
        ]
        path.write_text("\n".join(lines) + "\n")
        return path

    def path_policy(self, path: str) -> str:
        normalized = _path(path, "changed path")
        if any(_matches(normalized, configured) for configured in self.never_modify):
            return "never_modify"
        if any(
            _matches(normalized, configured)
            for configured in self.requires_human_approval
        ):
            return "requires_human_approval"
        if any(_matches(normalized, configured) for configured in self.editable_paths):
            return "editable"
        return "outside_editable"

    def context(self) -> str:
        return json.dumps({
            **self.policy_payload(),
            "approved": self.approved,
            "policy_sha256": self.policy_sha256(),
        }, indent=2)

    def governance(self, profile_name: str, *, explicit_autonomy=False) -> dict:
        """Return the immutable controls a planning or Factory Run records."""
        from factory_contracts import profile as factory_profile

        selected = factory_profile(profile_name)
        expected_authority = selected["merge_authority"]
        if self.merge_authority != expected_authority:
            raise FactoryCharterError(
                f"Factory Profile {selected['name']} requires {expected_authority} merge authority, "
                f"but the approved Charter requires {self.merge_authority}."
            )
        if selected.get("requires_explicit_opt_in") and not explicit_autonomy:
            raise FactoryCharterError(
                "Autonomous Demo delegates final merge accountability. Retry only with the explicit autonomous-merge opt-in."
            )
        self.assert_approved()
        return {
            "schema_version": 1,
            "profile": profile_name,
            "charter_path": CHARTER_PATH.as_posix(),
            "charter_sha256": self.policy_sha256(),
            "merge_authority": self.merge_authority,
            "consequence_tier": self.consequence_tier,
            "gate_level": self.gate_level,
            "planning_approvals": list(self.planning_approvals),
            "limits": {
                "max_retries": self.max_retries,
                "max_diff_lines": self.max_diff_lines,
                "max_awaiting_human_review": self.max_awaiting_human_review,
                "max_blocked_for_human": self.max_blocked_for_human,
                "oldest_review_hours": self.oldest_review_hours,
            },
            "path_policy": {
                "load_bearing": list(self.load_bearing_paths),
                "editable": list(self.editable_paths),
                "never_modify": list(self.never_modify),
                "requires_human_approval": list(self.requires_human_approval),
                "existing_tests": self.existing_tests,
            },
            "explicit_autonomy": bool(explicit_autonomy),
        }
