"""Four-stage, human-gated PRD planning pipeline.

Each stage runs as a fresh expert agent with a strict JSON contract.  Humans
approve product intent before technical planning and approve the aligned
package before any GitHub issue is created.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from factory_contracts import (
    handoff_receipt,
    profile as factory_profile,
    role_input,
    write_handoff_receipt,
)
from factory_charter import FactoryCharter, FactoryCharterError
from project_contract import ProjectContract
from planner import dependency_waves, issue_body, render_review, validate_plan
from sensitive_data import redact_credentials
from adapter_capabilities import role_environment
from triage import classify_controls


PROMPT_VERSION = "2.0"
STAGES = (
    ("product_review", "01-product-review", "Product Review"),
    ("system_architecture", "02-system-architecture", "System Architecture"),
    ("program_design", "03-program-design", "Program Design"),
    ("vertical_slices", "04-vertical-slices", "Vertical Slices"),
)
STAGE_INDEX = {name: index for index, (name, _, _) in enumerate(STAGES)}
APPROVAL_KEYS = {
    "product_review": "product",
    "system_architecture": "system_architecture",
    "program_design": "program_design",
    "alignment": "alignment",
}
REVISION_STAGES = {
    "product": "product_review",
    "architecture": "system_architecture",
    "program": "program_design",
    "slices": "vertical_slices",
}
ID_PATTERN = re.compile(r"[A-Z][A-Z0-9_-]{0,31}")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def sha_file(path: Path) -> str:
    return sha_text(path.read_text())


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def write_json(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")


def append_log(path: Path, message: str):
    """Append one redacted, user-readable diagnostic to a planning log."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as stream:
        stream.write(f"[{now()}] {redact_credentials(message)}\n")


def claude_json_schema(path: Path) -> str:
    """Return the planning schema in the dialect accepted by Claude Code."""
    schema = read_json(path)
    schema.pop("$schema", None)
    return json.dumps(schema)


def _run_claude_agent(
    command: list[str], repo: Path, prompt: str, log: Path, stage: str,
) -> tuple[subprocess.CompletedProcess, dict | None]:
    """Run Claude with safe, realtime progress while retaining structured output."""
    title = stage.replace("_", " ").title()
    log.write_text("")
    last_message = ""
    last_heartbeat = time.monotonic()

    def emit(message: str, *, repeat: bool = False):
        nonlocal last_message
        if not repeat and message == last_message:
            return
        last_message = message
        rendered = f"[{now()}] {message}"
        with log.open("a") as stream:
            stream.write(rendered + "\n")
            stream.flush()
        print(message, flush=True)

    emit(f"Claude {title} started.")
    try:
        process = subprocess.Popen(
            command,
            cwd=repo,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=role_environment("CLAUDE_CONFIG_DIR", "XDG_CONFIG_HOME", "XDG_CACHE_HOME"),
        )
    except OSError as exc:
        emit(f"Claude {title} could not start: {exc}")
        raise

    assert process.stdin is not None
    assert process.stdout is not None
    process.stdin.write(prompt)
    process.stdin.close()
    structured: dict | None = None
    errors: list[str] = []
    result_failed = False

    for line in process.stdout:
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            message = line[:2000]
            errors.append(message)
            emit(f"Claude reported: {message}")
            continue

        event_type = event.get("type")
        if event_type == "system" and event.get("subtype") == "init":
            emit("Claude session initialized.")
        elif event_type == "stream_event":
            stream_event = event.get("event", {})
            stream_type = stream_event.get("type")
            if stream_type == "content_block_start":
                block = stream_event.get("content_block", {})
                block_type = block.get("type")
                if block_type == "thinking":
                    emit("Claude is analyzing repository context.")
                elif block_type == "tool_use":
                    tool = block.get("name") or "a read-only tool"
                    emit(f"Claude is using {tool}.")
                elif block_type == "text":
                    emit("Claude is drafting the structured artifact.")
            elif stream_type == "content_block_delta" and time.monotonic() - last_heartbeat >= 10:
                emit("Claude is still working.", repeat=True)
                last_heartbeat = time.monotonic()
        elif event_type == "user":
            emit("Claude received repository context.")
        elif event_type == "result":
            structured_value = event.get("structured_output")
            if event.get("subtype") == "success" and isinstance(structured_value, dict):
                structured = structured_value
                duration = event.get("duration_ms")
                turns = event.get("num_turns")
                detail = ""
                if isinstance(duration, (int, float)):
                    detail += f" in {duration / 1000:.1f}s"
                if isinstance(turns, int):
                    detail += f" across {turns} turn{'s' if turns != 1 else ''}"
                emit(f"Claude {title} completed{detail}.")
            else:
                result_failed = True
                message = event.get("result") or "Claude returned an unsuccessful result."
                errors.append(str(message)[:2000])
                emit(f"Claude {title} failed.")

    process.stdout.close()
    return_code = process.wait()
    if return_code == 0 and (result_failed or structured is None):
        return_code = 1
        if structured is None:
            errors.append("Claude returned no valid structured_output.")
            emit(f"Claude {title} returned no valid structured output.")
    result = subprocess.CompletedProcess(command, return_code, "", "\n".join(errors))
    return result, structured


def relative_path(path: Path, repo: Path) -> str:
    """Return a stable repo-relative path even across macOS /var symlinks."""
    return os.path.relpath(path.resolve(), repo.resolve())


def unique_ids(items: list[dict], label: str) -> set[str]:
    result: set[str] = set()
    for item in items:
        identifier = item.get("id")
        if not isinstance(identifier, str) or not ID_PATTERN.fullmatch(identifier):
            raise ValueError(f"{label} has invalid id: {identifier!r}")
        if identifier in result:
            raise ValueError(f"{label} has duplicate id: {identifier}")
        result.add(identifier)
    return result


def require_references(values: list[str], allowed: set[str], label: str):
    if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
        raise ValueError(f"{label} references must be a list of IDs")
    unknown = set(values) - allowed
    if unknown:
        raise ValueError(f"{label} references unknown IDs: {', '.join(sorted(unknown))}")


def validate_product(product: dict):
    project = product.get("project")
    if not isinstance(project, dict) or not all(project.get(key) for key in ("name", "summary", "problem", "desired_outcome")):
        raise ValueError("product review requires project name, summary, problem, and desired outcome")
    requirements = product.get("requirements")
    if not isinstance(requirements, list) or not requirements:
        raise ValueError("product review requires at least one requirement")
    requirement_ids = unique_ids(requirements, "requirement")
    for requirement in requirements:
        if not all(requirement.get(key) for key in ("statement", "source", "success_evidence")):
            raise ValueError(f"{requirement['id']} requires statement, source, and success evidence")
    if not isinstance(product.get("users"), list) or not product["users"]:
        raise ValueError("product review requires at least one user")
    unique_ids(product["users"], "user")
    if not isinstance(product.get("journeys"), list) or not product["journeys"]:
        raise ValueError("product review requires at least one journey")
    unique_ids(product["journeys"], "journey")
    for journey in product["journeys"]:
        require_references(journey.get("requirements", []), requirement_ids, journey["id"])
        if not journey.get("steps") or not journey.get("outcome"):
            raise ValueError(f"{journey['id']} requires steps and an observable outcome")
    scope = product.get("scope")
    if not isinstance(scope, dict) or not isinstance(scope.get("in"), list) or not isinstance(scope.get("out"), list):
        raise ValueError("product review requires explicit in-scope and out-of-scope lists")
    if not isinstance(product.get("blocking_questions"), list):
        raise ValueError("product review blocking_questions must be a list")


def validate_architecture(architecture: dict, product: dict):
    requirement_ids = {item["id"] for item in product["requirements"]}
    components = architecture.get("components")
    if not isinstance(components, list) or not components:
        raise ValueError("architecture requires at least one component")
    component_ids = unique_ids(components, "component")
    covered_requirements: set[str] = set()
    for component in components:
        require_references(component.get("requirements", []), requirement_ids, component["id"])
        covered_requirements.update(component["requirements"])
    contracts = architecture.get("contracts")
    if not isinstance(contracts, list) or not contracts:
        raise ValueError("architecture requires at least one component contract")
    unique_ids(contracts, "contract")
    for contract in contracts:
        require_references([contract.get("provider")], component_ids, contract["id"])
        require_references(contract.get("consumers", []), component_ids, contract["id"])
        require_references(contract.get("requirements", []), requirement_ids, contract["id"])
        if not contract.get("input") or not contract.get("output"):
            raise ValueError(f"{contract['id']} requires input and output contracts")
    for collection, label in (("data_models", "data model"), ("decisions", "decision")):
        items = architecture.get(collection)
        if not isinstance(items, list):
            raise ValueError(f"architecture {collection} must be a list")
        unique_ids(items, label)
        for item in items:
            require_references(item.get("requirements", []), requirement_ids, item["id"])
    missing = requirement_ids - covered_requirements
    if missing:
        raise ValueError(f"requirements without an owning component: {', '.join(sorted(missing))}")
    if not isinstance(architecture.get("blocking_questions"), list):
        raise ValueError("architecture blocking_questions must be a list")


def program_element_ids(program: dict) -> set[str]:
    return {
        item["id"]
        for collection in ("modules", "types", "functions", "call_flows", "test_seams")
        for item in program.get(collection, [])
    }


def validate_program(program: dict, product: dict, architecture: dict):
    requirement_ids = {item["id"] for item in product["requirements"]}
    component_ids = {item["id"] for item in architecture["components"]}
    contract_ids = {item["id"] for item in architecture["contracts"]}
    modules = program.get("modules")
    if not isinstance(modules, list) or not modules:
        raise ValueError("program design requires at least one module")
    module_ids = unique_ids(modules, "module")
    for module in modules:
        require_references(module.get("components", []), component_ids, module["id"])
        if not module.get("path") or not module.get("responsibility"):
            raise ValueError(f"{module['id']} requires a path and responsibility")
    function_ids: set[str] = set()
    for collection, label in (("types", "type"), ("functions", "function"), ("call_flows", "call flow"), ("test_seams", "test seam")):
        items = program.get(collection)
        if not isinstance(items, list):
            raise ValueError(f"program design {collection} must be a list")
        ids = unique_ids(items, label)
        if collection == "functions":
            function_ids = ids
        for item in items:
            require_references(item.get("requirements", []), requirement_ids, item["id"])
            if "module" in item:
                require_references([item["module"]], module_ids, item["id"])
            if collection == "functions":
                require_references(item.get("contracts", []), contract_ids, item["id"])
    for function in program["functions"]:
        internal_calls = [item for item in function["calls"] if not item.startswith("external:")]
        require_references(internal_calls, function_ids, function["id"])
    if not isinstance(program.get("blocking_questions"), list):
        raise ValueError("program design blocking_questions must be a list")


def _depends_on(ticket_key: str, possible_dependency: str, tickets: dict[str, dict]) -> bool:
    pending = list(tickets[ticket_key]["dependencies"])
    seen: set[str] = set()
    while pending:
        key = pending.pop()
        if key == possible_dependency:
            return True
        if key not in seen:
            seen.add(key)
            pending.extend(tickets[key]["dependencies"])
    return False


def validate_vertical_slices(slices: dict, product: dict, architecture: dict, program: dict) -> list[str]:
    slices.setdefault("plan_version", 2)
    order = validate_plan(slices)
    requirement_ids = {item["id"] for item in product["requirements"]}
    contract_ids = {item["id"] for item in architecture["contracts"]}
    element_ids = program_element_ids(program)
    covered_requirements: set[str] = set()
    covered_elements: set[str] = set()
    tickets = {ticket["key"]: ticket for ticket in slices["tickets"]}
    for ticket in slices["tickets"]:
        for field in ("requirement_ids", "contract_ids", "program_element_ids", "qa_evidence", "file_ownership"):
            if not isinstance(ticket.get(field), list) or not ticket[field]:
                raise ValueError(f"{ticket['key']} requires non-empty {field}")
        require_references(ticket["requirement_ids"], requirement_ids, ticket["key"])
        require_references(ticket["contract_ids"], contract_ids, ticket["key"])
        require_references(ticket["program_element_ids"], element_ids, ticket["key"])
        if not ticket.get("vertical_outcome"):
            raise ValueError(f"{ticket['key']} requires an end-to-end vertical outcome")
        covered_requirements.update(ticket["requirement_ids"])
        covered_elements.update(ticket["program_element_ids"])
    missing_requirements = requirement_ids - covered_requirements
    if missing_requirements:
        raise ValueError(f"requirements without a vertical slice: {', '.join(sorted(missing_requirements))}")
    missing_elements = element_ids - covered_elements
    if missing_elements:
        raise ValueError(f"program elements without a ticket owner: {', '.join(sorted(missing_elements))}")
    owners: dict[str, list[str]] = {}
    for ticket in slices["tickets"]:
        for path in ticket["file_ownership"]:
            owners.setdefault(path, []).append(ticket["key"])
    for path, keys in owners.items():
        for index, first in enumerate(keys):
            for second in keys[index + 1:]:
                if not _depends_on(first, second, tickets) and not _depends_on(second, first, tickets):
                    raise ValueError(f"parallel tickets {first} and {second} both own {path}")
    return order


def validate_lean_vertical_slices(slices: dict, product: dict) -> list[str]:
    """Validate slices that intentionally have no architecture or program artifact."""
    slices.setdefault("plan_version", 2)
    order = validate_plan(slices)
    requirement_ids = {item["id"] for item in product["requirements"]}
    covered_requirements: set[str] = set()
    tickets = {ticket["key"]: ticket for ticket in slices["tickets"]}
    owners: dict[str, list[str]] = {}
    for ticket in slices["tickets"]:
        for field in ("requirement_ids", "qa_evidence", "file_ownership"):
            if not isinstance(ticket.get(field), list) or not ticket[field]:
                raise ValueError(f"{ticket['key']} requires non-empty {field}")
        for field in ("contract_ids", "program_element_ids"):
            if not isinstance(ticket.get(field), list):
                raise ValueError(f"{ticket['key']} {field} must be a list")
        require_references(ticket["requirement_ids"], requirement_ids, ticket["key"])
        if not ticket.get("vertical_outcome"):
            raise ValueError(f"{ticket['key']} requires an end-to-end vertical outcome")
        covered_requirements.update(ticket["requirement_ids"])
        for path in ticket["file_ownership"]:
            owners.setdefault(path, []).append(ticket["key"])
    missing = requirement_ids - covered_requirements
    if missing:
        raise ValueError(f"requirements without a vertical slice: {', '.join(sorted(missing))}")
    for path, keys in owners.items():
        for index, first in enumerate(keys):
            for second in keys[index + 1:]:
                if not _depends_on(first, second, tickets) and not _depends_on(second, first, tickets):
                    raise ValueError(f"parallel tickets {first} and {second} both own {path}")
    return order


def validate_project_paths(slices: dict, project: ProjectContract) -> None:
    """Keep planned ownership inside the checkout and outside protected policy."""
    protected = (*project.protected_paths, "factory.project.toml")
    for ticket in slices["tickets"]:
        for raw_path in ticket["file_ownership"]:
            if not isinstance(raw_path, str) or not raw_path.strip() or "\\" in raw_path:
                raise ValueError(f"{ticket['key']} has an invalid owned path: {raw_path!r}")
            path = PurePosixPath(raw_path.strip())
            normalized = path.as_posix().removeprefix("./")
            if path.is_absolute() or ".." in path.parts or not normalized:
                raise ValueError(f"{ticket['key']} owned path must stay inside the repository: {raw_path}")
            for protected_path in protected:
                protected_path = protected_path.rstrip("/")
                if normalized == protected_path or normalized.startswith(protected_path + "/"):
                    raise ValueError(
                        f"{ticket['key']} cannot own protected Project Contract path: {normalized}"
                    )


def build_traceability(
    product: dict,
    architecture: dict | None,
    program: dict | None,
    slices: dict,
) -> dict:
    rows = []
    for requirement in product["requirements"]:
        identifier = requirement["id"]
        contracts = [
            item["id"] for item in (architecture or {}).get("contracts", [])
            if identifier in item["requirements"]
        ]
        elements = [
            item["id"]
            for collection in ("types", "functions", "call_flows", "test_seams")
            for item in (program or {}).get(collection, [])
            if identifier in item["requirements"]
        ]
        tickets = [item for item in slices["tickets"] if identifier in item["requirement_ids"]]
        rows.append({
            "requirement_id": identifier,
            "product_behavior": requirement["statement"],
            "architecture_contracts": contracts,
            "program_elements": elements,
            "slices": [item["key"] for item in tickets],
            "qa_evidence": sorted({evidence for item in tickets for evidence in item["qa_evidence"]}),
        })
    return {"rows": rows}


def validate_traceability(traceability: dict):
    for row in traceability.get("rows", []):
        if not row.get("slices"):
            raise ValueError(f"{row.get('requirement_id')} has no implementing slice")
        if not row.get("qa_evidence"):
            raise ValueError(f"{row.get('requirement_id')} has no QA evidence")


def stage_prompt(
    stage: str,
    prd: str,
    inputs: dict[str, dict],
    default_agent: str,
    minimum: int,
    maximum: int,
    profile_name: str = "standard",
    repository_context: str = "",
) -> str:
    shared = """Use the repository only as implementation context; product scope comes from the PRD and approved upstream artifacts. Preserve stable IDs exactly. Every new object ID must start with an uppercase letter and contain only uppercase letters, digits, underscores, or hyphens (for example USER_HOME_COOK or COMPONENT_API). Ticket keys follow the same rule and must be at most 16 characters.
Inspect the current codebase when technical or file-level detail is required. Do not invent scope. Put decisions that require a human in blocking_questions.
Return only JSON matching the supplied schema. This artifact is an auditable contract for the next expert."""
    roles = {
        "product_review": """You are the Product Review expert. Clarify the problem, users, observable behavior, scope, journeys, success evidence, mockup needs, assumptions, and blocking questions. Give requirements stable IDs R1, R2, and so on. Cite the PRD section or phrase in each requirement's source. Do not design architecture or create implementation tickets.""",
        "system_architecture": """You are the System Architecture expert. Inspect the existing repository and, using the approved product review, define components, ownership boundaries, data models, explicit component contracts, architectural decisions, constraints, and risks. Map every item to product requirement IDs. Every requirement must have an owning component. Do not assign tickets or write low-level implementation code.""",
        "program_design": """You are the Program Design expert. Inspect the existing code and turn the approved architecture into a concrete code design: modules and paths, types, function signatures, call relationships, error behavior, call flows, and test seams. Use stable IDs (MOD-, TYPE-, FN-, FLOW-, TEST-), reference contracts and requirements, and prefix calls outside this design with external:. modules[].components must contain only component IDs copied from System Architecture. Never put function IDs, type IDs, constants, or prose in modules[].components. Every type and function module reference must name a MOD- ID defined in this artifact. Do not create tickets.""",
        "vertical_slices": f"""You are the Vertical Slices expert. Divide the aligned product, architecture, and program design into {minimum}-{maximum} small end-to-end tickets. Each ticket must deliver an observable vertical outcome, own explicit files, name QA evidence, and map requirement, contract, and program-element IDs. Every program element and requirement must have an owner. Overlapping file ownership is allowed only when one ticket depends on the other. Keep the dependency graph acyclic and maximize safe parallel work. Default agent to {default_agent}.""",
    }
    planning_roles = set(factory_profile(profile_name)["planning_roles"])
    if stage == "vertical_slices" and "system_architecture" not in planning_roles:
        roles[stage] = f"""You are the Vertical Slices expert for the Lean Factory Profile. Divide the approved product intent into {minimum}-{maximum} small end-to-end tickets. Each ticket must deliver an observable outcome, own explicit files, name evidence from existing tests, and map product requirement IDs. Set contract_ids and program_element_ids to empty arrays because this profile intentionally omits architecture and program-design roles. Keep dependencies acyclic and default agent to {default_agent}."""
    identifier_guidance = ""
    if stage == "vertical_slices" and "system_architecture" in planning_roles:
        architecture = inputs.get("system_architecture", {})
        program = inputs.get("program_design", {})
        contract_ids = sorted(item["id"] for item in architecture.get("contracts", []))
        element_ids = sorted(program_element_ids(program))
        identifier_guidance = (
            "\n\n## Exact Vertical Slice traceability identifiers\n\n"
            f"Allowed contract IDs: {', '.join(contract_ids)}\n\n"
            f"Allowed program-element IDs: {', '.join(element_ids)}\n\n"
            "Copy identifiers exactly from these lists. `contract_ids` must never contain "
            "component IDs or architecture-decision IDs. `program_element_ids` must never "
            "contain component, contract, or architecture-decision IDs."
        )
    context = "\n\n".join(
        f"## Approved {name.replace('_', ' ').title()}\n```json\n{json.dumps(value, indent=2)}\n```"
        for name, value in inputs.items()
    )
    return f"""{roles[stage]}

{shared}

## Source PRD

{prd}

## Repository Project Contract and inventory

```json
{repository_context or '{}'}
```

{context}{identifier_guidance}
"""


def render_product(product: dict, plan_id: str) -> str:
    project = product["project"]
    lines = [f"# Product review — {project['name']}", "", project["summary"], "", f"Plan ID: `{plan_id}`", ""]
    lines += ["## Problem and desired outcome", "", project["problem"], "", f"**Desired outcome:** {project['desired_outcome']}", ""]
    lines += ["## Requirements", "", "| ID | Behavior | Success evidence | Source |", "| --- | --- | --- | --- |"]
    for item in product["requirements"]:
        lines.append(f"| {item['id']} | {item['statement']} | {item['success_evidence']} | {item['source']} |")
    lines += ["", "## User journeys", ""]
    for journey in product["journeys"]:
        lines += [f"### {journey['id']} — {journey['name']}", "", journey["outcome"], ""]
        lines += [f"{index}. {step}" for index, step in enumerate(journey["steps"], 1)] + [""]
    lines += ["## Scope", "", "**In scope**", ""] + [f"- {item}" for item in product["scope"]["in"]]
    lines += ["", "**Out of scope**", ""] + [f"- {item}" for item in product["scope"]["out"]] + [""]
    if product["blocking_questions"]:
        lines += ["## Blocking questions", ""] + [f"- {item}" for item in product["blocking_questions"]] + [""]
    lines += ["## Human gate", "", "Resolve all blocking questions, edit the JSON if needed, then run:", "", f"`./factory/factory approve-product {plan_id}`", ""]
    return "\n".join(lines)


def render_architecture(value: dict, plan_id: str) -> str:
    lines = ["# System architecture", "", f"Plan ID: `{plan_id}`", "", "## Components", ""]
    for item in value["components"]:
        lines += [f"### {item['id']} — {item['name']}", "", item["responsibility"], "", f"Requirements: {', '.join(item['requirements'])}", ""]
    lines += ["## Contracts", "", "| ID | Contract | Provider → consumers | Input → output |", "| --- | --- | --- | --- |"]
    for item in value["contracts"]:
        lines.append(f"| {item['id']} | {item['name']} | {item['provider']} → {', '.join(item['consumers'])} | {item['input']} → {item['output']} |")
    lines += ["", "## Decisions", ""]
    for item in value["decisions"]:
        lines += [f"- **{item['id']}: {item['decision']}** — {item['rationale']}"]
    if value["blocking_questions"]:
        lines += ["", "## Blocking questions", ""] + [f"- {item}" for item in value["blocking_questions"]]
    return "\n".join(lines) + "\n"


def render_program(value: dict, plan_id: str) -> str:
    lines = ["# Program design", "", f"Plan ID: `{plan_id}`", "", "## Modules", "", "| ID | Path | Responsibility |", "| --- | --- | --- |"]
    for item in value["modules"]:
        lines.append(f"| {item['id']} | `{item['path']}` | {item['responsibility']} |")
    lines += ["", "## Types and functions", ""]
    for item in value["types"]:
        lines += [f"- **{item['id']} `{item['name']}`** in {item['module']}: {item['definition']}"]
    for item in value["functions"]:
        lines += [f"- **{item['id']} `{item['signature']}`** in {item['module']}; errors: {item['error_behavior']}"]
    lines += ["", "## Call flows", ""]
    for item in value["call_flows"]:
        lines += [f"### {item['id']} — {item['name']}", "", " → ".join(item["steps"]), ""]
    if value["blocking_questions"]:
        lines += ["## Blocking questions", ""] + [f"- {item}" for item in value["blocking_questions"]]
    return "\n".join(lines) + "\n"


def _stage_paths(run_dir: Path, stage: str) -> tuple[Path, Path]:
    filename = next(filename for name, filename, _ in STAGES if name == stage)
    return run_dir / f"{filename}.json", run_dir / f"{filename}.md"


def _render_stage(stage: str, value: dict, plan_id: str, json_path: Path) -> str:
    if stage == "product_review":
        return render_product(value, plan_id)
    if stage == "system_architecture":
        return render_architecture(value, plan_id)
    if stage == "program_design":
        return render_program(value, plan_id)
    review_value = dict(value, _plan_path=str(json_path))
    return render_review(review_value)


def resolve_run(repo: Path, identifier: str | Path) -> Path:
    supplied = Path(identifier).expanduser()
    candidates = [supplied if supplied.is_absolute() else (Path.cwd() / supplied), repo / ".factory/plans" / str(identifier)]
    for candidate in candidates:
        candidate = candidate.resolve()
        if candidate.is_file() and (candidate.name == "manifest.json" or (candidate.parent / "manifest.json").is_file()):
            candidate = candidate.parent
        if candidate.is_dir() and (candidate / "manifest.json").is_file():
            return candidate
    raise FileNotFoundError(f"planning run not found: {identifier}")


def load_manifest(run_dir: Path) -> dict:
    manifest = read_json(run_dir / "manifest.json")
    _ensure_approvals(manifest)
    return manifest


def _ensure_approvals(manifest: dict) -> dict:
    """Add approval slots without invalidating compatible v2 planning runs."""
    approvals = manifest.setdefault("approvals", {})
    for key in APPROVAL_KEYS.values():
        approvals.setdefault(key, None)
    return approvals


def _required_planning_approvals(manifest: dict) -> set[str]:
    configured = manifest.get("governance", {}).get("planning_approvals")
    if not isinstance(configured, list):
        configured = ["product_review", "alignment"]
    selected = manifest.get("planning_controls", {}).get("planning_approvals", [])
    if not isinstance(selected, list):
        selected = []
    return set(configured) | set(selected)


def _refresh_planning_controls(repo: Path, run_dir: Path, manifest: dict) -> dict:
    """Select planning approvals from the paths proposed by Vertical Slices."""
    slices_path, _ = _stage_paths(run_dir, "vertical_slices")
    if not slices_path.is_file():
        return manifest.get("planning_controls", {})
    slices = read_json(slices_path)
    paths = [
        path
        for ticket in slices.get("tickets", [])
        for path in ticket.get("file_ownership", [])
        if isinstance(path, str)
    ]
    controls = classify_controls(
        FactoryCharter.load(repo, require_approved=True), paths,
    )
    applicable = set(factory_profile(manifest.get("profile", "standard"))["planning_roles"])
    unsupported = (
        set(controls["planning_approvals"])
        - applicable
        - {"alignment"}
    )
    if unsupported:
        message = (
            "the proposed paths require planning stages outside this Factory Profile: "
            + ", ".join(sorted(unsupported))
            + "; choose Standard or Assured and plan again"
        )
        manifest["planning_controls"] = controls
        manifest["planning_control_error"] = message
        manifest["status"] = "stale_factory_profile"
        save_manifest(repo, run_dir, manifest)
        raise ValueError(message)
    manifest.pop("planning_control_error", None)
    manifest["planning_controls"] = controls
    return controls


def _invalidate_approvals_from(manifest: dict, stage: str) -> None:
    approvals = _ensure_approvals(manifest)
    start = STAGE_INDEX.get(stage, 0)
    for name, _, _ in STAGES[start:]:
        key = APPROVAL_KEYS.get(name)
        if key:
            approvals[key] = None
    approvals["alignment"] = None


def _stage_approval_current(run_dir: Path, manifest: dict, stage: str) -> bool:
    approval = _ensure_approvals(manifest).get(APPROVAL_KEYS[stage])
    artifact, _ = _stage_paths(run_dir, stage)
    return bool(
        isinstance(approval, dict)
        and artifact.is_file()
        and approval.get("artifact_sha256") == sha_file(artifact)
        and manifest["stages"][stage].get("source_hashes")
        == _input_hashes(run_dir, stage, manifest)
    )


def save_manifest(repo: Path, run_dir: Path, manifest: dict):
    _ensure_approvals(manifest)
    manifest["updated_at"] = now()
    write_json(run_dir / "manifest.json", manifest)
    write_dashboard_state(repo, run_dir, manifest)


def write_dashboard_state(repo: Path, run_dir: Path, manifest: dict):
    _ensure_approvals(manifest)
    stages = []
    for stage, filename, title in STAGES:
        record = manifest["stages"][stage]
        json_path, md_path = _stage_paths(run_dir, stage)
        questions = []
        if json_path.is_file():
            value = read_json(json_path)
            questions = value.get("blocking_questions", value.get("open_questions", []))
        stages.append({
            "id": stage,
            "title": title,
            "status": record["status"],
            "json": relative_path(json_path, repo) if json_path.is_file() else "",
            "markdown": relative_path(md_path, repo) if md_path.is_file() else "",
            "sha256": record.get("sha256", ""),
            "questions": questions,
            "receipt": record.get("receipt", ""),
            "failure_kind": record.get("failure_kind", ""),
            "error": record.get("error", ""),
            "validation_error": record.get("validation_error", ""),
            "rejected_artifact": record.get("rejected_artifact", ""),
            "failure_count": record.get("failure_count", 0),
            "same_failure_count": record.get("same_failure_count", 0),
        })
    state = {
        "plan_id": manifest["plan_id"],
        "project": manifest.get("project", "Planning run"),
        "status": manifest["status"],
        "planning_agent": manifest.get("planning_agent", "codex"),
        "mode": "rehearsal" if manifest.get("planning_agent") == "mock" else "live",
        "updated_at": manifest["updated_at"],
        "run_directory": relative_path(run_dir, repo),
        "approvals": manifest["approvals"],
        "profile": manifest.get("profile", "standard"),
        "governance": manifest.get("governance", {}),
        "planning_controls": manifest.get("planning_controls", {}),
        "planning_control_error": manifest.get("planning_control_error", ""),
        "policy": manifest.get("policy", {}),
        "stages": stages,
        "alignment_review": relative_path(run_dir / "alignment-review.md", repo) if (run_dir / "alignment-review.md").is_file() else "",
        "traceability": relative_path(run_dir / "traceability.json", repo) if (run_dir / "traceability.json").is_file() else "",
        "receipts": manifest.get("receipts", []),
    }
    write_json(repo / ".factory/planning-state.json", state)


def _stage_inputs(run_dir: Path, stage: str) -> dict[str, dict]:
    result = {}
    for current, _, _ in STAGES:
        if current == stage:
            break
        path, _ = _stage_paths(run_dir, current)
        if path.is_file():
            result[current] = read_json(path)
    return result


def _input_hashes(run_dir: Path, stage: str, manifest: dict) -> dict[str, str]:
    hashes = {"source_prd": sha_file(run_dir / "source-prd.md")}
    for current, _, _ in STAGES:
        if current == stage:
            break
        path, _ = _stage_paths(run_dir, current)
        if path.is_file():
            hashes[current] = sha_file(path)
    return hashes


def _validate_stage(
    stage: str,
    value: dict,
    inputs: dict[str, dict],
    profile_name: str = "standard",
    project: ProjectContract | None = None,
):
    if stage == "product_review":
        validate_product(value)
    elif stage == "system_architecture":
        validate_architecture(value, inputs["product_review"])
    elif stage == "program_design":
        validate_program(value, inputs["product_review"], inputs["system_architecture"])
    elif "system_architecture" not in factory_profile(profile_name)["planning_roles"]:
        validate_lean_vertical_slices(value, inputs["product_review"])
    else:
        validate_vertical_slices(value, inputs["product_review"], inputs["system_architecture"], inputs["program_design"])
    if stage == "vertical_slices" and project is not None:
        validate_project_paths(value, project)


def _fixture_path(repo: Path, stage: str) -> Path:
    filename = next(filename for name, filename, _ in STAGES if name == stage)
    supplied = repo / "factory/scenarios/recipe-rebrand/planning" / f"{filename}.json"
    return supplied if supplied.is_file() else Path(__file__).with_name("scenarios") / "recipe-rebrand" / "planning" / f"{filename}.json"


def _rejected_stage_path(repo: Path, stage_record: dict) -> Path | None:
    """Resolve a validator-owned rejected artifact without trusting manifest paths."""
    reference = stage_record.get("rejected_artifact", "")
    if not isinstance(reference, str) or not reference:
        return None
    candidate = (repo / reference).resolve()
    try:
        candidate.relative_to(repo.resolve())
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def _run_stage_agent_impl(
    repo: Path, run_dir: Path, stage: str, manifest: dict,
    planning_agent: str, agent_bin: str, mock: bool, feedback: str | None = None,
) -> dict:
    json_path, _ = _stage_paths(run_dir, stage)
    raw = run_dir / f".{stage}-raw.json"
    inputs = _stage_inputs(run_dir, stage)
    prompt = stage_prompt(
        stage, (run_dir / "source-prd.md").read_text(), inputs,
        manifest["default_ticket_agent"], manifest["ticket_limits"]["minimum"], manifest["ticket_limits"]["maximum"],
        manifest.get("profile", "standard"),
        ProjectContract.load(repo).context(),
    )
    charter = FactoryCharter.load(repo, require_approved=True)
    prompt += (
        "\n## Approved Factory Charter\n\n```json\n"
        f"{charter.context()}\n```\n"
    )
    stage_record = manifest["stages"][stage]
    previous_validation_error = stage_record.get("validation_error", "")
    rejected_path = _rejected_stage_path(repo, stage_record)
    if previous_validation_error:
        rejected_content = ""
        if rejected_path is not None and rejected_path.is_file():
            rejected_content = rejected_path.read_text()[:120_000]
        prompt += (
            "\n## Previous validation failure\n\n"
            "The previous structured artifact was rejected by the deterministic validator. "
            "Return a complete corrected replacement; do not merely explain the error.\n\n"
            f"Validator error: {previous_validation_error}\n"
        )
        if rejected_content:
            prompt += f"\n### Rejected artifact\n\n```json\n{rejected_content}\n```\n"
    stage_record.pop("failure_kind", None)
    stage_record.pop("error", None)
    revision_number = len(manifest.get("revisions", [])) + 1 if feedback else None
    if feedback:
        revision_source = json_path if json_path.is_file() else rejected_path
        if revision_source is None:
            raise ValueError(
                f"{stage.replace('_', ' ').title()} has no artifact available to revise"
            )
        prompt += (
            "\n## Current artifact\n\n"
            f"```json\n{json.dumps(read_json(revision_source), indent=2)}\n```\n"
            "\n## Human revision feedback\n\n"
            f"{feedback}\n\nRevise only the {stage.replace('_', ' ')} artifact. "
            "Treat the human decisions as authoritative, resolve the answered "
            "blocking questions in the artifact, and preserve stable IDs unless "
            "the feedback explicitly makes one invalid. Keep a question blocked "
            "only when the feedback does not provide the decision needed to resolve it.\n"
        )
    contract = role_input(repo, stage)
    prompt += "\n" + contract["text"]
    suffix = f"-revision-{revision_number}" if revision_number else ""
    prompt_path = repo / ".factory/prompts" / f"planner-{manifest['plan_id']}-{stage}{suffix}.md"
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text(prompt)
    log = repo / ".factory/logs" / f"planner-{manifest['plan_id']}-{stage}{suffix}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    if mock:
        fixture = _fixture_path(repo, stage)
        if feedback and stage == "product_review":
            fixture = fixture.with_name("01-product-review-revised.json")
        if not fixture.is_file():
            raise FileNotFoundError(f"mock planning fixture not found: {fixture}")
        shutil.copyfile(fixture, raw)
        log.write_text(f"Mock {stage} expert copied {fixture}\n")
    else:
        schema = repo / "factory/planning_schemas" / f"{stage}.json"
        if not schema.is_file():
            schema = Path(__file__).with_name("planning_schemas") / f"{stage}.json"
        if planning_agent == "codex":
            command = [
                agent_bin, "exec", "--sandbox", "read-only", "--ephemeral",
                "--ignore-user-config", "--ignore-rules", "--output-schema", str(schema),
                "-o", str(raw), "-",
            ]
            result = subprocess.run(
                command, cwd=repo, input=prompt, text=True, capture_output=True,
                env=role_environment("CODEX_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME"),
            )
        elif planning_agent == "claude":
            command = [
                agent_bin, "-p", "--permission-mode", "plan",
                "--tools", "Read,Glob,Grep", "--no-session-persistence",
                "--output-format", "stream-json", "--verbose", "--include-partial-messages",
                "--json-schema", claude_json_schema(schema),
            ]
            result, structured = _run_claude_agent(command, repo, prompt, log, stage)
            if result.returncode == 0 and structured is not None:
                write_json(raw, structured)
        else:
            raise ValueError(f"unsupported planning agent: {planning_agent}")
        if planning_agent == "codex":
            log.write_text(result.stdout + result.stderr)
        if result.returncode:
            detail = redact_credentials((result.stderr or "").strip())[:2000]
            if detail:
                append_log(log, f"Agent error: {detail}")
                raise RuntimeError(f"{stage.replace('_', ' ')} expert failed: {detail}; see {log}")
            raise RuntimeError(f"{stage.replace('_', ' ')} expert failed; see {log}")
    try:
        value = read_json(raw)
    finally:
        raw.unlink(missing_ok=True)
    if stage == "vertical_slices":
        planning_roles = factory_profile(manifest.get("profile", "standard"))["planning_roles"]
        if "system_architecture" not in planning_roles:
            for ticket in value.get("tickets", []):
                ticket["contract_ids"] = []
                ticket["program_element_ids"] = []
        value.update({
            "plan_version": 2,
            "plan_id": manifest["plan_id"],
            "source_prd": str(run_dir / "source-prd.md"),
            "created_at": now(),
            "planning_agent": planning_agent if not mock else "mock",
        })
    try:
        _validate_stage(
            stage, value, inputs, manifest.get("profile", "standard"),
            ProjectContract.load(repo),
        )
        if stage == "vertical_slices":
            count = len(value["tickets"])
            minimum = manifest["ticket_limits"]["minimum"]
            maximum = manifest["ticket_limits"]["maximum"]
            if not minimum <= count <= maximum:
                raise ValueError(
                    f"vertical slices expert returned {count} tickets; "
                    f"expected {minimum}-{maximum}"
                )
    except ValueError as exc:
        failure_number = int(stage_record.get("failure_count", 0)) + 1
        rejected_path = run_dir / "rejected" / f"{stage}-attempt-{failure_number}.json"
        write_json(rejected_path, value)
        message = redact_credentials(str(exc))[:2000]
        stage_record.update({
            "failure_kind": "validation",
            "error": message,
            "validation_error": message,
            "rejected_artifact": relative_path(rejected_path, repo),
        })
        append_log(log, f"Deterministic validation failed: {message}")
        raise
    write_json(json_path, value)
    _, markdown_path = _stage_paths(run_dir, stage)
    markdown_path.write_text(_render_stage(stage, value, manifest["plan_id"], json_path))
    manifest["stages"][stage] = {
        "status": "blocked" if value.get("blocking_questions", value.get("open_questions", [])) else "complete",
        "sha256": sha_file(json_path),
        "source_hashes": _input_hashes(run_dir, stage, manifest),
        "agent": "mock" if mock else planning_agent,
        "prompt_version": PROMPT_VERSION,
        "created_at": now(),
        "log": relative_path(log, repo),
        "prompt": relative_path(prompt_path, repo),
    }
    receipt = handoff_receipt(
        run_id=manifest["plan_id"],
        role=stage,
        phase="Plan",
        ticket=None,
        attempt=revision_number or 1,
        input_revisions=_input_hashes(run_dir, stage, manifest),
        output_revisions={stage: manifest["stages"][stage]["sha256"]},
        claimed_result=manifest["stages"][stage]["status"],
        verification=["Structured output validated against the stage contract."],
        unresolved_risks=value.get("blocking_questions", value.get("open_questions", [])),
        artifacts=[relative_path(json_path, repo), relative_path(markdown_path, repo)],
        policy_hashes=contract["policy_hashes"],
    )
    receipt_path = write_handoff_receipt(repo, receipt)
    receipt_reference = relative_path(receipt_path, repo)
    manifest.setdefault("receipts", []).append(receipt_reference)
    manifest["stages"][stage]["receipt"] = receipt_reference
    return value


def _run_stage_agent(
    repo: Path,
    run_dir: Path,
    stage: str,
    manifest: dict,
    planning_agent: str,
    agent_bin: str,
    mock: bool,
    feedback: str | None = None,
) -> dict:
    """Run a planning role and retain a structured failure handoff when it blocks."""
    try:
        return _run_stage_agent_impl(
            repo,
            run_dir,
            stage,
            manifest,
            planning_agent,
            agent_bin,
            mock,
            feedback,
        )
    except Exception as exc:
        contract = role_input(repo, stage)
        record = manifest["stages"][stage]
        record["failure_count"] = int(record.get("failure_count", 0)) + 1
        if not record.get("failure_kind"):
            record["failure_kind"] = (
                "validation" if isinstance(exc, ValueError)
                else "agent" if isinstance(exc, RuntimeError)
                else "internal"
            )
        record["error"] = redact_credentials(str(exc))[:2000]
        history = record.setdefault("failure_history", [])
        history.append({
            "at": now(),
            "kind": record["failure_kind"],
            "error": record["error"],
        })
        del history[:-10]
        record["same_failure_count"] = sum(
            1 for failure in history
            if failure.get("kind") == record["failure_kind"]
            and failure.get("error") == record["error"]
        )
        attempt = len(manifest.get("revisions", [])) + 1 if feedback else 1
        suffix = f"-revision-{attempt}" if feedback else ""
        prompt_path = repo / ".factory/prompts" / f"planner-{manifest['plan_id']}-{stage}{suffix}.md"
        log_path = repo / ".factory/logs" / f"planner-{manifest['plan_id']}-{stage}{suffix}.log"
        receipt = handoff_receipt(
            run_id=manifest["plan_id"],
            role=stage,
            phase="Plan",
            ticket=None,
            attempt=attempt,
            input_revisions=_input_hashes(run_dir, stage, manifest),
            output_revisions={},
            claimed_result="Planning stage failed",
            verification=[f"Planning stopped before a valid handoff ({type(exc).__name__})."],
            unresolved_risks=[record["error"]],
            artifacts=[
                relative_path(path, repo)
                for path in (
                    prompt_path,
                    log_path,
                    repo / record["rejected_artifact"] if record.get("rejected_artifact") else None,
                )
                if path is not None
                if path.is_file()
            ],
            policy_hashes=contract["policy_hashes"],
        )
        receipt_path = write_handoff_receipt(repo, receipt)
        receipt_reference = relative_path(receipt_path, repo)
        manifest.setdefault("receipts", []).append(receipt_reference)
        record.update(status="blocked", receipt=receipt_reference)
        manifest["status"] = "blocked"
        save_manifest(repo, run_dir, manifest)
        raise


def revise_plan(
    repo: Path,
    identifier: str | Path,
    stage: str,
    feedback: str,
    agent_bin: str,
    mock: bool = False,
) -> Path:
    """Regenerate one planning stage from explicit human feedback."""
    stage = REVISION_STAGES.get(stage, stage)
    if stage not in STAGE_INDEX:
        choices = ", ".join(REVISION_STAGES)
        raise ValueError(f"revision stage must be one of: {choices}")
    feedback = feedback.strip()
    if not feedback:
        raise ValueError("revision feedback must not be empty")
    run_dir = resolve_run(repo, identifier)
    manifest = load_manifest(run_dir)
    planning_agent = manifest.get("planning_agent", "codex")
    if mock:
        planning_agent = "mock"
    elif planning_agent == "mock":
        raise ValueError("this planning run uses deterministic fixtures; rerun with --mock")

    _assert_governance_current(repo, run_dir, manifest)
    _assert_project_contract_current(repo, run_dir, manifest)
    if stage != "product_review":
        _assert_product_approval_current(repo, run_dir, manifest)
    _refresh_edited_stage(repo, run_dir, manifest, stage)

    artifact_path, _ = _stage_paths(run_dir, stage)
    title = next(title for name, _, title in STAGES if name == stage)
    stage_record = manifest["stages"][stage]
    revision_source = (
        artifact_path if artifact_path.is_file()
        else _rejected_stage_path(repo, stage_record)
    )
    if revision_source is None:
        raise ValueError(f"{title} artifact is missing")
    before_hash = sha_file(revision_source)
    revision_number = len(manifest.get("revisions", [])) + 1
    revision_dir = run_dir / "revisions"
    revision_dir.mkdir(parents=True, exist_ok=True)
    revision_slug = stage.replace("_", "-")
    previous_path = revision_dir / f"{revision_slug}-{revision_number:02d}-before.json"
    shutil.copyfile(revision_source, previous_path)

    _invalidate_approvals_from(manifest, stage)
    gate = APPROVAL_KEYS.get(stage, "alignment")
    manifest.setdefault("approval_history", []).append({
        "gate": gate,
        "decision": "revision_requested",
        "at": now(),
        "feedback": feedback,
        "artifact_sha256": before_hash,
        "stage": stage,
    })
    manifest.pop("publication", None)
    manifest["status"] = f"revising_{stage}"
    for downstream, _, _ in STAGES[STAGE_INDEX[stage] + 1:]:
        if manifest["stages"][downstream].get("status") not in {"pending", "not_applicable"}:
            manifest["stages"][downstream]["status"] = "stale"
    for filename in ("traceability.json", "alignment-review.md"):
        (run_dir / filename).unlink(missing_ok=True)
    save_manifest(repo, run_dir, manifest)

    value = _run_stage_agent(
        repo,
        run_dir,
        stage,
        manifest,
        planning_agent,
        agent_bin,
        mock,
        feedback=feedback,
    )
    after_hash = sha_file(artifact_path)
    revision = {
        "revision": revision_number,
        "stage": stage,
        "feedback": feedback,
        "before_sha256": before_hash,
        "after_sha256": after_hash,
        "previous_artifact": relative_path(previous_path, repo),
        "revised_artifact": relative_path(artifact_path, repo),
        "agent": "mock" if mock else planning_agent,
        "created_at": now(),
    }
    revision_path = revision_dir / f"{revision_slug}-{revision_number:02d}.json"
    write_json(revision_path, revision)
    manifest.setdefault("revisions", []).append(revision)
    questions = value.get("blocking_questions", value.get("open_questions", []))
    if questions:
        manifest["status"] = "blocked"
    elif stage == "product_review":
        manifest["status"] = "awaiting_product_approval"
    else:
        manifest["status"] = "product_approved"
    save_manifest(repo, run_dir, manifest)
    print(f"{title} revised for {manifest['plan_id']}.")
    print(f"Feedback record: {revision_path}")
    if stage == "product_review":
        print(f"Next: ./factory/factory review product {manifest['plan_id']}")
    else:
        print(f"Next: ./factory/factory continue-plan {manifest['plan_id']}")
    return run_dir


def _blank_stage_state(profile_name: str) -> dict:
    applicable = set(factory_profile(profile_name)["planning_roles"])
    return {
        name: {"status": "pending" if name in applicable else "not_applicable"}
        for name, _, _ in STAGES
    }


def plan_prd(
    repo: Path, prd_path: Path, output: str | None, default_agent: str,
    minimum: int, maximum: int, planning_agent: str, agent_bin: str,
    mock: bool = False,
    profile_name: str = "standard",
    explicit_autonomy: bool = False,
) -> Path:
    repo = repo.resolve()
    prd_path = prd_path.resolve()
    if not prd_path.is_file():
        raise FileNotFoundError(f"PRD not found: {prd_path}")
    if minimum < 1 or maximum < minimum or maximum > 30:
        raise ValueError("ticket limits must satisfy 1 <= min <= max <= 30")
    factory_profile(profile_name)
    prd = prd_path.read_text()
    run_policy = role_input(repo, "product_review")
    project_contract = ProjectContract.load(repo)
    charter = FactoryCharter.load(repo, require_approved=True)
    governance = charter.governance(
        profile_name,
        explicit_autonomy=explicit_autonomy,
    )
    plan_id = sha_text(prd)[:12]
    run_dir = Path(output).resolve() if output else repo / ".factory/plans" / plan_id
    if run_dir.exists() and not run_dir.is_dir():
        raise ValueError("--output must name a planning-run directory")
    run_dir.mkdir(parents=True, exist_ok=True)
    if (run_dir / "manifest.json").is_file():
        print(f"Restarting existing planning run {plan_id}; downstream artifacts will be regenerated.")
    for stage, _, _ in STAGES[1:]:
        for path in _stage_paths(run_dir, stage):
            path.unlink(missing_ok=True)
    for filename in ("traceability.json", "alignment-review.md"):
        (run_dir / filename).unlink(missing_ok=True)
    (run_dir / "source-prd.md").write_text(prd)
    manifest = {
        "plan_version": 2,
        "plan_id": plan_id,
        "source_prd": str(prd_path),
        "prd_sha256": sha_text(prd),
        "project": prd_path.stem,
        "default_ticket_agent": default_agent,
        "planning_agent": "mock" if mock else planning_agent,
        "profile": profile_name,
        "governance": governance,
        "project_contract": {
            "path": str(project_contract.path.relative_to(repo)) if project_contract.path else "detected",
            "sha256": sha_text(project_contract.context()),
        },
        "policy": {
            "version": run_policy["policy_version"],
            "hashes": run_policy["policy_hashes"],
        },
        "ticket_limits": {"minimum": minimum, "maximum": maximum},
        "status": "planning_product_review",
        "created_at": now(),
        "approval_history": [],
        "updated_at": now(),
        "approvals": {
            "product": None,
            "system_architecture": None,
            "program_design": None,
            "alignment": None,
        },
        "receipts": [],
        "stages": _blank_stage_state(profile_name),
    }
    save_manifest(repo, run_dir, manifest)
    product = _run_stage_agent(
        repo, run_dir, "product_review", manifest,
        planning_agent, agent_bin, mock,
    )
    manifest["project"] = product["project"]["name"]
    manifest["status"] = "blocked" if product["blocking_questions"] else "awaiting_product_approval"
    save_manifest(repo, run_dir, manifest)
    write_json(repo / ".factory/plans/latest.json", {"plan_id": plan_id, "run_directory": relative_path(run_dir, repo)})
    print(f"Planning run: {run_dir}")
    print(f"Product review: {run_dir / '01-product-review.md'}")
    print(f"Next: ./factory/factory review product {plan_id}")
    return run_dir


def _refresh_edited_stage(repo: Path, run_dir: Path, manifest: dict, stage: str) -> bool:
    path, markdown = _stage_paths(run_dir, stage)
    if not path.is_file():
        return False
    record = manifest["stages"][stage]
    current_hash = sha_file(path)
    if record.get("sha256") == current_hash:
        return False
    inputs = _stage_inputs(run_dir, stage)
    value = read_json(path)
    _validate_stage(
        stage, value, inputs, manifest.get("profile", "standard"),
        ProjectContract.load(repo),
    )
    record["sha256"] = current_hash
    record["source_hashes"] = _input_hashes(run_dir, stage, manifest)
    record["status"] = "blocked" if value.get("blocking_questions", value.get("open_questions", [])) else "complete"
    record["edited_at"] = now()
    markdown.write_text(_render_stage(stage, value, manifest["plan_id"], path))
    for downstream, _, _ in STAGES[STAGE_INDEX[stage] + 1:]:
        if manifest["stages"][downstream]["status"] not in {"pending", "not_applicable"}:
            manifest["stages"][downstream]["status"] = "stale"
    _invalidate_approvals_from(manifest, stage)
    return True


def _assert_prior_planning_approvals(
    run_dir: Path,
    manifest: dict,
    stage: str,
) -> None:
    required = _required_planning_approvals(manifest)
    for name, _, title in STAGES[1:STAGE_INDEX[stage]]:
        if name in required and not _stage_approval_current(run_dir, manifest, name):
            raise ValueError(f"approve {title} before continuing to {stage.replace('_', ' ')}")


def review(repo: Path, kind: str, identifier: str | Path) -> Path:
    run_dir = resolve_run(repo, identifier)
    manifest = load_manifest(run_dir)
    _assert_governance_current(repo, run_dir, manifest)
    if kind == "product":
        _refresh_edited_stage(repo, run_dir, manifest, "product_review")
        save_manifest(repo, run_dir, manifest)
        path = run_dir / "01-product-review.md"
    elif kind in {"architecture", "system_architecture", "program", "program_design"}:
        stage = REVISION_STAGES.get(kind, kind)
        _assert_product_approval_current(repo, run_dir, manifest)
        applicable = set(factory_profile(manifest.get("profile", "standard"))["planning_roles"])
        if stage not in applicable:
            raise ValueError(f"{stage.replace('_', ' ')} is not part of this Factory Profile")
        if stage not in _required_planning_approvals(manifest):
            raise ValueError(f"the approved Factory Charter does not require {stage.replace('_', ' ')} approval")
        _assert_prior_planning_approvals(run_dir, manifest, stage)
        path, markdown = _stage_paths(run_dir, stage)
        if not path.is_file():
            raise ValueError(f"{stage.replace('_', ' ')} has not been generated")
        _refresh_edited_stage(repo, run_dir, manifest, stage)
        if manifest["stages"][stage].get("source_hashes") != _input_hashes(run_dir, stage, manifest):
            manifest["stages"][stage]["status"] = "stale"
            save_manifest(repo, run_dir, manifest)
            raise ValueError(f"{stage.replace('_', ' ')} inputs changed; rerun continue-plan")
        save_manifest(repo, run_dir, manifest)
        path = markdown
    elif kind == "alignment":
        _assert_product_approval_current(repo, run_dir, manifest)
        applicable = set(factory_profile(manifest.get("profile", "standard"))["planning_roles"])
        upstream_changed = any(
            _refresh_edited_stage(repo, run_dir, manifest, stage)
            for stage in ("system_architecture", "program_design")
            if stage in applicable
        )
        if upstream_changed:
            manifest["approvals"]["alignment"] = None
            manifest["status"] = "stale_alignment"
            save_manifest(repo, run_dir, manifest)
            raise ValueError("an upstream artifact changed; rerun continue-plan before alignment review")
        if _refresh_edited_stage(repo, run_dir, manifest, "vertical_slices"):
            manifest["approvals"]["alignment"] = None
        _refresh_planning_controls(repo, run_dir, manifest)
        _assert_prior_planning_approvals(run_dir, manifest, "vertical_slices")
        path = write_alignment_review(repo, run_dir, manifest)
        save_manifest(repo, run_dir, manifest)
    else:
        raise ValueError("review must be product, architecture, program, or alignment")
    print(path.read_text())
    print(f"Review artifact: {path}")
    return path


def approve_product(repo: Path, identifier: str | Path, assume_yes: bool = False):
    run_dir = resolve_run(repo, identifier)
    manifest = load_manifest(run_dir)
    _assert_governance_current(repo, run_dir, manifest)
    _assert_project_contract_current(repo, run_dir, manifest)
    changed = _refresh_edited_stage(repo, run_dir, manifest, "product_review")
    product = read_json(run_dir / "01-product-review.json")
    validate_product(product)
    if product["blocking_questions"]:
        save_manifest(repo, run_dir, manifest)
        raise ValueError("resolve every product blocking question before approval")
    if not assume_yes:
        try:
            answer = input("Approve this product behavior and scope? Type APPROVE PRODUCT: ")
        except EOFError as exc:
            raise ValueError("interactive product approval required; rerun in a terminal or pass --yes") from exc
        if answer != "APPROVE PRODUCT":
            raise ValueError("product approval cancelled")
    if changed:
        _invalidate_approvals_from(manifest, "product_review")
    approval = {"approved_at": now(), "artifact_sha256": sha_file(run_dir / "01-product-review.json")}
    manifest["approvals"]["product"] = approval
    manifest.setdefault("approval_history", []).append({
        "gate": "product",
        "decision": "approved",
        "at": approval["approved_at"],
        "artifact_sha256": approval["artifact_sha256"],
    })
    manifest["status"] = "product_approved"
    save_manifest(repo, run_dir, manifest)
    print(f"Product review approved for {manifest['plan_id']}.")
    print(f"Next: ./factory/factory continue-plan {manifest['plan_id']}")


def approve_planning_stage(
    repo: Path,
    identifier: str | Path,
    stage: str,
    assume_yes: bool = False,
) -> None:
    """Approve one Charter-selected intermediate expert artifact by exact hash."""
    stage = REVISION_STAGES.get(stage, stage)
    if stage not in {"system_architecture", "program_design"}:
        raise ValueError("planning stage approval must be architecture or program")
    run_dir = resolve_run(repo, identifier)
    manifest = load_manifest(run_dir)
    _assert_governance_current(repo, run_dir, manifest)
    _assert_project_contract_current(repo, run_dir, manifest)
    _assert_product_approval_current(repo, run_dir, manifest)
    if stage not in _required_planning_approvals(manifest):
        raise ValueError(
            f"the approved Factory Charter does not require {stage.replace('_', ' ')} approval"
        )
    applicable = set(factory_profile(manifest.get("profile", "standard"))["planning_roles"])
    if stage not in applicable:
        raise ValueError(f"{stage.replace('_', ' ')} is not part of this Factory Profile")
    _assert_prior_planning_approvals(run_dir, manifest, stage)
    artifact, _ = _stage_paths(run_dir, stage)
    if not artifact.is_file():
        raise ValueError(f"{stage.replace('_', ' ')} has not been generated")
    _refresh_edited_stage(repo, run_dir, manifest, stage)
    record = manifest["stages"][stage]
    if record.get("source_hashes") != _input_hashes(run_dir, stage, manifest):
        record["status"] = "stale"
        save_manifest(repo, run_dir, manifest)
        raise ValueError(f"{stage.replace('_', ' ')} inputs changed; rerun continue-plan")
    value = read_json(artifact)
    questions = value.get("blocking_questions", value.get("open_questions", []))
    if questions:
        save_manifest(repo, run_dir, manifest)
        raise ValueError(f"resolve every {stage.replace('_', ' ')} blocking question before approval")
    title = next(title for name, _, title in STAGES if name == stage)
    if not assume_yes:
        phrase = f"APPROVE {title.upper()}"
        try:
            answer = input(f"Approve this {title}? Type {phrase}: ")
        except EOFError as exc:
            raise ValueError(
                f"interactive {title} approval required; rerun in a terminal or pass --yes"
            ) from exc
        if answer != phrase:
            raise ValueError(f"{title} approval cancelled")
    approval = {"approved_at": now(), "artifact_sha256": sha_file(artifact)}
    _ensure_approvals(manifest)[APPROVAL_KEYS[stage]] = approval
    manifest.setdefault("approval_history", []).append({
        "gate": stage,
        "decision": "approved",
        "at": approval["approved_at"],
        "artifact_sha256": approval["artifact_sha256"],
    })
    manifest["status"] = f"{stage}_approved"
    save_manifest(repo, run_dir, manifest)
    print(f"{title} approved for {manifest['plan_id']}.")
    print(f"Next: ./factory/factory continue-plan {manifest['plan_id']}")


def _assert_product_approval_current(repo: Path, run_dir: Path, manifest: dict):
    if sha_file(run_dir / "source-prd.md") != manifest["prd_sha256"]:
        _invalidate_approvals_from(manifest, "product_review")
        manifest["status"] = "stale_product_review"
        manifest["stages"]["product_review"]["status"] = "stale"
        save_manifest(repo, run_dir, manifest)
        raise ValueError("the copied PRD changed; run `factory plan` again")
    edited = _refresh_edited_stage(repo, run_dir, manifest, "product_review")
    approval = manifest["approvals"].get("product")
    current_hash = sha_file(run_dir / "01-product-review.json")
    if edited or not approval or approval.get("artifact_sha256") != current_hash:
        _invalidate_approvals_from(manifest, "product_review")
        manifest["status"] = "awaiting_product_approval"
        save_manifest(repo, run_dir, manifest)
        raise ValueError("product review changed; review and approve it again")


def _assert_project_contract_current(repo: Path, run_dir: Path, manifest: dict):
    expected = manifest.get("project_contract", {}).get("sha256")
    current = sha_text(ProjectContract.load(repo).context())
    if expected == current:
        return
    _invalidate_approvals_from(manifest, "product_review")
    manifest["status"] = "stale_project_contract"
    save_manifest(repo, run_dir, manifest)
    raise ValueError(
        "the Project Contract or repository inventory changed; run `factory plan` again"
    )


def _assert_governance_current(repo: Path, run_dir: Path, manifest: dict):
    expected = manifest.get("governance")
    if not isinstance(expected, dict):
        manifest["status"] = "stale_factory_charter"
        save_manifest(repo, run_dir, manifest)
        raise ValueError(
            "Planning Run predates Factory Charter governance; run `factory plan` again"
        )
    try:
        charter = FactoryCharter.load(repo, require_approved=True)
        current = charter.governance(
            expected.get("profile", manifest.get("profile", "standard")),
            explicit_autonomy=expected.get("explicit_autonomy") is True,
        )
    except (FactoryCharterError, ValueError) as exc:
        _invalidate_approvals_from(manifest, "product_review")
        manifest["status"] = "stale_factory_charter"
        save_manifest(repo, run_dir, manifest)
        raise ValueError(
            f"Factory Charter is no longer valid for this Planning Run: {exc}. "
            "Review it and run `factory plan` again"
        ) from exc
    if expected == current and manifest.get("profile", "standard") == current["profile"]:
        return
    _invalidate_approvals_from(manifest, "product_review")
    manifest["status"] = "stale_factory_charter"
    save_manifest(repo, run_dir, manifest)
    raise ValueError(
        "Factory Charter changed after planning began; review it and run factory plan again"
    )


def continue_plan(
    repo: Path,
    identifier: str | Path,
    agent_bin: str,
    mock: bool = False,
    planning_agent_override: str | None = None,
) -> Path:
    run_dir = resolve_run(repo, identifier)
    manifest = load_manifest(run_dir)
    planning_agent = manifest.get("planning_agent", "codex")
    if mock and planning_agent != "mock":
        planning_agent = "mock"
    elif planning_agent == "mock" and not mock:
        raise ValueError("this planning run uses deterministic fixtures; rerun with --mock")
    elif planning_agent_override:
        if planning_agent_override not in {"claude", "codex"}:
            raise ValueError("planning retry agent must be claude or codex")
        if planning_agent_override != planning_agent:
            manifest.setdefault("planning_agent_history", []).append({
                "from": planning_agent,
                "to": planning_agent_override,
                "at": now(),
                "reason": "Operator changed the adapter for a blocked planning retry.",
            })
            manifest["planning_agent"] = planning_agent_override
            planning_agent = planning_agent_override
            save_manifest(repo, run_dir, manifest)
    _assert_governance_current(repo, run_dir, manifest)
    _assert_project_contract_current(repo, run_dir, manifest)
    _assert_product_approval_current(repo, run_dir, manifest)
    applicable = set(factory_profile(manifest.get("profile", "standard"))["planning_roles"])
    for stage, _, title in STAGES[1:]:
        if stage not in applicable:
            continue
        edited = _refresh_edited_stage(repo, run_dir, manifest, stage)
        expected_inputs = _input_hashes(run_dir, stage, manifest)
        record = manifest["stages"][stage]
        reusable = record.get("status") in {"complete", "blocked"} and record.get("source_hashes") == expected_inputs
        if not reusable or record.get("status") == "stale":
            manifest["status"] = f"planning_{stage}"
            save_manifest(repo, run_dir, manifest)
            value = _run_stage_agent(
                repo, run_dir, stage, manifest,
                planning_agent, agent_bin, mock,
            )
        else:
            value = read_json(_stage_paths(run_dir, stage)[0])
        questions = value.get("blocking_questions", value.get("open_questions", []))
        if questions:
            manifest["status"] = "blocked"
            save_manifest(repo, run_dir, manifest)
            raise ValueError(f"{title} has blocking questions; edit its JSON and rerun continue-plan")
        if edited:
            manifest["approvals"]["alignment"] = None
        if (
            stage in {"system_architecture", "program_design"}
            and stage in _required_planning_approvals(manifest)
            and not _stage_approval_current(run_dir, manifest, stage)
        ):
            manifest["status"] = f"awaiting_{stage}_approval"
            save_manifest(repo, run_dir, manifest)
            review_name = "architecture" if stage == "system_architecture" else "program"
            print(f"{title} is ready for Charter-required human approval.")
            print(f"Next: ./factory/factory review {review_name} {manifest['plan_id']}")
            return run_dir
    product = read_json(run_dir / "01-product-review.json")
    architecture_path = run_dir / "02-system-architecture.json"
    program_path = run_dir / "03-program-design.json"
    architecture = read_json(architecture_path) if architecture_path.is_file() else None
    program = read_json(program_path) if program_path.is_file() else None
    slices = read_json(run_dir / "04-vertical-slices.json")
    _refresh_planning_controls(repo, run_dir, manifest)
    for stage in ("system_architecture", "program_design"):
        if stage in _required_planning_approvals(manifest) and not _stage_approval_current(
            run_dir, manifest, stage,
        ):
            title = next(title for name, _, title in STAGES if name == stage)
            manifest["status"] = f"awaiting_{stage}_approval"
            save_manifest(repo, run_dir, manifest)
            review_name = "architecture" if stage == "system_architecture" else "program"
            print(f"{title} is ready for path-selected human approval.")
            print(f"Next: ./factory/factory review {review_name} {manifest['plan_id']}")
            return run_dir
    traceability = build_traceability(product, architecture, program, slices)
    validate_traceability(traceability)
    write_json(run_dir / "traceability.json", traceability)
    manifest["approvals"]["alignment"] = None
    manifest["status"] = "awaiting_alignment_approval"
    write_alignment_review(repo, run_dir, manifest)
    save_manifest(repo, run_dir, manifest)
    print(f"Planning package complete: {run_dir}")
    print(f"Next: ./factory/factory review alignment {manifest['plan_id']}")
    return run_dir


def write_alignment_review(repo: Path, run_dir: Path, manifest: dict) -> Path:
    product_path, _ = _stage_paths(run_dir, "product_review")
    architecture_path, _ = _stage_paths(run_dir, "system_architecture")
    program_path, _ = _stage_paths(run_dir, "program_design")
    slices_path, _ = _stage_paths(run_dir, "vertical_slices")
    profile_name = manifest.get("profile", "standard")
    applicable = set(factory_profile(profile_name)["planning_roles"])
    required_paths = [product_path, slices_path]
    if "system_architecture" in applicable:
        required_paths.append(architecture_path)
    if "program_design" in applicable:
        required_paths.append(program_path)
    for path in required_paths:
        if not path.is_file():
            raise ValueError("every profile planning artifact is required for alignment review")
    product = read_json(product_path)
    architecture = read_json(architecture_path) if architecture_path.is_file() else None
    program = read_json(program_path) if program_path.is_file() else None
    slices = read_json(slices_path)
    validate_product(product)
    if architecture is not None:
        validate_architecture(architecture, product)
    if program is not None:
        validate_program(program, product, architecture)
    if "system_architecture" not in applicable:
        validate_lean_vertical_slices(slices, product)
    else:
        validate_vertical_slices(slices, product, architecture, program)
    validate_project_paths(slices, ProjectContract.load(repo))
    traceability = build_traceability(product, architecture, program, slices)
    validate_traceability(traceability)
    write_json(run_dir / "traceability.json", traceability)
    lines = [
        f"# Alignment review — {product['project']['name']}", "", product["project"]["summary"], "",
        f"Plan ID: `{manifest['plan_id']}`", "", f"Factory Profile: **{profile_name.title()}**", "", "## Expert artifacts", "",
        "| Stage | Artifact | Result |", "| --- | --- | --- |",
        f"| Product Review | `01-product-review.md` | {len(product['requirements'])} requirements; approved |",
    ]
    if architecture is not None:
        lines.append(f"| System Architecture | `02-system-architecture.md` | {len(architecture['components'])} components; {len(architecture['contracts'])} contracts |")
    if program is not None:
        lines.append(f"| Program Design | `03-program-design.md` | {len(program['modules'])} modules; {len(program['functions'])} functions |")
    lines += [
        f"| Vertical Slices | `04-vertical-slices.md` | {len(slices['tickets'])} tickets in {len(dependency_waves(slices))} waves |",
        "", "## Traceability", "",
        "| Requirement | Contracts | Program elements | Slices | QA evidence |", "| --- | --- | --- | --- | --- |",
    ]
    for row in traceability["rows"]:
        lines.append(
            f"| {row['requirement_id']}: {row['product_behavior']} | {', '.join(row['architecture_contracts']) or '—'} | "
            f"{', '.join(row['program_elements']) or '—'} | {', '.join(row['slices'])} | {', '.join(row['qa_evidence'])} |"
        )
    lines += ["", "## Dependency waves", ""]
    for index, wave in enumerate(dependency_waves(slices), 1):
        lines.append(f"{index}. {', '.join(wave)}")
    lines += [
        "", "## Human gate", "", "Confirm scope, contracts, code design, ownership, dependencies, and QA evidence. Then publish:", "",
        f"`./factory/factory approve {manifest['plan_id']}`", "",
        "No GitHub issue or implementation agent is created until this command is explicitly confirmed.", "",
    ]
    path = run_dir / "alignment-review.md"
    path.write_text("\n".join(lines))
    return path


def prepare_publication(repo: Path, identifier: str | Path, assume_yes: bool) -> tuple[Path, Path]:
    run_dir = resolve_run(repo, identifier)
    manifest = load_manifest(run_dir)
    _assert_governance_current(repo, run_dir, manifest)
    _assert_project_contract_current(repo, run_dir, manifest)
    _assert_product_approval_current(repo, run_dir, manifest)
    applicable = set(factory_profile(manifest.get("profile", "standard"))["planning_roles"])
    upstream_changed = any(
        _refresh_edited_stage(repo, run_dir, manifest, stage)
        for stage in ("system_architecture", "program_design")
        if stage in applicable
    )
    if upstream_changed:
        manifest["approvals"]["alignment"] = None
        manifest["status"] = "stale_alignment"
        save_manifest(repo, run_dir, manifest)
        raise ValueError("an upstream artifact changed; rerun continue-plan before publication")
    if _refresh_edited_stage(repo, run_dir, manifest, "vertical_slices"):
        manifest["approvals"]["alignment"] = None
    _refresh_planning_controls(repo, run_dir, manifest)
    _assert_prior_planning_approvals(run_dir, manifest, "vertical_slices")
    review_path = write_alignment_review(repo, run_dir, manifest)
    slices_path, _ = _stage_paths(run_dir, "vertical_slices")
    current_hashes = _input_hashes(run_dir, "vertical_slices", manifest)
    if manifest["stages"]["vertical_slices"].get("source_hashes") != current_hashes:
        manifest["stages"]["vertical_slices"]["status"] = "stale"
        manifest["approvals"]["alignment"] = None
        manifest["status"] = "stale_alignment"
        save_manifest(repo, run_dir, manifest)
        raise ValueError("an upstream artifact changed; rerun continue-plan before publication")
    print(review_path.read_text())
    if not assume_yes:
        try:
            answer = input("Approve this alignment and publish tickets? Type APPROVE ALIGNMENT: ")
        except EOFError as exc:
            raise ValueError("interactive alignment approval required; rerun in a terminal or pass --yes") from exc
        if answer != "APPROVE ALIGNMENT":
            raise ValueError("alignment approval cancelled; no GitHub issues were changed")
    manifest["approvals"]["alignment"] = {
        "approved_at": now(),
        "artifact_hashes": {
            name: sha_file(_stage_paths(run_dir, name)[0])
            for name, _, _ in STAGES
            if name in applicable
        },
        "traceability_sha256": sha_file(run_dir / "traceability.json"),
    }
    manifest.setdefault("approval_history", []).append({
        "gate": "alignment",
        "decision": "approved",
        "at": manifest["approvals"]["alignment"]["approved_at"],
        "artifact_hashes": manifest["approvals"]["alignment"]["artifact_hashes"],
        "traceability_sha256": manifest["approvals"]["alignment"]["traceability_sha256"],
    })
    manifest["status"] = "alignment_approved"
    save_manifest(repo, run_dir, manifest)
    return slices_path, run_dir


def approve_rehearsal(
    repo: Path,
    identifier: str | Path,
    assume_yes: bool = False,
    scenario: str = "recipe-rebrand",
) -> Path:
    """Approve alignment and turn the reviewed slices into local rehearsal tickets."""
    slices_path, run_dir = prepare_publication(repo, identifier, assume_yes)
    slices = read_json(slices_path)
    template_path = repo / "factory/scenarios" / scenario / "tickets.json"
    if not template_path.is_file():
        template_path = Path(__file__).parent / "scenarios" / scenario / "tickets.json"
    if not template_path.is_file():
        raise FileNotFoundError(f"Rehearsal scenario not found: {scenario}")
    templates = read_json(template_path)
    if len(templates) < len(slices["tickets"]):
        raise ValueError(
            f"Rehearsal scenario {scenario} supports {len(templates)} tickets, "
            f"but the approved plan contains {len(slices['tickets'])}"
        )
    numbers = {
        ticket["key"]: index
        for index, ticket in enumerate(slices["tickets"], 1)
    }
    manifest = load_manifest(run_dir)
    governance = manifest.get("governance")
    materialized = []
    for index, ticket in enumerate(slices["tickets"], 1):
        executable = {**ticket, "agent": "mock"}
        materialized.append({
            "number": index,
            "title": ticket["title"],
            "labels": ["agent-ready"],
            "body": issue_body(
                executable, numbers, slices["plan_id"], governance,
            ),
            "dependencies": [numbers[key] for key in ticket["dependencies"]],
            "planned_agent": ticket["agent"],
            "mock_action": templates[index - 1].get("mock_action", ""),
            "simulate_merge_conflict": templates[index - 1].get("simulate_merge_conflict", False),
        })
    output = repo / ".factory/rehearsal" / slices["plan_id"] / "tickets.json"
    write_json(output, materialized)
    manifest["rehearsal"] = {
        "approved_at": now(),
        "scenario": scenario,
        "tickets_path": relative_path(output, repo),
        "vertical_slices_sha256": sha_file(slices_path),
    }
    save_manifest(repo, run_dir, manifest)
    return output


def mark_published(repo: Path, run_dir: Path, url: str):
    manifest = load_manifest(run_dir)
    manifest["status"] = "published"
    manifest["publication"] = {"published_at": now(), "url": url}
    save_manifest(repo, run_dir, manifest)
