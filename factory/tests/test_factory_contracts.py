import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


FACTORY = Path(__file__).parents[1] / "orchestrator.py"
sys.path.insert(0, str(Path(__file__).parents[1]))

from factory_contracts import handoff_receipt, validate_handoff_receipt
from release_check import audit_release, run_live_github_smoke, validate_standard_rehearsal


class FactoryContractTests(unittest.TestCase):
    def test_handoff_receipt_carries_structured_causal_evidence(self):
        receipt = handoff_receipt(
            run_id="run-1",
            role="qa",
            phase="Build",
            ticket=7,
            attempt=1,
            input_revisions={"base_commit": "abc"},
            output_revisions={"qa_commit": "def"},
            claimed_result="RED PROVED",
            verification=["Focused Acceptance Test failed on a behavior assertion."],
            unresolved_risks=[],
            artifacts=["tests/test_ticket_7.py"],
            policy_hashes={"engineering": "hash"},
            evidence={
                "focused_test_command": "python -m pytest -q tests/test_ticket_7.py",
                "expected_failure_classification": "behavior_assertion",
                "test_revision": "def",
                "output": "AssertionError: expected recipe",
            },
        )

        self.assertEqual(receipt["schema_version"], 2)
        self.assertEqual(receipt["evidence"]["test_revision"], "def")
        receipt["evidence"] = []
        with self.assertRaisesRegex(ValueError, "evidence must be an object"):
            validate_handoff_receipt(receipt)

    def test_cli_exposes_frozen_workshop_version(self):
        result = subprocess.run(
            [sys.executable, str(FACTORY), "--version"],
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertEqual(result.stdout.strip(), "factory workshop-v1.1.0")

    def test_release_check_audits_clean_versioned_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "factory").mkdir()
            (repo / "workshop-guide/app").mkdir(parents=True)
            (repo / "factory/factory_contracts.py").write_text('WORKSHOP_VERSION = "workshop-v1.1.0"\n')
            (repo / "factory/WORKSHOP_OUTLINE.md").write_text("# workshop-v1.1.0\n")
            (repo / "factory/FACILITATOR.md").write_text("# workshop-v1.1.0\n")
            (repo / "workshop-guide/app/page.tsx").write_text("workshop-v1.1.0\n")
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

    def test_release_audit_rejects_broken_participant_links(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "factory").mkdir()
            (repo / "workshop-guide/app").mkdir(parents=True)
            (repo / "factory/factory_contracts.py").write_text('WORKSHOP_VERSION = "workshop-v1.1.0"\n')
            (repo / "factory/WORKSHOP_OUTLINE.md").write_text("# workshop-v1.1.0\n[Missing](NOPE.md)\n")
            (repo / "factory/FACILITATOR.md").write_text("# workshop-v1.1.0\n")
            (repo / "workshop-guide/app/page.tsx").write_text("workshop-v1.1.0\n")
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run(
                ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-qm", "fixture"],
                cwd=repo,
                check=True,
            )

            failures, _ = audit_release(repo)

            self.assertIn(
                "broken participant link: factory/WORKSHOP_OUTLINE.md -> NOPE.md",
                failures,
            )

    def test_release_rehearsal_contract_requires_gates_retry_and_role_receipts(self):
        manifest = {
            "approvals": {"product": {"approved_at": "now"}, "alignment": {"approved_at": "now"}},
            "revisions": [{"revision": 1}],
            "rehearsal": {"tickets_path": ".factory/rehearsal/demo/tickets.json"},
        }
        receipt_roles = [
            "supervisor", "qa", "implementation", "verification", "code_review", "human_review",
        ]
        state = {"tickets": [
            {
                "number": number,
                "status": "Done",
                "attempt": 2 if number in {1, 3} else 1,
                "_loaded_receipts": [{"role": role} for role in receipt_roles],
                "code_review": {"result": {"decision": "APPROVE"}},
                "gate_results": [{"name": "tests", "required": True, "exit_code": 0}],
                "qa_evidence": {
                    "focused_test_command": "python -m pytest -q tests/test_ticket.py",
                    "focused_test_command_sha256": "same-command",
                    "red": {"result": "RED PROVED", "classification": "behavior_assertion"},
                    "green": {"result": "GREEN PROVED", "classification": "pass"},
                },
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
        state["tickets"][1]["gate_results"] = [{"name": "tests", "required": True, "exit_code": 0}]
        state["tickets"][1]["qa_evidence"]["red"]["result"] = "RED NOT PROVED"
        self.assertIn(
            "ticket #2 has no RED PROVED evidence",
            "; ".join(validate_standard_rehearsal(manifest, state)),
        )

    def test_live_smoke_requires_explicit_disposable_repository_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "factory").mkdir()
            (repo / "workshop-guide/app").mkdir(parents=True)
            (repo / "factory/factory_contracts.py").write_text('WORKSHOP_VERSION = "workshop-v1.1.0"\n')
            (repo / "factory/WORKSHOP_OUTLINE.md").write_text("# workshop-v1.1.0\n")
            (repo / "factory/FACILITATOR.md").write_text("# workshop-v1.1.0\n")
            (repo / "workshop-guide/app/page.tsx").write_text("workshop-v1.1.0\n")
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

    def test_live_smoke_brief_records_protected_acceptance_test_approval(self):
        class StopAfterProductReview(Exception):
            pass

        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / ".factory/plans").mkdir(parents=True)
            backend = Mock(owner="giolaq", name="test1")

            def checked(command, cwd, timeout=180):
                if "plan" in command:
                    (repo / ".factory/plans/latest.json").write_text(json.dumps({
                        "plan_id": "live-plan",
                    }))
                if command[-3:] == ["review", "product", "live-plan"]:
                    brief = next((repo / ".factory").glob("live-smoke-*.md")).read_text()
                    self.assertIn(
                        "Human approval for this disposable smoke explicitly covers adding "
                        "the Acceptance Test under `demo-app/tests/`.",
                        brief,
                    )
                    raise StopAfterProductReview
                return ""

            with (
                patch("github_backend.GitHubBackend", return_value=backend),
                patch("release_check.shutil.which", return_value="/usr/bin/gh"),
                patch("release_check._checked", side_effect=checked),
                self.assertRaises(StopAfterProductReview),
            ):
                run_live_github_smoke(repo, True)

    def test_live_smoke_repairs_first_vertical_slice_validation_once(self):
        class StopAfterBoundedRepair(Exception):
            pass

        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            run_dir = repo / ".factory/plans/live-plan"
            run_dir.mkdir(parents=True)
            backend = Mock(owner="giolaq", name="test1")
            continue_attempts = 0

            def checked(command, cwd, timeout=180):
                nonlocal continue_attempts
                if "plan" in command:
                    (repo / ".factory/plans/latest.json").write_text(json.dumps({
                        "plan_id": "live-plan",
                    }))
                if command[-2:] == ["continue-plan", "live-plan"]:
                    continue_attempts += 1
                    if continue_attempts == 1:
                        (run_dir / "manifest.json").write_text(json.dumps({
                            "stages": {
                                "vertical_slices": {
                                    "status": "blocked",
                                    "failure_kind": "validation",
                                    "validation_error": (
                                        "SMOKE-DELIVER requires non-empty file_ownership"
                                    ),
                                    "same_failure_count": 1,
                                },
                            },
                        }))
                        raise RuntimeError(
                            "SMOKE-DELIVER requires non-empty file_ownership"
                        )
                if "revise" in command:
                    self.assertEqual(command[command.index("revise") + 1:command.index("revise") + 3], [
                        "live-plan", "slices",
                    ])
                    feedback = command[command.index("--feedback") + 1]
                    self.assertIn("exactly one vertical slice", feedback)
                    self.assertIn("Acceptance Test", feedback)
                    self.assertIn("non-empty file_ownership", feedback)
                    raise StopAfterBoundedRepair
                return ""

            with (
                patch("github_backend.GitHubBackend", return_value=backend),
                patch("release_check.shutil.which", return_value="/usr/bin/gh"),
                patch("release_check._checked", side_effect=checked),
                self.assertRaises(StopAfterBoundedRepair),
            ):
                run_live_github_smoke(repo, True)

            self.assertEqual(continue_attempts, 1)

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
            ["supervisor", "qa", "implementation", "verification", "code_review", "human_review"],
        )
        self.assertEqual(
            profiles["assured"]["execution_roles"],
            [
                "supervisor",
                "qa",
                "implementation",
                "cleanup",
                "architecture_conformance",
                "hardening",
                "verification",
                "critic",
                "negative_proof",
                "final_verifier",
                "code_review",
                "human_review",
            ],
        )
        self.assertFalse(profiles["lean"]["protected_acceptance_tests"])
        self.assertTrue(profiles["standard"]["protected_acceptance_tests"])
        self.assertTrue(profiles["assured"]["protected_acceptance_tests"])

    def test_normal_profiles_keep_human_merge_and_autonomous_demo_is_explicit(self):
        result = subprocess.run(
            [sys.executable, str(FACTORY), "profiles", "--json"],
            text=True,
            capture_output=True,
            check=True,
        )
        profiles = json.loads(result.stdout)

        for name in ("lean", "standard", "assured"):
            with self.subTest(profile=name):
                self.assertEqual(profiles[name]["merge_authority"], "human")
                self.assertNotIn("supervisor_merge", profiles[name]["execution_roles"])
        self.assertEqual(profiles["autonomous-demo"]["merge_authority"], "supervisor")
        self.assertIn("supervisor_merge", profiles["autonomous-demo"]["execution_roles"])
        self.assertTrue(profiles["autonomous-demo"]["requires_explicit_opt_in"])

if __name__ == "__main__":
    unittest.main()
