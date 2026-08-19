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
    approve_product,
    continue_plan,
    load_manifest,
    plan_prd,
    prepare_publication,
    review,
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

    def test_parallel_file_ownership_conflict_is_rejected(self):
        product = json.loads((FIXTURES / "01-product-review.json").read_text())
        architecture = json.loads((FIXTURES / "02-system-architecture.json").read_text())
        program = json.loads((FIXTURES / "03-program-design.json").read_text())
        slices = json.loads((FIXTURES / "04-vertical-slices.json").read_text())
        slices["tickets"][1]["file_ownership"].append("demo-app/recipes.py")
        with self.assertRaisesRegex(ValueError, "parallel tickets T1 and T2"):
            validate_vertical_slices(slices, product, architecture, program)


if __name__ == "__main__":
    unittest.main()
