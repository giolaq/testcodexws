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
from datetime import datetime, timezone
from pathlib import Path

from planner import dependency_waves, render_review, validate_plan


PROMPT_VERSION = "2.0"
STAGES = (
    ("product_review", "01-product-review", "Product Review"),
    ("system_architecture", "02-system-architecture", "System Architecture"),
    ("program_design", "03-program-design", "Program Design"),
    ("vertical_slices", "04-vertical-slices", "Vertical Slices"),
)
STAGE_INDEX = {name: index for index, (name, _, _) in enumerate(STAGES)}
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


def build_traceability(product: dict, architecture: dict, program: dict, slices: dict) -> dict:
    rows = []
    for requirement in product["requirements"]:
        identifier = requirement["id"]
        contracts = [item["id"] for item in architecture["contracts"] if identifier in item["requirements"]]
        elements = [
            item["id"]
            for collection in ("types", "functions", "call_flows", "test_seams")
            for item in program[collection]
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


def stage_prompt(stage: str, prd: str, inputs: dict[str, dict], default_agent: str, minimum: int, maximum: int) -> str:
    shared = """Use the repository only as implementation context; product scope comes from the PRD and approved upstream artifacts. Preserve stable IDs exactly.
Inspect the current codebase when technical or file-level detail is required. Do not invent scope. Put decisions that require a human in blocking_questions.
Return only JSON matching the supplied schema. This artifact is an auditable contract for the next expert."""
    roles = {
        "product_review": """You are the Product Review expert. Clarify the problem, users, observable behavior, scope, journeys, success evidence, mockup needs, assumptions, and blocking questions. Give requirements stable IDs R1, R2, and so on. Cite the PRD section or phrase in each requirement's source. Do not design architecture or create implementation tickets.""",
        "system_architecture": """You are the System Architecture expert. Inspect the existing repository and, using the approved product review, define components, ownership boundaries, data models, explicit component contracts, architectural decisions, constraints, and risks. Map every item to product requirement IDs. Every requirement must have an owning component. Do not assign tickets or write low-level implementation code.""",
        "program_design": """You are the Program Design expert. Inspect the existing code and turn the approved architecture into a concrete code design: modules and paths, types, function signatures, call relationships, error behavior, call flows, and test seams. Use stable IDs (MOD-, TYPE-, FN-, FLOW-, TEST-), reference contracts and requirements, and prefix calls outside this design with external:. Do not create tickets.""",
        "vertical_slices": f"""You are the Vertical Slices expert. Divide the aligned product, architecture, and program design into {minimum}-{maximum} small end-to-end tickets. Each ticket must deliver an observable vertical outcome, own explicit files, name QA evidence, and map requirement, contract, and program-element IDs. Every program element and requirement must have an owner. Overlapping file ownership is allowed only when one ticket depends on the other. Keep the dependency graph acyclic and maximize safe parallel work. Default agent to {default_agent}.""",
    }
    context = "\n\n".join(
        f"## Approved {name.replace('_', ' ').title()}\n```json\n{json.dumps(value, indent=2)}\n```"
        for name, value in inputs.items()
    )
    return f"""{roles[stage]}

{shared}

## Source PRD

{prd}

{context}
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
    return read_json(run_dir / "manifest.json")


def save_manifest(repo: Path, run_dir: Path, manifest: dict):
    manifest["updated_at"] = now()
    write_json(run_dir / "manifest.json", manifest)
    write_dashboard_state(repo, run_dir, manifest)


def write_dashboard_state(repo: Path, run_dir: Path, manifest: dict):
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
        })
    state = {
        "plan_id": manifest["plan_id"],
        "project": manifest.get("project", "Planning run"),
        "status": manifest["status"],
        "updated_at": manifest["updated_at"],
        "run_directory": relative_path(run_dir, repo),
        "approvals": manifest["approvals"],
        "stages": stages,
        "alignment_review": relative_path(run_dir / "alignment-review.md", repo) if (run_dir / "alignment-review.md").is_file() else "",
        "traceability": relative_path(run_dir / "traceability.json", repo) if (run_dir / "traceability.json").is_file() else "",
    }
    write_json(repo / ".factory/planning-state.json", state)


def _stage_inputs(run_dir: Path, stage: str) -> dict[str, dict]:
    result = {}
    for current, _, _ in STAGES:
        if current == stage:
            break
        path, _ = _stage_paths(run_dir, current)
        result[current] = read_json(path)
    return result


def _input_hashes(run_dir: Path, stage: str, manifest: dict) -> dict[str, str]:
    hashes = {"source_prd": sha_file(run_dir / "source-prd.md")}
    for current, _, _ in STAGES:
        if current == stage:
            break
        path, _ = _stage_paths(run_dir, current)
        hashes[current] = sha_file(path)
    return hashes


def _validate_stage(stage: str, value: dict, inputs: dict[str, dict]):
    if stage == "product_review":
        validate_product(value)
    elif stage == "system_architecture":
        validate_architecture(value, inputs["product_review"])
    elif stage == "program_design":
        validate_program(value, inputs["product_review"], inputs["system_architecture"])
    else:
        validate_vertical_slices(value, inputs["product_review"], inputs["system_architecture"], inputs["program_design"])


def _fixture_path(repo: Path, stage: str) -> Path:
    filename = next(filename for name, filename, _ in STAGES if name == stage)
    return repo / "factory/scenarios/recipe-rebrand/planning" / f"{filename}.json"


def _run_stage_agent(
    repo: Path, run_dir: Path, stage: str, manifest: dict,
    planning_agent: str, agent_bin: str, mock: bool,
) -> dict:
    json_path, _ = _stage_paths(run_dir, stage)
    raw = run_dir / f".{stage}-raw.json"
    inputs = _stage_inputs(run_dir, stage)
    prompt = stage_prompt(
        stage, (run_dir / "source-prd.md").read_text(), inputs,
        manifest["default_ticket_agent"], manifest["ticket_limits"]["minimum"], manifest["ticket_limits"]["maximum"],
    )
    prompt_path = repo / ".factory/prompts" / f"planner-{manifest['plan_id']}-{stage}.md"
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text(prompt)
    log = repo / ".factory/logs" / f"planner-{manifest['plan_id']}-{stage}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    if mock:
        fixture = _fixture_path(repo, stage)
        if not fixture.is_file():
            raise FileNotFoundError(f"mock planning fixture not found: {fixture}")
        shutil.copyfile(fixture, raw)
        log.write_text(f"Mock {stage} expert copied {fixture}\n")
    else:
        schema = repo / "factory/planning_schemas" / f"{stage}.json"
        if planning_agent == "codex":
            command = [
                agent_bin, "exec", "--sandbox", "read-only", "--ephemeral",
                "--ignore-user-config", "--ignore-rules", "--output-schema", str(schema),
                "-o", str(raw), "-",
            ]
            result = subprocess.run(command, cwd=repo, input=prompt, text=True, capture_output=True)
        elif planning_agent == "claude":
            command = [
                agent_bin, "-p", "--permission-mode", "plan",
                "--tools", "Read,Glob,Grep", "--no-session-persistence",
                "--output-format", "json", "--json-schema", schema.read_text(),
            ]
            result = subprocess.run(command, cwd=repo, input=prompt, text=True, capture_output=True)
            if result.returncode == 0:
                try:
                    envelope = json.loads(result.stdout)
                    structured = envelope["structured_output"]
                    write_json(raw, structured)
                except (json.JSONDecodeError, KeyError, TypeError) as exc:
                    result = subprocess.CompletedProcess(
                        result.args, 1, result.stdout,
                        result.stderr + f"\nClaude returned no valid structured_output: {exc}\n",
                    )
        else:
            raise ValueError(f"unsupported planning agent: {planning_agent}")
        log.write_text(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError(f"{stage.replace('_', ' ')} expert failed; see {log}")
    try:
        value = read_json(raw)
    finally:
        raw.unlink(missing_ok=True)
    if stage == "vertical_slices":
        value.update({
            "plan_version": 2,
            "plan_id": manifest["plan_id"],
            "source_prd": str(run_dir / "source-prd.md"),
            "created_at": now(),
            "planning_agent": planning_agent if not mock else "mock",
        })
    _validate_stage(stage, value, inputs)
    if stage == "vertical_slices":
        count = len(value["tickets"])
        minimum = manifest["ticket_limits"]["minimum"]
        maximum = manifest["ticket_limits"]["maximum"]
        if not minimum <= count <= maximum:
            raise ValueError(f"vertical slices expert returned {count} tickets; expected {minimum}-{maximum}")
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
    return value


def _blank_stage_state() -> dict:
    return {name: {"status": "pending"} for name, _, _ in STAGES}


def plan_prd(
    repo: Path, prd_path: Path, output: str | None, default_agent: str,
    minimum: int, maximum: int, planning_agent: str, agent_bin: str,
    mock: bool = False,
) -> Path:
    prd_path = prd_path.resolve()
    if not prd_path.is_file():
        raise FileNotFoundError(f"PRD not found: {prd_path}")
    if minimum < 1 or maximum < minimum or maximum > 30:
        raise ValueError("ticket limits must satisfy 1 <= min <= max <= 30")
    prd = prd_path.read_text()
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
        "ticket_limits": {"minimum": minimum, "maximum": maximum},
        "status": "planning_product_review",
        "created_at": now(),
        "updated_at": now(),
        "approvals": {"product": None, "alignment": None},
        "stages": _blank_stage_state(),
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
    _validate_stage(stage, value, inputs)
    record["sha256"] = current_hash
    record["source_hashes"] = _input_hashes(run_dir, stage, manifest)
    record["status"] = "blocked" if value.get("blocking_questions", value.get("open_questions", [])) else "complete"
    record["edited_at"] = now()
    markdown.write_text(_render_stage(stage, value, manifest["plan_id"], path))
    for downstream, _, _ in STAGES[STAGE_INDEX[stage] + 1:]:
        if manifest["stages"][downstream]["status"] != "pending":
            manifest["stages"][downstream]["status"] = "stale"
    return True


def review(repo: Path, kind: str, identifier: str | Path) -> Path:
    run_dir = resolve_run(repo, identifier)
    manifest = load_manifest(run_dir)
    if kind == "product":
        _refresh_edited_stage(repo, run_dir, manifest, "product_review")
        save_manifest(repo, run_dir, manifest)
        path = run_dir / "01-product-review.md"
    elif kind == "alignment":
        _assert_product_approval_current(repo, run_dir, manifest)
        upstream_changed = any(
            _refresh_edited_stage(repo, run_dir, manifest, stage)
            for stage in ("system_architecture", "program_design")
        )
        if upstream_changed:
            manifest["approvals"]["alignment"] = None
            manifest["status"] = "stale_alignment"
            save_manifest(repo, run_dir, manifest)
            raise ValueError("an upstream artifact changed; rerun continue-plan before alignment review")
        if _refresh_edited_stage(repo, run_dir, manifest, "vertical_slices"):
            manifest["approvals"]["alignment"] = None
        path = write_alignment_review(repo, run_dir, manifest)
        save_manifest(repo, run_dir, manifest)
    else:
        raise ValueError("review must be product or alignment")
    print(path.read_text())
    print(f"Review artifact: {path}")
    return path


def approve_product(repo: Path, identifier: str | Path, assume_yes: bool = False):
    run_dir = resolve_run(repo, identifier)
    manifest = load_manifest(run_dir)
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
        manifest["approvals"]["alignment"] = None
    manifest["approvals"]["product"] = {"approved_at": now(), "artifact_sha256": sha_file(run_dir / "01-product-review.json")}
    manifest["status"] = "product_approved"
    save_manifest(repo, run_dir, manifest)
    print(f"Product review approved for {manifest['plan_id']}.")
    print(f"Next: ./factory/factory continue-plan {manifest['plan_id']}")


def _assert_product_approval_current(repo: Path, run_dir: Path, manifest: dict):
    if sha_file(run_dir / "source-prd.md") != manifest["prd_sha256"]:
        manifest["approvals"] = {"product": None, "alignment": None}
        manifest["status"] = "stale_product_review"
        manifest["stages"]["product_review"]["status"] = "stale"
        save_manifest(repo, run_dir, manifest)
        raise ValueError("the copied PRD changed; run `factory plan` again")
    edited = _refresh_edited_stage(repo, run_dir, manifest, "product_review")
    approval = manifest["approvals"].get("product")
    current_hash = sha_file(run_dir / "01-product-review.json")
    if edited or not approval or approval.get("artifact_sha256") != current_hash:
        manifest["approvals"]["product"] = None
        manifest["approvals"]["alignment"] = None
        manifest["status"] = "awaiting_product_approval"
        save_manifest(repo, run_dir, manifest)
        raise ValueError("product review changed; review and approve it again")


def continue_plan(repo: Path, identifier: str | Path, agent_bin: str, mock: bool = False) -> Path:
    run_dir = resolve_run(repo, identifier)
    manifest = load_manifest(run_dir)
    planning_agent = manifest.get("planning_agent", "codex")
    if mock and planning_agent != "mock":
        planning_agent = "mock"
    elif planning_agent == "mock" and not mock:
        raise ValueError("this planning run uses deterministic fixtures; rerun with --mock")
    _assert_product_approval_current(repo, run_dir, manifest)
    for stage, _, title in STAGES[1:]:
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
    product = read_json(run_dir / "01-product-review.json")
    architecture = read_json(run_dir / "02-system-architecture.json")
    program = read_json(run_dir / "03-program-design.json")
    slices = read_json(run_dir / "04-vertical-slices.json")
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
    for path in (product_path, architecture_path, program_path, slices_path):
        if not path.is_file():
            raise ValueError("all four expert artifacts are required for alignment review")
    product, architecture, program, slices = map(read_json, (product_path, architecture_path, program_path, slices_path))
    validate_product(product)
    validate_architecture(architecture, product)
    validate_program(program, product, architecture)
    validate_vertical_slices(slices, product, architecture, program)
    traceability = build_traceability(product, architecture, program, slices)
    validate_traceability(traceability)
    write_json(run_dir / "traceability.json", traceability)
    lines = [
        f"# Alignment review — {product['project']['name']}", "", product["project"]["summary"], "",
        f"Plan ID: `{manifest['plan_id']}`", "", "## Expert artifacts", "",
        "| Stage | Artifact | Result |", "| --- | --- | --- |",
        f"| Product Review | `01-product-review.md` | {len(product['requirements'])} requirements; approved |",
        f"| System Architecture | `02-system-architecture.md` | {len(architecture['components'])} components; {len(architecture['contracts'])} contracts |",
        f"| Program Design | `03-program-design.md` | {len(program['modules'])} modules; {len(program['functions'])} functions |",
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
    _assert_product_approval_current(repo, run_dir, manifest)
    upstream_changed = any(
        _refresh_edited_stage(repo, run_dir, manifest, stage)
        for stage in ("system_architecture", "program_design")
    )
    if upstream_changed:
        manifest["approvals"]["alignment"] = None
        manifest["status"] = "stale_alignment"
        save_manifest(repo, run_dir, manifest)
        raise ValueError("an upstream artifact changed; rerun continue-plan before publication")
    if _refresh_edited_stage(repo, run_dir, manifest, "vertical_slices"):
        manifest["approvals"]["alignment"] = None
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
        "artifact_hashes": {name: sha_file(_stage_paths(run_dir, name)[0]) for name, _, _ in STAGES},
        "traceability_sha256": sha_file(run_dir / "traceability.json"),
    }
    manifest["status"] = "alignment_approved"
    save_manifest(repo, run_dir, manifest)
    return slices_path, run_dir


def mark_published(repo: Path, run_dir: Path, url: str):
    manifest = load_manifest(run_dir)
    manifest["status"] = "published"
    manifest["publication"] = {"published_at": now(), "url": url}
    save_manifest(repo, run_dir, manifest)
