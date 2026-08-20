import hashlib
import json
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parents[1]))

from orchestrator import DEFAULT_AGENTS, Factory, validate_qa_changes, validate_qa_config
from mock_qa_agent import RECIPE_TESTS


TEST_ROOTS = ["demo-app/tests", "demo-app/static/tests"]


class QaPolicyTests(unittest.TestCase):
    def test_recipe_rehearsal_qa_covers_each_ticket_contract(self):
        self.assertIn("len(recipes) >= 12", RECIPE_TESTS[1])
        self.assertIn("/api/cookbook", RECIPE_TESTS[1])
        self.assertIn("recipe_ids", RECIPE_TESTS[1])
        self.assertIn(":focus-visible", RECIPE_TESTS[2])
        self.assertIn("aria-pressed", RECIPE_TESTS[2])
        self.assertIn("addEventListener('input'", RECIPE_TESTS[3])
        self.assertIn("Ingredients", RECIPE_TESTS[3])
        self.assertIn("Backspace", RECIPE_TESTS[4])
        self.assertIn("scrollIntoView", RECIPE_TESTS[4])
        self.assertIn("catalog.json", RECIPE_TESTS[5])
        self.assertIn("test_terminology.py", RECIPE_TESTS[5])

    def test_standard_profile_cannot_disable_independent_qa(self):
        with tempfile.TemporaryDirectory() as directory:
            args = SimpleNamespace(
                repo=directory, qa_agent=None, no_qa=True, mock=True,
                project_number=None, review_qa_tests=False, scenario="tv",
                agent="mock", profile="standard",
            )
            with self.assertRaisesRegex(ValueError, "requires independent QA"):
                Factory(args)

    def test_implementation_prompt_includes_role_contract_and_versioned_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            contract_dir = repo / "factory"
            contract_dir.mkdir()
            (contract_dir / "roles.json").write_text(json.dumps({
                "schema_version": 1,
                "roles": {
                    "implementation": {
                        "ownership": ["Production code in the Ticket scope."],
                        "exclusions": ["Protected Acceptance Tests."],
                        "verification": ["Run the required gates."],
                        "handoff_receipt": ["Report changed files and unresolved risks."],
                    },
                },
            }))
            policy = {
                "version": "policy-test-v1",
                "engineering": ["Prefer public behavior seams."],
                "workflow": ["Stay within the Ticket scope."],
                "repository": ["Do not rewrite shared history."],
                "role_applicability": {
                    "implementation": ["engineering", "workflow", "repository"],
                },
            }
            (contract_dir / "policy.json").write_text(json.dumps(policy))
            args = SimpleNamespace(
                repo=str(repo), qa_agent="codex", no_qa=False, mock=True,
                project_number=None, review_qa_tests=False,
                scenario="tv", agent="codex", profile="standard",
            )
            factory = Factory(args)
            prompt = factory.make_prompt({
                "number": 7,
                "title": "Search recipes",
                "body": "## Spec\nSearch by ingredient.",
                "attempt": 1,
                "qa_tests": {},
            }, "").read_text()

            self.assertIn("## Agent Role contract · Implementation", prompt)
            self.assertIn("### Ownership", prompt)
            self.assertIn("### Exclusions", prompt)
            self.assertIn("### Verification responsibility", prompt)
            self.assertIn("### Handoff Receipt", prompt)
            self.assertIn("Policy version: `policy-test-v1`", prompt)
            engineering_hash = hashlib.sha256("Prefer public behavior seams.\n".encode()).hexdigest()
            self.assertIn(engineering_hash, prompt)
            self.assertIn("Do not rewrite shared history.", prompt)

    def test_accepts_new_ticket_numbered_python_and_javascript_tests(self):
        changes = [
            ("A", "demo-app/tests/test_ticket_42_search.py"),
            ("A", "demo-app/static/tests/ticket-42-tv-nav.test.js"),
        ]
        self.assertEqual(validate_qa_changes(changes, 42, TEST_ROOTS), [])

    def test_requires_at_least_one_acceptance_test(self):
        self.assertEqual(
            validate_qa_changes([], 42, TEST_ROOTS),
            ["QA agent did not create an acceptance-test file"],
        )

    def test_rejects_edits_to_existing_tests_and_production_files(self):
        changes = [
            ("M", "demo-app/tests/test_ticket_42_search.py"),
            ("A", "demo-app/app.py"),
        ]
        errors = validate_qa_changes(changes, 42, TEST_ROOTS)
        self.assertTrue(any("may only add" in error for error in errors))
        self.assertTrue(any("outside" in error for error in errors))

    def test_rejects_unmapped_test_filenames(self):
        errors = validate_qa_changes(
            [("A", "demo-app/tests/test_search.py")], 42, TEST_ROOTS,
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("test_ticket_42", errors[0])

    def test_validates_qa_configuration(self):
        qa = {"agent": "codex", "max_retries": 1, "test_roots": TEST_ROOTS}
        self.assertIsNone(validate_qa_config(qa, DEFAULT_AGENTS))
        custom_agents = {**DEFAULT_AGENTS, "my-agent": "./tools/run-my-agent.sh {prompt}"}
        self.assertIsNone(validate_qa_config({**qa, "agent": "my-agent"}, custom_agents))
        with self.assertRaisesRegex(ValueError, "stay inside"):
            validate_qa_config({**qa, "test_roots": ["../outside"]}, DEFAULT_AGENTS)
        with self.assertRaisesRegex(ValueError, "configured"):
            validate_qa_config({**qa, "agent": "mock"}, DEFAULT_AGENTS)

    def test_qa_phase_commits_and_protects_acceptance_tests(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            subprocess.run(["git", "config", "user.name", "Factory Test"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.email", "factory@example.test"], cwd=repo, check=True)
            (repo / "README.md").write_text("baseline\n")
            (repo / ".gitignore").write_text(".factory/\n")
            subprocess.run(["git", "add", "README.md", ".gitignore"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-qm", "baseline"], cwd=repo, check=True)
            base_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=repo, text=True, capture_output=True, check=True,
            ).stdout.strip()

            args = SimpleNamespace(
                repo=str(repo), qa_agent="codex", no_qa=False, mock=True, project_number=None,
                review_qa_tests=False, scenario="tv", agent="codex",
            )
            factory = Factory(args)
            ticket = {
                "number": 42, "title": "Search recipes", "body": "## Acceptance criteria\n- Search works",
                "agent": "codex", "attempt": 1, "qa_agent": "codex", "qa_attempt": 0,
                "qa_tests": {}, "history": [],
            }
            factory.tickets[42] = ticket

            def fake_qa_adapter(agent, active_ticket, worktree, prompt, log_name, phase):
                test = worktree / "demo-app/tests/test_ticket_42_search.py"
                test.parent.mkdir(parents=True, exist_ok=True)
                test.write_text("def test_recipe_search_acceptance():\n    assert True\n")
                return 0, "acceptance test created"

            factory.run_adapter = fake_qa_adapter
            self.assertEqual(factory.create_qa_tests(ticket, repo, base_sha), "")
            self.assertNotEqual(ticket["qa_commit"], base_sha)
            self.assertEqual(list(ticket["qa_tests"]), ["demo-app/tests/test_ticket_42_search.py"])
            self.assertEqual(len(ticket["receipts"]), 1)
            receipt = json.loads((repo / ticket["receipts"][0]).read_text())
            self.assertEqual(receipt["role"], "qa")
            self.assertEqual(receipt["phase"], "Build")
            self.assertEqual(receipt["ticket"], 42)
            self.assertEqual(receipt["output_revisions"]["qa_commit"], ticket["qa_commit"])
            self.assertEqual(receipt["artifacts"], ["demo-app/tests/test_ticket_42_search.py"])
            self.assertEqual(set(receipt["policy_hashes"]), {"engineering", "workflow", "repository"})

            prompt = factory.make_prompt(ticket, "").read_text()
            self.assertIn("Independent QA acceptance tests", prompt)
            self.assertIn("Git hashes", prompt)

            protected = repo / "demo-app/tests/test_ticket_42_search.py"
            protected.write_text("def test_recipe_search_acceptance():\n    assert False\n")
            self.assertIn("was modified", factory.verify_qa_tests_unchanged(ticket, repo))

    def test_assured_profile_executes_extended_roles_with_read_only_reviews(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
            subprocess.run(["git", "config", "user.name", "Factory Test"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.email", "factory@example.test"], cwd=repo, check=True)
            (repo / "README.md").write_text("baseline\n")
            (repo / ".gitignore").write_text(".factory/\n")
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-qm", "baseline"], cwd=repo, check=True)
            head = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=repo, text=True, capture_output=True, check=True,
            ).stdout.strip()
            args = SimpleNamespace(
                repo=str(repo), qa_agent=None, no_qa=False, mock=True,
                project_number=None, review_qa_tests=False, scenario="tv",
                agent="mock", profile="assured",
            )
            factory = Factory(args)
            ticket = {
                "number": 9, "title": "Harden search", "body": "## Spec\nHarden search.",
                "agent": "mock", "attempt": 1, "qa_tests": {}, "history": [], "receipts": [],
            }
            factory.tickets[9] = ticket
            phases = []

            def successful_role(agent, active_ticket, worktree, prompt, log_name, phase):
                phases.append(phase)
                return 0, f"{phase} passed\nFACTORY_ROLE_VERDICT: PASS"

            factory.run_adapter = successful_role
            self.assertEqual(factory.run_assured_roles(ticket, repo, head), "")
            self.assertEqual(factory.run_final_verifier(ticket, repo, head), "")
            self.assertEqual(
                phases,
                ["cleanup", "architecture_conformance", "hardening", "final_verifier"],
            )
            receipts = [json.loads((repo / path).read_text()) for path in ticket["receipts"]]
            self.assertEqual(
                [item["role"] for item in receipts],
                ["cleanup", "architecture_conformance", "hardening", "final_verifier"],
            )
            self.assertEqual(receipts[1]["phase"], "Verify")
            self.assertEqual(receipts[-1]["phase"], "Verify")

            correction_phases = []

            def corrected_final_verdict(agent, active_ticket, worktree, prompt, log_name, phase):
                correction_phases.append(phase)
                if len(correction_phases) == 1:
                    return 0, "Contract C4 is not enforced.\nFACTORY_ROLE_VERDICT: BLOCK: C4 is missing"
                if phase == "hardening":
                    self.assertIn("Final Verifier blocked: C4 is missing", prompt.read_text())
                return 0, "Correction verified.\nFACTORY_ROLE_VERDICT: PASS"

            factory.cfg["gate"] = [{"name": "tests", "cmd": "true", "required": True}]
            factory.run_adapter = corrected_final_verdict
            self.assertEqual(factory.run_final_verifier(ticket, repo, head), "")
            self.assertEqual(
                correction_phases,
                ["final_verifier", "hardening", "final_verifier"],
            )

            blocked_phases = []

            def blocked_conformance(agent, active_ticket, worktree, prompt, log_name, phase):
                blocked_phases.append(phase)
                if phase == "architecture_conformance":
                    return 0, "Contract C2 drifted.\nFACTORY_ROLE_VERDICT: BLOCK: C2 drifted"
                return 0, "Role passed.\nFACTORY_ROLE_VERDICT: PASS"

            factory.run_adapter = blocked_conformance
            failure = factory.run_assured_roles(ticket, repo, head)
            self.assertIn("Architecture Conformance blocked: C2 drifted", failure)
            self.assertEqual(blocked_phases, ["cleanup", "architecture_conformance"])
            blocked_receipt = json.loads((repo / ticket["receipts"][-1]).read_text())
            self.assertEqual(blocked_receipt["role"], "architecture_conformance")
            self.assertEqual(blocked_receipt["claimed_result"], "Architecture Conformance blocked")


if __name__ == "__main__":
    unittest.main()
