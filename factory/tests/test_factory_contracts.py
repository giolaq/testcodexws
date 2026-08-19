import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


FACTORY = Path(__file__).parents[1] / "orchestrator.py"
sys.path.insert(0, str(Path(__file__).parents[1]))

from release_check import validate_standard_rehearsal


class FactoryContractTests(unittest.TestCase):
    def test_cli_exposes_frozen_workshop_version(self):
        result = subprocess.run(
            [sys.executable, str(FACTORY), "--version"],
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertEqual(result.stdout.strip(), "factory workshop-v1.0.0")

    def test_release_check_audits_clean_versioned_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "factory").mkdir()
            (repo / "workshop-guide/app").mkdir(parents=True)
            (repo / "factory/factory_contracts.py").write_text('WORKSHOP_VERSION = "workshop-v1.0.0"\n')
            (repo / "factory/WORKSHOP_OUTLINE.md").write_text("# workshop-v1.0.0\n")
            (repo / "factory/FACILITATOR.md").write_text("# workshop-v1.0.0\n")
            (repo / "workshop-guide/app/page.tsx").write_text("workshop-v1.0.0\n")
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run(
                ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "fixture"],
                cwd=repo,
                check=True,
            )

            result = subprocess.run(
                [sys.executable, str(FACTORY), "release-check", "--repo", str(repo)],
                text=True,
                capture_output=True,
                check=True,
            )

            self.assertIn("Local release audit: PASS", result.stdout)
            self.assertIn("release-check --rehearsal", result.stdout)
            self.assertIn("release-check --live-smoke", result.stdout)

    def test_release_rehearsal_contract_requires_gates_retry_and_role_receipts(self):
        manifest = {
            "approvals": {"product": {"approved_at": "now"}, "alignment": {"approved_at": "now"}},
            "revisions": [{"revision": 1}],
            "rehearsal": {"tickets_path": ".factory/rehearsal/demo/tickets.json"},
        }
        receipt_roles = ["qa", "implementation", "verification", "human_review"]
        state = {"tickets": [
            {
                "number": number,
                "status": "Done",
                "attempt": 2 if number == 3 else 1,
                "_loaded_receipts": [{"role": role} for role in receipt_roles],
                "gate_results": [{"name": "tests", "required": True, "exit_code": 0}],
            }
            for number in range(1, 6)
        ]}

        self.assertEqual(validate_standard_rehearsal(manifest, state), [])
        state["tickets"][2]["attempt"] = 1
        self.assertIn("one retry", "; ".join(validate_standard_rehearsal(manifest, state)))
        state["tickets"][2]["attempt"] = 2
        state["tickets"][0]["_loaded_receipts"] = [{"role": "implementation"}]
        self.assertIn(
            "ticket #1 is missing Standard role receipts",
            "; ".join(validate_standard_rehearsal(manifest, state)),
        )
        state["tickets"][0]["_loaded_receipts"] = [{"role": role} for role in receipt_roles]
        state["tickets"][1]["gate_results"][0]["exit_code"] = 1
        self.assertIn(
            "ticket #2 has failed required gates",
            "; ".join(validate_standard_rehearsal(manifest, state)),
        )
        state["tickets"][1]["gate_results"] = [{
            "name": "advisory-lint", "required": False, "exit_code": 0,
        }]
        self.assertIn(
            "ticket #2 has no required verification gate result",
            "; ".join(validate_standard_rehearsal(manifest, state)),
        )

    def test_live_smoke_requires_explicit_disposable_repository_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "factory").mkdir()
            (repo / "workshop-guide/app").mkdir(parents=True)
            (repo / "factory/factory_contracts.py").write_text('WORKSHOP_VERSION = "workshop-v1.0.0"\n')
            (repo / "factory/WORKSHOP_OUTLINE.md").write_text("# workshop-v1.0.0\n")
            (repo / "factory/FACILITATOR.md").write_text("# workshop-v1.0.0\n")
            (repo / "workshop-guide/app/page.tsx").write_text("workshop-v1.0.0\n")
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run(
                ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "fixture"],
                cwd=repo,
                check=True,
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(FACTORY),
                    "release-check",
                    "--repo",
                    str(repo),
                    "--live-smoke",
                ],
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("--confirm-disposable-repo", result.stdout)

    def test_profiles_command_exposes_executable_role_topologies(self):
        result = subprocess.run(
            [sys.executable, str(FACTORY), "profiles", "--json"],
            text=True,
            capture_output=True,
            check=True,
        )
        profiles = json.loads(result.stdout)
        self.assertEqual(
            profiles["lean"]["planning_roles"],
            ["product_review", "vertical_slices"],
        )
        self.assertEqual(
            profiles["standard"]["execution_roles"],
            ["qa", "implementation", "verification", "human_review"],
        )
        self.assertEqual(
            profiles["assured"]["execution_roles"],
            [
                "qa",
                "implementation",
                "cleanup",
                "architecture_conformance",
                "hardening",
                "verification",
                "final_verifier",
                "human_review",
            ],
        )
        self.assertFalse(profiles["lean"]["protected_acceptance_tests"])
        self.assertTrue(profiles["standard"]["protected_acceptance_tests"])
        self.assertTrue(profiles["assured"]["protected_acceptance_tests"])

    def test_dashboard_teaches_macro_phases_and_exposes_engine_room_evidence(self):
        dashboard = (Path(__file__).parents[1] / "dashboard.html").read_text()
        for phase in ("Plan", "Build", "Verify", "Review"):
            self.assertIn(f">{phase}<", dashboard)
        self.assertIn("Factory Profile", dashboard)
        self.assertIn("Policy version", dashboard)
        self.assertIn("Handoff Receipts", dashboard)
        self.assertIn("Rehearsal Run", dashboard)
        self.assertIn("Live Run", dashboard)
        self.assertNotIn("Mock rehearsal", dashboard)
        self.assertNotIn("GitHub production", dashboard)


if __name__ == "__main__":
    unittest.main()
