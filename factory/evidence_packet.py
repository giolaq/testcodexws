"""Sanitized, portable evidence export for a completed Planning Run."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from factory_contracts import WORKSHOP_VERSION
from planning_pipeline import STAGES, load_manifest, resolve_run
from sensitive_data import redact_credentials


CANVAS_SECTIONS = (
    "Use case",
    "Factory Profile",
    "Consequence tier",
    "Merge authority",
    "Review capacity",
    "Load-bearing paths",
    "Gate budget",
    "Durable remote record",
    "Monitoring owner",
    "Agent Roles",
    "Human Gates",
    "Execution environment",
    "Required evidence",
    "Recovery policy",
    "First Vertical Slice",
    "Peer review",
)
def sha_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _canvas_sections(text: str) -> dict[str, str]:
    matches = list(re.finditer(r"(?m)^##\s+(.+?)\s*$", text))
    sections = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections[match.group(1).strip()] = text[match.end():end].strip()
    return sections


def validate_canvas(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"Factory Canvas not found: {path}")
    text = path.read_text()
    sections = _canvas_sections(text)
    missing = [name for name in CANVAS_SECTIONS if not sections.get(name)]
    placeholders = []
    for name in CANVAS_SECTIONS:
        value = sections.get(name, "").strip()
        if (
            value.casefold() in {"todo", "tbd", "...", "[complete this section]"}
            or (value.startswith("[") and value.endswith("]"))
        ):
            placeholders.append(name)
    if missing or placeholders:
        problems = []
        if missing:
            problems.append("missing: " + ", ".join(missing))
        if placeholders:
            problems.append("incomplete: " + ", ".join(placeholders))
        raise ValueError("Factory Canvas is incomplete; " + "; ".join(problems))
    return text


def create_canvas(repo: Path, output: Path, force: bool = False) -> Path:
    output = output if output.is_absolute() else repo / output
    if output.exists() and not force:
        raise ValueError(f"Factory Canvas already exists: {output}")
    template = repo / "factory/FACTORY_CANVAS.md"
    if not template.is_file():
        template = Path(__file__).with_name("FACTORY_CANVAS.md")
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(template, output)
    return output


def _load_state(repo: Path) -> dict:
    path = repo / ".factory/state.json"
    if not path.is_file():
        return {"tickets": []}
    return json.loads(path.read_text())


def _receipt_references(manifest: dict, tickets: list[dict]) -> list[str]:
    values = list(manifest.get("receipts", []))
    for ticket in tickets:
        values.extend(ticket.get("receipts", []))
    return list(dict.fromkeys(value for value in values if value))


def export_evidence(
    repo: Path,
    identifier: str,
    canvas_path: Path,
    ticket_numbers: list[int] | None = None,
    output: Path | None = None,
) -> tuple[Path, Path]:
    run_dir = resolve_run(repo, identifier)
    manifest = load_manifest(run_dir)
    governance = manifest.get("governance")
    if not isinstance(governance, dict):
        raise ValueError(
            "Planning Run predates governed evidence. Re-run planning with an approved "
            "Factory Charter before exporting an Evidence Packet."
        )
    required_governance = {
        "schema_version", "profile", "charter_sha256", "merge_authority",
    }
    missing_governance = sorted(required_governance - set(governance))
    if missing_governance:
        raise ValueError(
            "Planning Run governance is incomplete: " + ", ".join(missing_governance)
        )
    if governance.get("profile") != manifest.get("profile", "standard"):
        raise ValueError(
            "Planning Run profile does not match its recorded Factory Charter governance."
        )
    canvas_path = canvas_path if canvas_path.is_absolute() else repo / canvas_path
    canvas_text = validate_canvas(canvas_path)
    state = _load_state(repo)
    all_tickets = state.get("tickets", [])
    plan_tickets = [ticket for ticket in all_tickets if ticket.get("plan_id") == manifest["plan_id"]]
    selected_numbers = ticket_numbers or [ticket["number"] for ticket in plan_tickets]
    selected = [ticket for ticket in plan_tickets if ticket.get("number") in selected_numbers]
    unknown = sorted(set(selected_numbers) - {ticket.get("number") for ticket in selected})
    if unknown:
        raise ValueError("Ticket evidence not found: " + ", ".join(f"#{number}" for number in unknown))
    if selected:
        execution_governance = state.get("governance")
        if not isinstance(execution_governance, dict):
            raise ValueError(
                "Execution state predates governed evidence. Re-run the selected Tickets "
                "under the approved planning Charter."
            )
        governed_fields = (
            "schema_version", "profile", "charter_sha256", "merge_authority",
        )
        drift = [
            field for field in governed_fields
            if execution_governance.get(field) != governance.get(field)
        ]
        if drift:
            raise ValueError(
                "execution governance does not match planning: " + ", ".join(drift)
            )

    output_dir = output or repo / ".factory/evidence" / manifest["plan_id"]
    output_dir = output_dir if output_dir.is_absolute() else repo / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    missing = []
    artifacts = []
    lines = [
        f"# Evidence Packet — {manifest.get('project', 'Planning Run')}",
        "",
        f"Workshop version: `{WORKSHOP_VERSION}`  ",
        f"Planning Run: `{manifest['plan_id']}`  ",
        f"Factory Profile: **{manifest.get('profile', 'standard').title()}**  ",
        f"Policy version: `{manifest.get('policy', {}).get('version', 'not recorded')}`  ",
        f"Factory Charter version: `{governance['schema_version']}`  ",
        f"Factory Charter hash: `{governance['charter_sha256']}`  ",
        f"Merge authority: **{str(governance['merge_authority']).title()}**",
        "",
        "## Planning artifacts",
        "",
    ]
    for stage, filename, title in STAGES:
        record = manifest.get("stages", {}).get(stage, {})
        if record.get("status") == "not_applicable":
            lines += [f"### {title}", "", "Not applicable to this Factory Profile.", ""]
            continue
        path = run_dir / f"{filename}.md"
        if not path.is_file():
            missing.append(f"{title} artifact is missing")
            continue
        content = redact_credentials(path.read_text()).strip()
        lines += [f"### {title}", "", content, ""]
        artifacts.append({"kind": stage, "path": str(path.relative_to(repo)), "sha256": sha_text(path.read_text())})

    lines += ["## Approval history", ""]
    history = manifest.get("approval_history", [])
    if history:
        for event in history:
            gate = str(event.get("gate", "unknown")).replace("_", " ").title()
            decision = str(event.get("decision", "not recorded")).replace("_", " ")
            line = f"- {event.get('at', 'time not recorded')} · {gate}: {decision}"
            if event.get("feedback"):
                line += f" — {event['feedback']}"
            lines.append(line)
    else:
        for gate in ("product", "alignment"):
            approval = manifest.get("approvals", {}).get(gate)
            if approval:
                lines.append(f"- {gate.title()}: approved at {approval.get('approved_at', 'time not recorded')}")
            else:
                missing.append(f"{gate.title()} approval is missing")
                lines.append(f"- {gate.title()}: not approved")
    lines += ["", "### Revision records", ""]
    revisions = manifest.get("revisions", [])
    if revisions:
        for revision in revisions:
            lines += [
                f"- Revision {revision.get('revision', '?')} · {str(revision.get('stage', 'unknown')).replace('_', ' ')}",
                f"  - Feedback: {revision.get('feedback', 'not recorded')}",
                f"  - Before: `{revision.get('before_sha256', 'not recorded')}`",
                f"  - After: `{revision.get('after_sha256', 'not recorded')}`",
            ]
    else:
        lines.append("- No revisions were requested.")

    traceability_path = run_dir / "traceability.json"
    lines += ["", "## Requirement and dependency trace", ""]
    if traceability_path.is_file():
        traceability = json.loads(traceability_path.read_text())
        lines += ["| Requirement | Slices | Evidence |", "| --- | --- | --- |"]
        for row in traceability.get("rows", []):
            lines.append(
                f"| {row.get('requirement_id', '—')} | {', '.join(row.get('slices', [])) or '—'} | "
                f"{', '.join(row.get('qa_evidence', [])) or '—'} |"
            )
        artifacts.append({"kind": "traceability", "path": str(traceability_path.relative_to(repo)), "sha256": sha_text(traceability_path.read_text())})
    else:
        missing.append("Traceability artifact is missing")
        lines.append("Traceability artifact is unavailable.")

    lines += ["", "## Selected Ticket evidence", ""]
    if not selected:
        missing.append("No execution Ticket evidence is available")
        lines.append("No Ticket evidence is available.")
    for ticket in selected:
        number = ticket["number"]
        lines += [f"### Ticket #{number} — {ticket.get('title', 'Untitled')}", ""]
        lines.append(f"- Status: {ticket.get('status', 'unknown')}")
        dependencies = ticket.get("dependencies", [])
        lines.append(f"- Dependencies: {', '.join(f'#{item}' for item in dependencies) or 'none'}")
        triage = ticket.get("triage", {})
        controls = triage.get("controls", {})
        lines.append(
            f"- Triage: **{triage.get('result', 'not recorded')}** · "
            f"risk {controls.get('risk', 'not recorded')} · "
            f"verification {ticket.get('verification_level') or controls.get('gate_level', 'not recorded')}"
        )
        if triage.get("reason") or controls.get("reason"):
            lines.append(f"- Control reason: {triage.get('reason') or controls.get('reason')}")
        lines.append(
            f"- Verification duration: {ticket.get('verification_duration_seconds', 0)}s"
        )
        metrics = ticket.get("metrics", {})
        lines.append(
            "- Time by owner: "
            f"agent {metrics.get('agent_seconds', 0)}s · "
            f"gates {metrics.get('gate_seconds', 0)}s · "
            f"human wait {metrics.get('human_wait_seconds', 0)}s"
        )
        lines.append(
            f"- Recovery: {metrics.get('retry_count', 0)} retries · "
            f"{metrics.get('verifier_rejections', 0)} verifier rejections"
        )
        if ticket.get("issue_url"):
            lines.append(f"- GitHub Issue: {ticket['issue_url']}")
        else:
            missing.append(f"Ticket #{number} issue link is missing")
        if ticket.get("pr_url"):
            lines.append(f"- Pull request: {ticket['pr_url']}")
        else:
            missing.append(f"Ticket #{number} Pull request link is missing")
        lines += ["", "Protected Acceptance Tests:", ""]
        tests = ticket.get("qa_tests", {})
        if tests:
            lines += [f"- `{path}` · blob `{blob}`" for path, blob in sorted(tests.items())]
        else:
            missing.append(f"Ticket #{number} protected Acceptance Test metadata is missing")
            lines.append("- None recorded")
        lines += ["", "Causal Acceptance Test evidence:", ""]
        causal = ticket.get("qa_evidence", {})
        red = causal.get("red", {})
        green = causal.get("green", {})
        command = redact_credentials(str(causal.get("focused_test_command", "")))
        command_hash = causal.get("focused_test_command_sha256", "")
        if command:
            lines += [
                f"- Focused command: `{command}`",
                f"- Command hash: `{command_hash or 'not recorded'}`",
                f"- Before implementation: **{red.get('result', 'RED NOT PROVED')}** "
                f"· {red.get('classification', 'not classified')} · revision `{red.get('revision', 'not recorded')}`",
                f"- After implementation: **{green.get('result', 'GREEN NOT PROVED')}** "
                f"· {green.get('classification', 'not classified')} · revision `{green.get('revision', 'not recorded')}`",
            ]
        else:
            lines.append("- RED NOT PROVED · no focused command recorded")
        if manifest.get("profile") in {"standard", "assured", "autonomous-demo"}:
            if red.get("result") != "RED PROVED":
                missing.append(f"Ticket #{number} has no valid pre-implementation RED proof")
            if green.get("result") != "GREEN PROVED":
                missing.append(f"Ticket #{number} has no valid post-implementation GREEN proof")
        if manifest.get("profile") == "assured":
            negative = causal.get("negative", {})
            lines.append(
                f"- Assured negative proof: **{negative.get('result', 'NEGATIVE PROOF NOT PROVED')}**"
            )
            if negative.get("result") != "NEGATIVE PROOF PROVED":
                missing.append(f"Ticket #{number} has no valid Assured negative proof")
        lines += ["", "Verification gates:", ""]
        gates = ticket.get("gate_results", [])
        if gates:
            for gate in gates:
                result = gate.get("classification") or ("PASS" if gate.get("exit_code") == 0 else "FAIL")
                lines.append(
                    f"- {result} · {gate.get('name', 'unnamed')} · {gate.get('level', 'full')} · exit {gate.get('exit_code')} · "
                    f"{gate.get('duration_seconds', 0)}s"
                )
        else:
            missing.append(f"Ticket #{number} gate results are missing")
            lines.append("- None recorded")
        lines.append("")

    lines += ["## Handoff Receipts", ""]
    references = _receipt_references(manifest, selected)
    if not references:
        missing.append("No Handoff Receipts are available")
        lines.append("No Handoff Receipts are available.")
    for reference in references:
        path = repo / reference
        if not path.is_file():
            missing.append(f"Handoff Receipt is missing: {reference}")
            continue
        receipt = json.loads(path.read_text())
        lines += [
            f"### {receipt.get('role', 'unknown').replace('_', ' ').title()} · {receipt.get('phase', 'unknown')}",
            "",
            f"- Claim: {redact_credentials(str(receipt.get('claimed_result', 'not recorded')))}",
            f"- Verification: {redact_credentials('; '.join(receipt.get('verification', [])) or 'not recorded')}",
            f"- Unresolved risks: {redact_credentials('; '.join(receipt.get('unresolved_risks', [])) or 'none')}",
            f"- Timestamp: {receipt.get('timestamp', 'not recorded')}",
            "",
        ]
        artifacts.append({"kind": "handoff_receipt", "path": reference, "sha256": sha_text(path.read_text())})

    lines += ["## Factory Canvas", "", redact_credentials(canvas_text).strip(), ""]
    canvas_resolved = canvas_path.resolve()
    artifacts.append({
        "kind": "factory_canvas",
        "path": str(canvas_resolved.relative_to(repo.resolve())) if repo.resolve() in canvas_resolved.parents else canvas_resolved.name,
        "sha256": sha_text(canvas_text),
    })
    lines += ["## Completion rubric", ""]
    rubric = (
        "revised Product Review",
        "PRD-derived Tickets",
        "reviewed protected Acceptance Test",
        "Ticket trace",
        "peer-reviewed Factory Canvas",
    )
    lines += [f"- [ ] {item}" for item in rubric]
    if missing:
        lines += ["", "## Missing evidence", ""] + [f"- {item}" for item in missing]
    lines += [
        "",
        "## Sanitization boundary",
        "",
        "Raw prompts, raw logs, command output, environment values, tokens, and credentials are excluded.",
        "Review this packet before sharing or committing it.",
        "",
    ]
    packet_path = output_dir / "evidence-packet.md"
    packet_path.write_text(redact_credentials("\n".join(lines)))
    export_manifest = {
        "schema_version": 1,
        "workshop_version": WORKSHOP_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "plan_id": manifest["plan_id"],
        "profile": manifest.get("profile", "standard"),
        "governance": governance,
        "policy": manifest.get("policy", {}),
        "tickets": [ticket["number"] for ticket in selected],
        "artifacts": artifacts,
        "missing_evidence": missing,
        "packet_sha256": sha_text(packet_path.read_text()),
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(redact_credentials(json.dumps(export_manifest, indent=2)) + "\n")
    return packet_path, manifest_path
