import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1]))

from planning_pipeline import (
    approve_rehearsal,
    approve_product,
    continue_plan,
    load_manifest,
    plan_prd,
    prepare_publication,
    revise_plan,
    review,
    sha_text,
    validate_vertical_slices,
)


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

    def test_claude_planner_uses_structured_output_and_records_agent(self):
        product = json.loads((FIXTURES / "01-product-review.json").read_text())
        response = subprocess.CompletedProcess(
            ["claude"], 0,
            json.dumps({"structured_output": product, "result": ""}), "",
        )
        with patch("planning_pipeline.subprocess.run", return_value=response) as invoked:
            run = plan_prd(
                self.repo, self.prd, None, "claude", 3, 12,
                "claude", "claude", mock=False,
            )
        command = invoked.call_args.args[0]
        self.assertIn("--json-schema", command)
        self.assertTrue(
            invoked.call_args.kwargs["input"].startswith("You are the Product Review expert."),
        )
        manifest = load_manifest(run)
        self.assertEqual(manifest["planning_agent"], "claude")
        self.assertEqual(manifest["stages"]["product_review"]["agent"], "claude")

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
