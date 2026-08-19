"""Versioned Factory Profiles, Agent Role contracts, policy, and handoffs."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


WORKSHOP_VERSION = "workshop-v1.0.0"
PROFILES = {
    "lean": {
        "name": "Lean",
        "purpose": "Low-risk changes that need clear intent, small slices, existing tests, and human review.",
        "planning_roles": ["product_review", "vertical_slices"],
        "execution_roles": ["implementation", "verification", "human_review"],
        "protected_acceptance_tests": False,
    },
    "standard": {
        "name": "Standard",
        "purpose": "The workshop path with aligned planning, independent Acceptance Tests, verification, and human merge.",
        "planning_roles": [
            "product_review",
            "system_architecture",
            "program_design",
            "vertical_slices",
        ],
        "execution_roles": ["qa", "implementation", "verification", "human_review"],
        "protected_acceptance_tests": True,
    },
    "assured": {
        "name": "Assured",
        "purpose": "Higher-risk work with cleanup, architecture conformance, hardening, and final independent verification.",
        "planning_roles": [
            "product_review",
            "system_architecture",
            "program_design",
            "vertical_slices",
        ],
        "execution_roles": [
            "qa",
            "implementation",
            "cleanup",
            "architecture_conformance",
            "hardening",
            "verification",
            "final_verifier",
            "human_review",
        ],
        "protected_acceptance_tests": True,
    },
}


def profile(name: str) -> dict:
    try:
        return PROFILES[name]
    except KeyError as exc:
        raise ValueError(f"unknown Factory Profile: {name}") from exc


def render_profiles(as_json: bool = False) -> str:
    if as_json:
        return json.dumps(PROFILES, indent=2, sort_keys=True)
    lines = [f"Factory Profiles · {WORKSHOP_VERSION}"]
    for value in PROFILES.values():
        lines += [
            "",
            f"{value['name']}: {value['purpose']}",
            f"  Planning: {', '.join(value['planning_roles'])}",
            f"  Execution: {', '.join(value['execution_roles'])}",
        ]
    return "\n".join(lines)


ROLE_SECTIONS = ("ownership", "exclusions", "verification", "handoff_receipt")
POLICY_SECTIONS = ("engineering", "workflow", "repository")


def _contract_file(repo: Path, name: str) -> Path:
    supplied = repo / "factory" / name
    return supplied if supplied.is_file() else Path(__file__).with_name(name)


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read factory contract {path}: {exc}") from exc


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def role_input(repo: Path, role: str) -> dict:
    roles = _read_json(_contract_file(repo, "roles.json"))
    contract = roles.get("roles", {}).get(role)
    if not isinstance(contract, dict):
        raise ValueError(f"Agent Role contract is not defined: {role}")
    for section in ROLE_SECTIONS:
        items = contract.get(section)
        if not isinstance(items, list) or not items or not all(isinstance(item, str) and item for item in items):
            raise ValueError(f"Agent Role {role} requires non-empty {section}")

    policy = _read_json(_contract_file(repo, "policy.json"))
    version = policy.get("version")
    if not isinstance(version, str) or not version:
        raise ValueError("factory policy requires a version")
    applicable = policy.get("role_applicability", {}).get(
        role,
        policy.get("role_applicability", {}).get("*", list(POLICY_SECTIONS)),
    )
    if not isinstance(applicable, list) or not set(applicable) <= set(POLICY_SECTIONS):
        raise ValueError(f"invalid policy applicability for Agent Role {role}")
    policy_values = {}
    policy_hashes = {}
    for section in applicable:
        items = policy.get(section)
        if not isinstance(items, list) or not items or not all(isinstance(item, str) and item for item in items):
            raise ValueError(f"factory policy requires non-empty {section} rules")
        content = "\n".join(items) + "\n"
        policy_values[section] = items
        policy_hashes[section] = _sha(content)

    titles = {
        "ownership": "Ownership",
        "exclusions": "Exclusions",
        "verification": "Verification responsibility",
        "handoff_receipt": "Handoff Receipt",
    }
    display_role = role.replace("_", " ").title()
    lines = [f"## Agent Role contract · {display_role}", ""]
    for section in ROLE_SECTIONS:
        lines += [f"### {titles[section]}", ""]
        lines += [f"- {item}" for item in contract[section]] + [""]
    lines += ["## Applicable project policy", "", f"Policy version: `{version}`", ""]
    for section in applicable:
        lines += [f"### {section.title()} policy · sha256: `{policy_hashes[section]}`", ""]
        lines += [f"- {item}" for item in policy_values[section]] + [""]
    return {
        "role": role,
        "contract_version": roles.get("schema_version", 1),
        "contract_sha256": _sha(json.dumps(contract, sort_keys=True, separators=(",", ":"))),
        "policy_version": version,
        "policy_hashes": policy_hashes,
        "text": "\n".join(lines),
    }


RECEIPT_FIELDS = {
    "schema_version",
    "run_id",
    "role",
    "phase",
    "ticket",
    "attempt",
    "input_revisions",
    "output_revisions",
    "claimed_result",
    "verification",
    "unresolved_risks",
    "artifacts",
    "policy_hashes",
    "timestamp",
}


def handoff_receipt(
    *,
    run_id: str,
    role: str,
    phase: str,
    ticket: int | None,
    attempt: int,
    input_revisions: dict[str, str],
    output_revisions: dict[str, str],
    claimed_result: str,
    verification: list[str],
    unresolved_risks: list[str],
    artifacts: list[str],
    policy_hashes: dict[str, str],
    timestamp: str | None = None,
) -> dict:
    receipt = {
        "schema_version": 1,
        "run_id": run_id,
        "role": role,
        "phase": phase,
        "ticket": ticket,
        "attempt": attempt,
        "input_revisions": input_revisions,
        "output_revisions": output_revisions,
        "claimed_result": claimed_result,
        "verification": verification,
        "unresolved_risks": unresolved_risks,
        "artifacts": artifacts,
        "policy_hashes": policy_hashes,
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    validate_handoff_receipt(receipt)
    return receipt


def validate_handoff_receipt(receipt: dict):
    if set(receipt) != RECEIPT_FIELDS:
        missing = RECEIPT_FIELDS - set(receipt)
        extra = set(receipt) - RECEIPT_FIELDS
        raise ValueError(f"invalid Handoff Receipt fields; missing={sorted(missing)}, extra={sorted(extra)}")
    for field in ("run_id", "role", "phase", "claimed_result", "timestamp"):
        if not isinstance(receipt[field], str) or not receipt[field]:
            raise ValueError(f"Handoff Receipt requires {field}")
    if receipt["ticket"] is not None and not isinstance(receipt["ticket"], int):
        raise ValueError("Handoff Receipt ticket must be an integer or null")
    if not isinstance(receipt["attempt"], int) or receipt["attempt"] < 1:
        raise ValueError("Handoff Receipt attempt must be positive")
    for field in ("input_revisions", "output_revisions", "policy_hashes"):
        value = receipt[field]
        if not isinstance(value, dict) or not all(
            isinstance(key, str) and isinstance(item, str) for key, item in value.items()
        ):
            raise ValueError(f"Handoff Receipt {field} must map strings to strings")
    for field in ("verification", "unresolved_risks", "artifacts"):
        value = receipt[field]
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ValueError(f"Handoff Receipt {field} must be a list of strings")


def write_handoff_receipt(repo: Path, receipt: dict) -> Path:
    validate_handoff_receipt(receipt)
    directory = repo / ".factory" / "receipts" / receipt["run_id"]
    directory.mkdir(parents=True, exist_ok=True)
    ticket = f"-ticket-{receipt['ticket']}" if receipt["ticket"] is not None else ""
    path = directory / (
        f"{receipt['phase'].lower()}-{receipt['role']}{ticket}"
        f"-attempt-{receipt['attempt']}-{uuid4().hex[:8]}.json"
    )
    path.write_text(json.dumps(receipt, indent=2) + "\n")
    return path
