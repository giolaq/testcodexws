import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
import subprocess

import sys

sys.path.insert(0, str(Path(__file__).parents[1]))

from factory_charter import FactoryCharter, FactoryCharterError
from orchestrator import approve_charter, initialize_project
from planning_pipeline import plan_prd
from project_contract import ProjectContract


class FactoryCharterTests(unittest.TestCase):
    def test_factory_init_creates_a_reviewable_draft_and_approval_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
            (repo / "README.md").write_text("# Target\n")

            initialize_project(repo, None, False)

            self.assertTrue((repo / "factory.project.toml").is_file())
            self.assertTrue((repo / "factory.charter.toml").is_file())
            with self.assertRaisesRegex(FactoryCharterError, "not approved"):
                FactoryCharter.load(repo, require_approved=True)

            approve_charter(repo, assume_yes=True)

            self.assertTrue(FactoryCharter.load(repo, require_approved=True).approved)

    def test_approval_is_bound_to_the_exact_human_owned_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            project = ProjectContract.detect(repo)
            path = FactoryCharter.draft(repo, project).write()

            with self.assertRaisesRegex(FactoryCharterError, "not approved"):
                FactoryCharter.load(repo, require_approved=True)

            approved = FactoryCharter.load(repo).approve()
            loaded = FactoryCharter.load(repo, require_approved=True)
            self.assertTrue(loaded.approved)
            self.assertEqual(loaded.approved_policy_sha256, approved.policy_sha256())
            self.assertEqual(loaded.merge_authority, "human")
            self.assertEqual(loaded.gate_level, "full")
            self.assertIn("factory.charter.toml", loaded.never_modify)

            path.write_text(path.read_text().replace("max_diff_lines = 800", "max_diff_lines = 801"))
            with self.assertRaisesRegex(FactoryCharterError, "changed after approval"):
                FactoryCharter.load(repo, require_approved=True)

    def test_draft_contains_all_required_production_controls(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            charter = FactoryCharter.draft(repo, ProjectContract.detect(repo))

            self.assertEqual(charter.schema_version, 1)
            self.assertEqual(charter.consequence_tier, "shared")
            self.assertEqual(charter.existing_tests, "review")
            self.assertEqual(charter.planning_approvals, ("product_review", "alignment"))
            self.assertEqual(charter.max_retries, 2)
            self.assertEqual(charter.max_awaiting_human_review, 3)
            self.assertEqual(charter.max_blocked_for_human, 2)
            self.assertTrue(charter.load_bearing_paths)
            self.assertEqual(charter.editable_paths, ProjectContract.detect(repo).source_roots)
            self.assertTrue(charter.requires_human_approval)
            self.assertTrue(charter.stop_conditions)

    def test_charter_cannot_remove_product_and_alignment_accountability_gates(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            path = FactoryCharter.draft(repo, ProjectContract.detect(repo)).write()
            path.write_text(path.read_text().replace(
                'planning_approvals = ["product_review", "alignment"]',
                'planning_approvals = ["system_architecture"]',
            ))

            with self.assertRaisesRegex(
                FactoryCharterError, "must include product_review and alignment",
            ):
                FactoryCharter.load(repo)

    def test_profile_cannot_omit_a_charter_required_planning_stage(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            charter = replace(
                FactoryCharter.draft(repo, ProjectContract.detect(repo)),
                planning_approvals=(
                    "product_review", "system_architecture", "alignment",
                ),
            )
            charter.write()
            charter = charter.approve()

            with self.assertRaisesRegex(
                FactoryCharterError, "Lean does not run.*system_architecture",
            ):
                charter.governance("lean")

    def test_planning_fails_closed_until_the_exact_charter_is_approved(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            prd = repo / "PRD.md"
            prd.write_text("# Product\n\nDeliver one observable outcome.\n")

            with self.assertRaisesRegex(FactoryCharterError, "not found"):
                plan_prd(
                    repo, prd, None, "mock", 3, 12,
                    "mock", "mock", mock=True,
                )

            FactoryCharter.draft(repo, ProjectContract.detect(repo)).write()
            with self.assertRaisesRegex(FactoryCharterError, "not approved"):
                plan_prd(
                    repo, prd, None, "mock", 3, 12,
                    "mock", "mock", mock=True,
                )

            FactoryCharter.load(repo).approve()
            run = plan_prd(
                repo, prd, None, "mock", 3, 12,
                "mock", "mock", mock=True,
            )
            manifest = __import__("json").loads((run / "manifest.json").read_text())
            self.assertEqual(manifest["governance"]["profile"], "standard")
            self.assertEqual(manifest["governance"]["merge_authority"], "human")
            self.assertEqual(
                manifest["governance"]["charter_sha256"],
                FactoryCharter.load(repo, require_approved=True).policy_sha256(),
            )


if __name__ == "__main__":
    unittest.main()
