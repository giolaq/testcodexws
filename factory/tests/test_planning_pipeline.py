import json
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1]))

from planning_pipeline import (
    approve_planning_stage,
    approve_rehearsal,
    approve_product,
    continue_plan,
    load_manifest,
    plan_prd,
    prepare_publication,
    revise_plan,
    review,
    sha_text,
    stage_prompt,
    validate_vertical_slices,
    validate_project_paths,
)
from factory_charter import FactoryCharter
from project_contract import ProjectContract


FIXTURES = Path(__file__).parents[1] / "scenarios" / "recipe-rebrand" / "planning"
SCHEMAS = Path(__file__).parents[1] / "planning_schemas"


class PlanningPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.repo = Path(self.temporary.name)
        destination = self.repo / "factory/scenarios/recipe-rebrand/planning"
        destination.parent.mkdir(parents=True)
        shutil.copytree(FIXTURES, destination)
        shutil.copytree(SCHEMAS, self.repo / "factory/planning_schemas")
        self.prd = self.repo / "PRD.md"
        self.prd.write_text("# TableStory\n\nConvert the demo into the approved recipe product.\n")
        charter = FactoryCharter.draft(self.repo, ProjectContract.detect(self.repo))
        charter.write()
        charter.approve()

    def tearDown(self):
        self.temporary.cleanup()

    def start(self) -> Path:
        return plan_prd(
            self.repo, self.prd, None, "codex", 3, 12,
            "mock", "mock", mock=True,
        )

    def finish(self) -> Path:
        run = self.start()
        approve_product(self.repo, run.name, assume_yes=True)
        continue_plan(self.repo, run.name, "codex", mock=True)
        return run

    def test_plan_stops_at_product_approval_gate(self):
        run = self.start()
        manifest = load_manifest(run)
        self.assertEqual(manifest["status"], "awaiting_product_approval")
        self.assertEqual(manifest["stages"]["product_review"]["status"], "complete")
        self.assertEqual(manifest["stages"]["system_architecture"]["status"], "pending")
        self.assertIsNone(manifest["approvals"]["product"])

    def test_project_contract_change_invalidates_planning_before_approval(self):
        ProjectContract.detect(self.repo).write()
        run = self.start()
        contract = self.repo / "factory.project.toml"
        contract.write_text(contract.read_text().replace(
            f'name = "{self.repo.name}"', 'name = "changed-project"',
        ))

        with self.assertRaisesRegex(ValueError, "Project Contract.*changed"):
            approve_product(self.repo, run.name, assume_yes=True)

        self.assertEqual(load_manifest(run)["status"], "stale_project_contract")

    def test_factory_charter_change_invalidates_planning_before_approval(self):
        run = self.start()
        charter = self.repo / "factory.charter.toml"
        charter.write_text(charter.read_text().replace(
            "max_diff_lines = 800", "max_diff_lines = 801",
        ))
        FactoryCharter.load(self.repo).approve()

        with self.assertRaisesRegex(ValueError, "Factory Charter changed.*plan again"):
            approve_product(self.repo, run.name, assume_yes=True)

        self.assertEqual(load_manifest(run)["status"], "stale_factory_charter")

    def test_vertical_slice_cannot_claim_a_protected_project_path(self):
        project = ProjectContract.detect(self.repo)
        slices = {"tickets": [{
            "key": "T1", "file_ownership": ["factory.project.toml"],
        }]}

        with self.assertRaisesRegex(ValueError, "protected Project Contract path"):
            validate_project_paths(slices, project)

    def test_planning_stage_emits_dashboard_readable_handoff_receipt(self):
        run = self.start()
        manifest = load_manifest(run)
        self.assertEqual(len(manifest["receipts"]), 1)
        receipt_path = self.repo / manifest["receipts"][0]
        receipt = json.loads(receipt_path.read_text())
        self.assertEqual(
            set(receipt),
            {
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
                "evidence",
                "timestamp",
            },
        )
        self.assertEqual(receipt["run_id"], manifest["plan_id"])
        self.assertEqual(receipt["role"], "product_review")
        self.assertEqual(receipt["phase"], "Plan")
        self.assertIsNone(receipt["ticket"])
        self.assertEqual(receipt["output_revisions"]["product_review"], manifest["stages"]["product_review"]["sha256"])
        self.assertEqual(set(receipt["policy_hashes"]), {"engineering", "workflow", "repository"})
        dashboard = json.loads((self.repo / ".factory/planning-state.json").read_text())
        self.assertEqual(dashboard["receipts"], manifest["receipts"])
        self.assertEqual(dashboard["stages"][0]["receipt"], manifest["receipts"][0])
        prompt = (self.repo / manifest["stages"]["product_review"]["prompt"]).read_text()
        self.assertIn("## Approved Factory Charter", prompt)
        self.assertIn(manifest["governance"]["charter_sha256"], prompt)

    def test_planning_validation_failure_emits_a_blocking_receipt(self):
        with patch("planning_pipeline._validate_stage", side_effect=ValueError("invalid artifact")):
            with self.assertRaisesRegex(ValueError, "invalid artifact"):
                plan_prd(
                    self.repo, self.prd, None, "mock", 3, 12,
                    "mock", "mock", True, "standard",
                )

        plan_id = sha_text(self.prd.read_text())[:12]
        manifest = load_manifest(self.repo / ".factory/plans" / plan_id)
        self.assertEqual(manifest["stages"]["product_review"]["status"], "blocked")
        self.assertEqual(len(manifest["receipts"]), 1)
        receipt = json.loads((self.repo / manifest["receipts"][0]).read_text())
        self.assertEqual(receipt["claimed_result"], "Planning stage failed")
        self.assertTrue(receipt["unresolved_risks"])

    def test_retry_preserves_rejected_slices_and_sends_validator_feedback_to_expert(self):
        product = json.loads((FIXTURES / "01-product-review.json").read_text())
        architecture = json.loads((FIXTURES / "02-system-architecture.json").read_text())
        program = json.loads((FIXTURES / "03-program-design.json").read_text())
        rejected_slices = json.loads((FIXTURES / "04-vertical-slices.json").read_text())
        corrected_slices = json.loads((FIXTURES / "04-vertical-slices.json").read_text())
        rejected_slices["tickets"][0]["contract_ids"].append("C1")
        success = subprocess.CompletedProcess(["claude"], 0, "", "")

        with patch(
            "planning_pipeline._run_claude_agent",
            side_effect=[
                (success, product),
                (success, architecture),
                (success, program),
                (success, rejected_slices),
                (success, corrected_slices),
            ],
        ) as invoked:
            run = plan_prd(
                self.repo, self.prd, None, "codex", 3, 12,
                "claude", "claude", mock=False,
            )
            approve_product(self.repo, run.name, assume_yes=True)

            with self.assertRaisesRegex(ValueError, "T1 references unknown IDs: C1"):
                continue_plan(self.repo, run.name, "claude")

            blocked = load_manifest(run)
            stage = blocked["stages"]["vertical_slices"]
            self.assertEqual(stage["status"], "blocked")
            self.assertEqual(stage["failure_kind"], "validation")
            self.assertEqual(stage["error"], "T1 references unknown IDs: C1")
            rejected_path = self.repo / stage["rejected_artifact"]
            self.assertTrue(rejected_path.is_file())
            self.assertIn("C1", rejected_path.read_text())
            dashboard = json.loads((self.repo / ".factory/planning-state.json").read_text())
            dashboard_stage = next(item for item in dashboard["stages"] if item["id"] == "vertical_slices")
            self.assertEqual(dashboard_stage["error"], "T1 references unknown IDs: C1")
            self.assertEqual(dashboard_stage["failure_kind"], "validation")
            self.assertEqual(dashboard_stage["rejected_artifact"], stage["rejected_artifact"])

            continue_plan(self.repo, run.name, "claude")

        retry_prompt = invoked.call_args_list[-1].args[2]
        self.assertIn("## Previous validation failure", retry_prompt)
        self.assertIn("T1 references unknown IDs: C1", retry_prompt)
        self.assertIn("C1", retry_prompt)
        self.assertIn("Allowed contract IDs: CT1, CT2, CT3, CT4", retry_prompt)
        self.assertIn("Allowed program-element IDs:", retry_prompt)
        completed = load_manifest(run)
        self.assertEqual(completed["status"], "awaiting_alignment_approval")
        self.assertEqual(completed["stages"]["vertical_slices"]["status"], "complete")

    def test_ticket_count_failure_preserves_rejected_artifact_for_correction(self):
        product = json.loads((FIXTURES / "01-product-review.json").read_text())
        architecture = json.loads((FIXTURES / "02-system-architecture.json").read_text())
        program = json.loads((FIXTURES / "03-program-design.json").read_text())
        too_short = json.loads((FIXTURES / "04-vertical-slices.json").read_text())
        too_short["tickets"] = too_short["tickets"][:1]
        success = subprocess.CompletedProcess(["claude"], 0, "", "")

        with patch("planning_pipeline._validate_stage"):
            with patch(
                "planning_pipeline._run_claude_agent",
                side_effect=[
                    (success, product),
                    (success, architecture),
                    (success, program),
                    (success, too_short),
                ],
            ):
                run = plan_prd(
                    self.repo, self.prd, None, "codex", 3, 12,
                    "claude", "claude", mock=False,
                )
                approve_product(self.repo, run.name, assume_yes=True)

                with self.assertRaisesRegex(ValueError, "returned 1 tickets; expected 3-12"):
                    continue_plan(self.repo, run.name, "claude")

        stage = load_manifest(run)["stages"]["vertical_slices"]
        self.assertEqual(stage["failure_kind"], "validation")
        self.assertEqual(stage["validation_error"], "vertical slices expert returned 1 tickets; expected 3-12")
        rejected = self.repo / stage["rejected_artifact"]
        self.assertTrue(rejected.is_file())
        self.assertEqual(len(json.loads(rejected.read_text())["tickets"]), 1)

    def test_operator_can_revise_a_rejected_artifact_when_retry_repeats_the_error(self):
        product = json.loads((FIXTURES / "01-product-review.json").read_text())
        architecture = json.loads((FIXTURES / "02-system-architecture.json").read_text())
        program = json.loads((FIXTURES / "03-program-design.json").read_text())
        rejected_slices = json.loads((FIXTURES / "04-vertical-slices.json").read_text())
        corrected_slices = json.loads((FIXTURES / "04-vertical-slices.json").read_text())
        rejected_slices["tickets"][0]["file_ownership"].append("factory.project.toml")
        success = subprocess.CompletedProcess(["claude"], 0, "", "")
        correction = (
            "Remove factory.project.toml from every ticket's file ownership. "
            "Treat repository-level gate registration as an external prerequisite."
        )

        with patch(
            "planning_pipeline._run_claude_agent",
            side_effect=[
                (success, product),
                (success, architecture),
                (success, program),
                (success, rejected_slices),
                (success, corrected_slices),
            ],
        ) as invoked:
            run = plan_prd(
                self.repo, self.prd, None, "codex", 3, 12,
                "claude", "claude", mock=False,
            )
            approve_product(self.repo, run.name, assume_yes=True)

            with self.assertRaisesRegex(ValueError, "protected Project Contract path"):
                continue_plan(self.repo, run.name, "claude")

            blocked = load_manifest(run)
            rejected_path = self.repo / blocked["stages"]["vertical_slices"]["rejected_artifact"]
            self.assertTrue(rejected_path.is_file())
            self.assertFalse((run / "04-vertical-slices.json").is_file())

            revise_plan(
                self.repo,
                run.name,
                "slices",
                correction,
                "claude",
                mock=False,
            )
            continue_plan(self.repo, run.name, "claude")

        revision_prompt = invoked.call_args_list[-1].args[2]
        self.assertIn("## Previous validation failure", revision_prompt)
        self.assertIn("## Current artifact", revision_prompt)
        self.assertIn("factory.project.toml", revision_prompt)
        self.assertIn(correction, revision_prompt)
        completed = load_manifest(run)
        self.assertEqual(completed["status"], "awaiting_alignment_approval")
        self.assertEqual(completed["stages"]["vertical_slices"]["status"], "complete")

    def test_claude_planner_uses_structured_output_and_records_agent(self):
        product = json.loads((FIXTURES / "01-product-review.json").read_text())
        response = subprocess.CompletedProcess(
            ["claude"], 0, "", "",
        )
        with patch("planning_pipeline._run_claude_agent", return_value=(response, product)) as invoked:
            run = plan_prd(
                self.repo, self.prd, None, "claude", 3, 12,
                "claude", "claude", mock=False,
            )
        command = invoked.call_args.args[0]
        self.assertIn("--json-schema", command)
        self.assertIn("stream-json", command)
        claude_schema = json.loads(command[command.index("--json-schema") + 1])
        self.assertNotIn("$schema", claude_schema)
        self.assertEqual(claude_schema["type"], "object")
        self.assertTrue(
            invoked.call_args.args[2].startswith("You are the Product Review expert."),
        )
        manifest = load_manifest(run)
        self.assertEqual(manifest["planning_agent"], "claude")
        self.assertEqual(manifest["stages"]["product_review"]["agent"], "claude")

    def test_planning_schemas_expose_runtime_identifier_rules(self):
        id_pattern = "^[A-Z][A-Z0-9_-]{0,31}$"
        ticket_pattern = "^[A-Z][A-Z0-9_-]{0,15}$"

        def identifier_properties(value):
            if isinstance(value, dict):
                properties = value.get("properties", {})
                for name in ("id", "key"):
                    if name in properties:
                        yield name, properties[name]
                for child in value.values():
                    yield from identifier_properties(child)
            elif isinstance(value, list):
                for child in value:
                    yield from identifier_properties(child)

        for schema_path in sorted(SCHEMAS.glob("*.json")):
            schema = json.loads(schema_path.read_text())
            for name, property_schema in identifier_properties(schema):
                with self.subTest(schema=schema_path.name, property=name):
                    expected = ticket_pattern if name == "key" else id_pattern
                    self.assertEqual(property_schema.get("pattern"), expected)

    def test_program_design_prompt_disambiguates_module_components(self):
        prompt = stage_prompt(
            "program_design", "# PRD", {}, "claude", 3, 12, "standard",
        )

        self.assertIn(
            "modules[].components must contain only component IDs copied from System Architecture",
            prompt,
        )
        self.assertIn("Never put function IDs, type IDs, constants, or prose in modules[].components", prompt)

    def test_claude_planner_streams_progress_before_the_agent_exits(self):
        product = json.loads((FIXTURES / "01-product-review.json").read_text())
        fake_claude = self.repo / "fake-claude"
        fake_claude.write_text(
            f"#!{sys.executable}\n"
            "import json\n"
            "from pathlib import Path\n"
            "import sys\n"
            "import time\n"
            "repo = Path.cwd()\n"
            "streaming = 'stream-json' in sys.argv\n"
            "if streaming:\n"
            "    print(json.dumps({'type': 'system', 'subtype': 'init'}), flush=True)\n"
            "(repo / '.factory/fake-claude-started').write_text(json.dumps(sys.argv))\n"
            "release = repo / '.factory/release-fake-claude'\n"
            "for _ in range(500):\n"
            "    if release.exists():\n"
            "        break\n"
            "    time.sleep(0.01)\n"
            "else:\n"
            "    raise SystemExit(3)\n"
            f"payload = {{'structured_output': {product!r}}}\n"
            "if streaming:\n"
            "    payload.update({'type': 'result', 'subtype': 'success', 'is_error': False})\n"
            "print(json.dumps(payload), flush=True)\n"
        )
        fake_claude.chmod(0o755)
        failures = []

        def run_planner():
            try:
                plan_prd(
                    self.repo, self.prd, None, "claude", 3, 12,
                    "claude", str(fake_claude), mock=False,
                )
            except BaseException as exc:  # propagate failures from the worker thread
                failures.append(exc)

        worker = threading.Thread(target=run_planner)
        worker.start()
        marker = self.repo / ".factory/fake-claude-started"
        deadline = time.monotonic() + 2
        while not marker.is_file() and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue(marker.is_file(), "fake Claude process did not start")
        plan_id = sha_text(self.prd.read_text())[:12]
        log = self.repo / f".factory/logs/planner-{plan_id}-product_review.log"
        live_output = log.read_text() if log.is_file() else ""
        invoked_arguments = json.loads(marker.read_text())
        (self.repo / ".factory/release-fake-claude").write_text("continue\n")
        worker.join(timeout=2)
        self.assertFalse(worker.is_alive(), "fake Claude process did not stop")
        if failures:
            raise failures[0]
        self.assertIn("Claude Product Review started", live_output)
        self.assertIn("stream-json", invoked_arguments)

    def test_continue_requires_product_approval(self):
        run = self.start()
        with self.assertRaisesRegex(ValueError, "approve it again"):
            continue_plan(self.repo, run.name, "codex", mock=True)

    def test_four_stages_create_traceability_and_alignment_gate(self):
        run = self.finish()
        manifest = load_manifest(run)
        self.assertEqual(manifest["status"], "awaiting_alignment_approval")
        self.assertTrue(all(item["status"] == "complete" for item in manifest["stages"].values()))
        traceability = json.loads((run / "traceability.json").read_text())
        self.assertEqual({row["requirement_id"] for row in traceability["rows"]}, {"R1", "R2", "R3", "R4", "R5"})
        self.assertTrue(all(row["slices"] and row["qa_evidence"] for row in traceability["rows"]))
        self.assertTrue((run / "alignment-review.md").is_file())

    def test_charter_selected_intermediate_planning_approvals_pause_the_pipeline(self):
        charter = replace(
            FactoryCharter.load(self.repo),
            planning_approvals=(
                "product_review",
                "system_architecture",
                "program_design",
                "alignment",
            ),
            approved=False,
            approved_policy_sha256="",
        )
        charter.write(force=True)
        charter.approve()

        run = self.start()
        approve_product(self.repo, run.name, assume_yes=True)
        continue_plan(self.repo, run.name, "mock", mock=True)

        manifest = load_manifest(run)
        self.assertEqual(manifest["status"], "awaiting_system_architecture_approval")
        self.assertEqual(manifest["stages"]["system_architecture"]["status"], "complete")
        self.assertEqual(manifest["stages"]["program_design"]["status"], "pending")
        self.assertIsNone(manifest["approvals"]["system_architecture"])

        approve_planning_stage(
            self.repo, run.name, "system_architecture", assume_yes=True,
        )
        continue_plan(self.repo, run.name, "mock", mock=True)
        manifest = load_manifest(run)
        self.assertEqual(manifest["status"], "awaiting_program_design_approval")
        self.assertIsNotNone(manifest["approvals"]["system_architecture"])
        self.assertIsNone(manifest["approvals"]["program_design"])
        self.assertEqual(manifest["stages"]["vertical_slices"]["status"], "pending")

        approve_planning_stage(
            self.repo, run.name, "program_design", assume_yes=True,
        )
        continue_plan(self.repo, run.name, "mock", mock=True)
        manifest = load_manifest(run)
        self.assertEqual(manifest["status"], "awaiting_alignment_approval")
        self.assertIsNotNone(manifest["approvals"]["program_design"])
        self.assertEqual(manifest["stages"]["vertical_slices"]["status"], "complete")

    def test_load_bearing_slice_selects_intermediate_planning_approvals(self):
        charter = FactoryCharter.load(self.repo)
        charter = replace(
            charter,
            load_bearing_paths=("demo-app",),
            planning_approvals=("product_review", "alignment"),
            approved=False,
            approved_policy_sha256="",
        )
        charter.write(force=True)
        charter.approve()
        run = self.start()
        approve_product(self.repo, run.name, assume_yes=True)

        continue_plan(self.repo, run.name, "codex", mock=True)
        manifest = load_manifest(run)

        self.assertEqual(manifest["status"], "awaiting_system_architecture_approval")
        self.assertEqual(manifest["planning_controls"]["risk"], "load-bearing")
        self.assertEqual(
            manifest["planning_controls"]["planning_approvals"],
            ["product_review", "system_architecture", "program_design", "alignment"],
        )
        approve_planning_stage(
            self.repo, run.name, "architecture", assume_yes=True,
        )
        continue_plan(self.repo, run.name, "codex", mock=True)
        self.assertEqual(
            load_manifest(run)["status"], "awaiting_program_design_approval",
        )

    def test_lean_plan_fails_closed_when_slice_paths_require_missing_experts(self):
        charter = replace(
            FactoryCharter.load(self.repo),
            load_bearing_paths=("demo-app",),
            approved=False,
            approved_policy_sha256="",
        )
        charter.write(force=True)
        charter.approve()
        run = plan_prd(
            self.repo, self.prd, None, "codex", 3, 12,
            "mock", "mock", mock=True, profile_name="lean",
        )
        approve_product(self.repo, run.name, assume_yes=True)

        with self.assertRaisesRegex(ValueError, "choose Standard or Assured"):
            continue_plan(self.repo, run.name, "mock", mock=True)
        manifest = load_manifest(run)
        self.assertEqual(manifest["status"], "stale_factory_profile")
        self.assertIn("choose Standard or Assured", manifest["planning_control_error"])

    def test_editing_an_approved_intermediate_artifact_clears_its_downstream_gates(self):
        charter = replace(
            FactoryCharter.load(self.repo),
            planning_approvals=(
                "product_review", "system_architecture", "program_design", "alignment",
            ),
            approved=False,
            approved_policy_sha256="",
        )
        charter.write(force=True)
        charter.approve()
        run = self.start()
        approve_product(self.repo, run.name, assume_yes=True)
        continue_plan(self.repo, run.name, "mock", mock=True)
        approve_planning_stage(
            self.repo, run.name, "system_architecture", assume_yes=True,
        )
        architecture_path = run / "02-system-architecture.json"
        architecture = json.loads(architecture_path.read_text())
        architecture["risks"].append("Human-edited deployment boundary")
        architecture_path.write_text(json.dumps(architecture, indent=2) + "\n")

        continue_plan(self.repo, run.name, "mock", mock=True)

        manifest = load_manifest(run)
        self.assertEqual(manifest["status"], "awaiting_system_architecture_approval")
        self.assertIsNone(manifest["approvals"]["system_architecture"])
        self.assertIsNone(manifest["approvals"]["program_design"])
        self.assertIsNone(manifest["approvals"]["alignment"])
        self.assertEqual(manifest["stages"]["program_design"]["status"], "pending")

    def test_product_edit_invalidates_approval_and_downstream(self):
        run = self.start()
        approve_product(self.repo, run.name, assume_yes=True)
        product_path = run / "01-product-review.json"
        product = json.loads(product_path.read_text())
        product["assumptions"].append("Human-edited assumption")
        product_path.write_text(json.dumps(product, indent=2) + "\n")
        with self.assertRaisesRegex(ValueError, "changed"):
            continue_plan(self.repo, run.name, "codex", mock=True)
        manifest = load_manifest(run)
        self.assertIsNone(manifest["approvals"]["product"])
        self.assertEqual(manifest["status"], "awaiting_product_approval")

    def test_architecture_edit_requires_downstream_regeneration(self):
        run = self.finish()
        architecture_path = run / "02-system-architecture.json"
        architecture = json.loads(architecture_path.read_text())
        architecture["risks"].append("Human-added integration risk")
        architecture_path.write_text(json.dumps(architecture, indent=2) + "\n")
        with self.assertRaisesRegex(ValueError, "rerun continue-plan"):
            review(self.repo, "alignment", run.name)
        manifest = load_manifest(run)
        self.assertEqual(manifest["status"], "stale_alignment")
        self.assertEqual(manifest["stages"]["program_design"]["status"], "stale")

    def test_restarting_same_prd_removes_downstream_artifacts(self):
        run = self.finish()
        self.assertTrue((run / "04-vertical-slices.json").is_file())
        restarted = self.start()
        self.assertEqual(restarted, run)
        self.assertFalse((run / "02-system-architecture.json").exists())
        self.assertFalse((run / "traceability.json").exists())
        self.assertEqual(load_manifest(run)["status"], "awaiting_product_approval")

    def test_alignment_approval_produces_publishable_plan_without_github(self):
        run = self.finish()
        publishable, returned_run = prepare_publication(self.repo, run.name, assume_yes=True)
        self.assertEqual(returned_run.resolve(), run.resolve())
        self.assertEqual(json.loads(publishable.read_text())["plan_version"], 2)
        self.assertEqual(load_manifest(run)["status"], "alignment_approved")

    def test_rehearsal_alignment_approval_materializes_prd_derived_tickets(self):
        run = self.finish()

        tickets_path = approve_rehearsal(
            self.repo,
            run.name,
            assume_yes=True,
            scenario="recipe-rebrand",
        )

        tickets = json.loads(tickets_path.read_text())
        slices = json.loads((run / "04-vertical-slices.json").read_text())["tickets"]
        self.assertEqual(
            [ticket["title"] for ticket in tickets],
            [ticket["title"] for ticket in slices],
        )
        self.assertIn(f"factory-plan:{run.name}:T1", tickets[0]["body"])
        self.assertIn("factory-governance:v1;profile=standard;charter=", tickets[0]["body"])
        self.assertIn(";merge=human", tickets[0]["body"])
        self.assertIn("agent: mock", tickets[0]["body"])
        self.assertEqual(tickets[2]["dependencies"], [1, 2])
        manifest = load_manifest(run)
        self.assertEqual(manifest["status"], "alignment_approved")
        self.assertEqual(manifest["rehearsal"]["tickets_path"], str(tickets_path.relative_to(self.repo)))

    def test_product_revision_records_feedback_and_invalidates_downstream_approval(self):
        run = self.finish()
        prepare_publication(self.repo, run.name, assume_yes=True)
        original = load_manifest(run)
        original_hash = original["stages"]["product_review"]["sha256"]

        revise_plan(
            self.repo,
            run.name,
            "product",
            "Define keyboard back-navigation evidence and prove TV mode is preserved.",
            "mock",
            mock=True,
        )

        manifest = load_manifest(run)
        self.assertEqual(manifest["status"], "awaiting_product_approval")
        self.assertIsNone(manifest["approvals"]["product"])
        self.assertIsNone(manifest["approvals"]["alignment"])
        self.assertNotEqual(manifest["stages"]["product_review"]["sha256"], original_hash)
        self.assertTrue(
            all(
                manifest["stages"][stage]["status"] == "stale"
                for stage in ("system_architecture", "program_design", "vertical_slices")
            )
        )
        revision = manifest["revisions"][-1]
        self.assertEqual(revision["stage"], "product_review")
        self.assertIn("keyboard back-navigation", revision["feedback"])
        self.assertEqual(revision["before_sha256"], original_hash)
        self.assertEqual(revision["after_sha256"], manifest["stages"]["product_review"]["sha256"])
        revised_product = json.loads((run / "01-product-review.json").read_text())
        tv_evidence = next(item for item in revised_product["requirements"] if item["id"] == "R4")["success_evidence"]
        self.assertIn("mode=tv", tv_evidence)
        with self.assertRaisesRegex(ValueError, "approve it again"):
            prepare_publication(self.repo, run.name, assume_yes=True)

    def test_architecture_revision_records_decisions_and_resumes_downstream_planning(self):
        run = self.finish()
        architecture_path = run / "02-system-architecture.json"
        architecture = json.loads(architecture_path.read_text())
        architecture["blocking_questions"] = ["Should the service live in this repository?"]
        architecture_path.write_text(json.dumps(architecture, indent=2) + "\n")
        decision = "Keep the service in this repository under the configured source root."

        revise_plan(
            self.repo,
            run.name,
            "architecture",
            decision,
            "mock",
            mock=True,
        )

        manifest = load_manifest(run)
        self.assertEqual(manifest["status"], "product_approved")
        self.assertIsNotNone(manifest["approvals"]["product"])
        self.assertIsNone(manifest["approvals"]["alignment"])
        self.assertEqual(manifest["stages"]["system_architecture"]["status"], "complete")
        self.assertEqual(manifest["stages"]["program_design"]["status"], "stale")
        self.assertEqual(manifest["stages"]["vertical_slices"]["status"], "stale")
        revision = manifest["revisions"][-1]
        self.assertEqual(revision["stage"], "system_architecture")
        self.assertEqual(revision["feedback"], decision)
        self.assertTrue((self.repo / revision["previous_artifact"]).is_file())
        prompt = (self.repo / manifest["stages"]["system_architecture"]["prompt"]).read_text()
        self.assertIn("## Current artifact", prompt)
        self.assertIn("Should the service live in this repository?", prompt)
        self.assertIn(decision, prompt)

        continue_plan(self.repo, run.name, "mock", mock=True)
        resumed = load_manifest(run)
        self.assertEqual(resumed["status"], "awaiting_alignment_approval")
        self.assertTrue(all(item["status"] == "complete" for item in resumed["stages"].values()))

    def test_parallel_file_ownership_conflict_is_rejected(self):
        product = json.loads((FIXTURES / "01-product-review.json").read_text())
        architecture = json.loads((FIXTURES / "02-system-architecture.json").read_text())
        program = json.loads((FIXTURES / "03-program-design.json").read_text())
        slices = json.loads((FIXTURES / "04-vertical-slices.json").read_text())
        slices["tickets"][1]["file_ownership"].append("demo-app/recipes.py")
        with self.assertRaisesRegex(ValueError, "parallel tickets T1 and T2"):
            validate_vertical_slices(slices, product, architecture, program)

    def test_lean_profile_runs_only_product_review_and_vertical_slices(self):
        run = plan_prd(
            self.repo,
            self.prd,
            None,
            "codex",
            3,
            12,
            "mock",
            "mock",
            mock=True,
            profile_name="lean",
        )
        approve_product(self.repo, run.name, assume_yes=True)
        continue_plan(self.repo, run.name, "mock", mock=True)

        manifest = load_manifest(run)
        self.assertEqual(manifest["profile"], "lean")
        self.assertEqual(manifest["stages"]["system_architecture"]["status"], "not_applicable")
        self.assertEqual(manifest["stages"]["program_design"]["status"], "not_applicable")
        self.assertEqual(manifest["stages"]["vertical_slices"]["status"], "complete")
        self.assertFalse((run / "02-system-architecture.json").exists())
        self.assertFalse((run / "03-program-design.json").exists())
        traceability = json.loads((run / "traceability.json").read_text())
        self.assertTrue(all(row["slices"] and row["qa_evidence"] for row in traceability["rows"]))
        self.assertTrue(all(not row["architecture_contracts"] for row in traceability["rows"]))
        publishable, _ = prepare_publication(self.repo, run.name, assume_yes=True)
        self.assertTrue(publishable.is_file())


if __name__ == "__main__":
    unittest.main()
