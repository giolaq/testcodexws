"""Versioned, bounded, credential-safe remote Factory Run summaries."""

from __future__ import annotations

import json
import re

from sensitive_data import contains_credentials, redact_credentials


def factory_run_summary(state: dict, ticket: dict) -> dict:
    governance = state.get("governance", {})
    triage = ticket.get("triage", {})
    controls = triage.get("controls", {})
    review = ticket.get("code_review") or {}
    review_result = review.get("result") or {}
    qa = ticket.get("qa_evidence", {})
    claim = ticket.get("remote_claim") or {}
    metrics = ticket.get("metrics", {})
    recorded_evidence = ticket.get("evidence_packet")
    recorded_evidence = recorded_evidence if isinstance(recorded_evidence, dict) else {}
    evidence_available = (
        recorded_evidence.get("status") == "available"
        and recorded_evidence.get("path")
        and recorded_evidence.get("sha256")
    )
    unresolved_risks = []
    for value in [ticket.get("failure", ""), *ticket.get("warnings", [])]:
        sanitized = " ".join(redact_credentials(str(value)).split())[:240]
        if sanitized and sanitized not in unresolved_risks:
            unresolved_risks.append(sanitized)
    payload = {
        "schema_version": 1,
        "run_id": state.get("run_id", ""),
        "ticket": int(ticket["number"]),
        "status": ticket.get("status", "unknown"),
        "plan_id": ticket.get("plan_id", ""),
        "profile": state.get("profile", governance.get("profile", "")),
        "governance": {
            "charter_sha256": governance.get("charter_sha256", ""),
            "merge_authority": governance.get("merge_authority", ""),
            "policy_hashes": state.get("policy", {}).get("hashes", {}),
        },
        "adapters": {
            "qa": ticket.get("qa_agent", ""),
            "implementation": ticket.get("agent", ""),
            "review": ticket.get("review_agent", ""),
            "supervisor": state.get("supervisor_agent", ""),
        },
        "input_hashes": {
            "charter": governance.get("charter_sha256", ""),
            **{
                f"policy_{name}": value
                for name, value in state.get("policy", {}).get("hashes", {}).items()
            },
            "base_revision": ticket.get("base_sha", ""),
            "acceptance_tests_revision": ticket.get("qa_commit", ""),
        },
        "revisions": {
            "base": ticket.get("base_sha", ""),
            "qa": ticket.get("qa_commit", ""),
            "approved_head": ticket.get("approved_head", ""),
        },
        "claim": {
            "owner_run_id": claim.get("owner_run_id") or claim.get("run_id", ""),
            "base_revision": claim.get("base_revision", ""),
            "claimed_at": claim.get("claimed_at", ""),
            "claim_sha": claim.get("claim_sha", ""),
            "ref": claim.get("ref", ""),
        },
        "triage": {
            "result": triage.get("result", ""),
            "risk": controls.get("risk", ""),
            "gate_level": ticket.get("verification_level") or controls.get("gate_level", ""),
        },
        "verdicts": {
            "red": qa.get("red", {}).get("result", ""),
            "green": qa.get("green", {}).get("result", ""),
            "negative": qa.get("negative", {}).get("result", ""),
            "code_review": review_result.get("decision", ""),
            "supervisor_merge": ticket.get("supervisor_merge_action", ""),
        },
        "gates": [
            {
                "name": redact_credentials(str(gate.get("name", "unnamed"))),
                "level": gate.get("level", "full"),
                "required": bool(gate.get("required", True)),
                "classification": gate.get("classification") or (
                    "PASS" if gate.get("exit_code") == 0 else "FAIL"
                ),
                "exit_code": gate.get("exit_code"),
                "duration_seconds": gate.get("duration_seconds", 0),
            }
            for gate in ticket.get("gate_results", [])
        ],
        "metrics": {
            "attempts": ticket.get("attempt", 0),
            "qa_attempts": ticket.get("qa_attempt", 0),
            "verification_seconds": ticket.get("verification_duration_seconds", 0),
            "stage_seconds": metrics.get("stage_seconds", {}),
            "agent_seconds": metrics.get("agent_seconds", 0),
            "gate_seconds": metrics.get("gate_seconds", 0),
            "human_wait_seconds": metrics.get("human_wait_seconds", 0),
            "retry_count": metrics.get("retry_count", 0),
            "verifier_rejections": metrics.get("verifier_rejections", 0),
            "peak_review_queue": state.get("metrics", {}).get("peak_review_queue", 0),
        },
        "human_decisions": {
            "qa_approved": bool(ticket.get("qa_approved")),
            "merge_executed_by": ticket.get("merge_executed_by", ""),
            "policy_required_human_merge": bool(ticket.get("policy_required_human_merge")),
            "effective_merge_authority": ticket.get(
                "merge_authority", governance.get("merge_authority", ""),
            ),
        },
        "unresolved_risks": unresolved_risks,
        "unresolved_risk_count": len(unresolved_risks),
        "evidence_packet": {
            "status": "available" if evidence_available else "pending",
            "path": str(recorded_evidence.get("path", "")) if evidence_available else "",
            "manifest": str(recorded_evidence.get("manifest", "")) if evidence_available else "",
            "sha256": str(recorded_evidence.get("sha256", "")) if evidence_available else "",
        },
    }
    encoded = json.dumps(payload, sort_keys=True)
    if contains_credentials(encoded):
        raise ValueError("sanitized Factory Run summary contains credential-like data")
    return payload


def render_factory_run_summary(payload: dict) -> str:
    marker = (
        f"<!-- factory-run:v1 ticket={payload['ticket']} run={payload['run_id']} -->"
    )
    return marker + "\n`factory-run:v1`\n\n```json\n" + json.dumps(
        payload, indent=2, sort_keys=True,
    ) + "\n```"


def parse_factory_run_summary(body: str, *, ticket: int) -> dict | None:
    """Return one validated ``factory-run:v1`` payload from a GitHub comment."""
    if not isinstance(body, str) or len(body) > 128_000 or contains_credentials(body):
        return None
    marker = re.search(
        r"<!-- factory-run:v1 ticket=(\d+) run=([A-Za-z0-9_-]{1,64}) -->",
        body,
    )
    block = re.search(r"```json\s*(\{.*?\})\s*```", body, re.DOTALL)
    if not marker or not block or int(marker.group(1)) != int(ticket):
        return None
    try:
        payload = json.loads(block.group(1))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    if (
        payload.get("schema_version") != 1
        or payload.get("ticket") != int(ticket)
        or payload.get("run_id") != marker.group(2)
    ):
        return None
    return payload
