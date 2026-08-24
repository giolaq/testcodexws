"""One bounded view of every human decision that can pause Factory work."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def _waiting_since(ticket: dict) -> str:
    current = ticket.get("status")
    events = [
        event.get("at", "") for event in ticket.get("history", [])
        if event.get("status") == current and event.get("at")
    ]
    return events[-1] if events else ticket.get("finished_at") or ticket.get("started_at") or ""


def _planning_decision(planning: dict) -> tuple[dict | None, bool]:
    status = str(planning.get("status", ""))
    if status.startswith("awaiting_") and status.endswith("_approval"):
        label = {
            "awaiting_product_approval": "Product Review",
            "awaiting_alignment_approval": "Alignment Review",
            "awaiting_system_architecture_approval": "System Architecture Review",
            "awaiting_program_design_approval": "Program Design Review",
        }.get(status, "Planning Review")
        return ({
            "ticket": None,
            "plan_id": planning.get("plan_id", ""),
            "status": label,
            "waiting_since": planning.get("updated_at", ""),
            "history": [],
        }, False)
    blocked = next(
        (
            stage for stage in planning.get("stages", [])
            if stage.get("status") == "blocked" and stage.get("questions")
        ),
        None,
    )
    if blocked:
        return ({
            "ticket": None,
            "plan_id": planning.get("plan_id", ""),
            "status": f"{blocked.get('title', 'Planning')} questions",
            "waiting_since": planning.get("updated_at", ""),
            "history": [],
        }, True)
    return None, False


def human_attention_snapshot(
    repo: Path,
    tickets: list[dict],
    *,
    review_limit: int,
    blocked_limit: int,
    oldest_limit: int,
    planning: dict | None = None,
    current_time: datetime | None = None,
) -> dict:
    """Build the shared queue used by the scheduler and Control Center."""
    awaiting = [
        ticket for ticket in tickets
        if ticket.get("status") in {"QA Review", "In Review"}
    ]
    if planning is None:
        path = repo / ".factory/planning-state.json"
        if path.is_file():
            try:
                planning = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                planning = {}
        else:
            planning = {}
    planning_item, is_question = _planning_decision(planning)
    planning_items = [planning_item] if planning_item else []
    human_words = ("human", "decision", "clarif", "approval", "answer", "scope")
    blocked = [
        ticket for ticket in tickets
        if ticket.get("status") == "Blocked" and (
            ticket.get("blocking_questions")
            or any(word in ticket.get("failure", "").lower() for word in human_words)
        )
    ]

    decisions = []
    clock = current_time or datetime.now(timezone.utc)
    for item in awaiting + planning_items + blocked:
        since = item.get("waiting_since") or _waiting_since(item)
        age_hours = 0.0
        if since:
            try:
                parsed = datetime.fromisoformat(since.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                age_hours = max(0.0, (clock - parsed).total_seconds() / 3600)
            except ValueError:
                pass
        decisions.append({
            "ticket": item.get("number"),
            "plan_id": item.get("plan_id", ""),
            "status": item.get("status"),
            "waiting_since": since,
            "age_hours": round(age_hours, 2),
        })
    decisions.sort(key=lambda item: item["waiting_since"] or "9999")
    awaiting_human = len(awaiting) + len(planning_items)
    blocked_for_human = len(blocked) + int(is_question)
    reason = ""
    if awaiting_human >= review_limit:
        reason = f"human decision queue {awaiting_human} / limit {review_limit}"
    elif blocked_for_human >= blocked_limit:
        reason = f"human-blocked queue {blocked_for_human} / limit {blocked_limit}"
    elif decisions and decisions[0]["age_hours"] >= oldest_limit:
        reason = (
            f"oldest human decision has waited {decisions[0]['age_hours']:.1f}h "
            f"/ limit {oldest_limit}h"
        )
    return {
        "dispatch_paused": bool(reason),
        "reason": reason,
        "awaiting_review": len(awaiting),
        "planning_approvals": len(planning_items) - int(is_question),
        "planning_questions": int(is_question),
        "awaiting_human": awaiting_human,
        "review_limit": review_limit,
        "blocked_for_human": blocked_for_human,
        "blocked_limit": blocked_limit,
        "oldest_review_hours": oldest_limit,
        "oldest": decisions[0] if decisions else None,
        "decisions": decisions,
    }
