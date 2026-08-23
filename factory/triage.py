"""Deterministic Ticket triage and risk-proportional control selection."""

from __future__ import annotations

import re
from pathlib import PurePosixPath


TRIAGE_RESULTS = {"READY_TO_IMPLEMENT", "READY_TO_PLAN", "NEEDS_INFORMATION", "WAIT"}
GATE_ORDER = {"fast": 0, "full": 1, "deep": 2}


def _matches(path: str, root: str) -> bool:
    return root == "." or path == root.rstrip("/") or path.startswith(root.rstrip("/") + "/")


def declared_paths(body: str) -> list[str]:
    match = re.search(r"(?ims)^## File ownership\s*\n(.+?)(?=^## |\Z)", body or "")
    if not match:
        return []
    paths = []
    for line in match.group(1).splitlines():
        value = re.sub(r"^\s*[-*]\s*", "", line).strip().strip("`")
        if not value:
            continue
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts:
            continue
        paths.append(path.as_posix())
    return sorted(dict.fromkeys(paths))


def classify_controls(charter, paths: list[str]) -> dict:
    load_bearing = any(
        _matches(path, root) for path in paths for root in charter.load_bearing_paths
    )
    human_approval = any(
        _matches(path, root) for path in paths for root in charter.requires_human_approval
    )
    tier_level = {"low": "fast", "shared": "full", "load-bearing": "deep"}[
        charter.consequence_tier
    ]
    selected = max(
        (charter.gate_level, tier_level, "deep" if load_bearing else "full" if human_approval else "fast"),
        key=GATE_ORDER.__getitem__,
    )
    risk = "load-bearing" if load_bearing else "elevated" if human_approval else charter.consequence_tier
    reason = (
        "Declared or changed paths intersect the Charter's load-bearing paths."
        if load_bearing else
        "Declared or changed paths require explicit human approval."
        if human_approval else
        f"The Charter consequence tier is {charter.consequence_tier}."
    )
    planning_approvals = list(charter.planning_approvals)
    if load_bearing:
        for stage in ("system_architecture", "program_design"):
            if stage not in planning_approvals:
                planning_approvals.insert(-1, stage)
    return {
        "risk": risk,
        "gate_level": selected,
        "load_bearing": load_bearing,
        "requires_human_approval": human_approval,
        "planning_approvals": planning_approvals,
        "paths": sorted(dict.fromkeys(paths)),
        "reason": reason,
    }


def triage_ticket(
    body: str,
    *,
    dependencies_ready: bool,
    planned: bool,
    profile: str,
    charter,
) -> dict:
    paths = declared_paths(body)
    controls = classify_controls(charter, paths)
    if profile == "assured":
        controls = {
            **controls,
            "gate_level": "deep",
            "reason": controls["reason"] + " The Assured profile requires deep verification.",
        }
    has_spec = bool(re.search(r"(?im)^## Spec\s*$", body or ""))
    criteria_section = re.search(
        r"(?ims)^## Acceptance criteria\s*\n(.+?)(?=^## |\Z)", body or "",
    )
    criteria = (
        re.findall(r"(?im)^\s*-\s*(?:\[[ x]\]\s*)?(.+)$", criteria_section.group(1))
        if criteria_section else []
    )
    if not has_spec or not criteria:
        result = "NEEDS_INFORMATION"
        reason = "Add a Spec and at least one observable Acceptance criterion."
    elif not dependencies_ready:
        result = "WAIT"
        reason = "A declared dependency is not Done."
    elif not planned and profile != "lean":
        result = "READY_TO_PLAN"
        reason = "This unplanned Ticket needs the selected profile's planning path."
    else:
        result = "READY_TO_IMPLEMENT"
        reason = "Intent is testable and dependencies are satisfied."
    return {
        "result": result,
        "reason": reason,
        "declared_paths": paths,
        "controls": controls,
    }
