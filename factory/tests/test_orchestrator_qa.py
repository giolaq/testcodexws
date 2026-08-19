import sys
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parents[1]))

from orchestrator import DEFAULT_AGENTS, Factory, validate_qa_changes, validate_qa_config


TEST_ROOTS = ["demo-app/tests", "demo-app/static/tests"]


class QaPolicyTests(unittest.TestCase):
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

            prompt = factory.make_prompt(ticket, "").read_text()
            self.assertIn("Independent QA acceptance tests", prompt)
            self.assertIn("Git hashes", prompt)

            protected = repo / "demo-app/tests/test_ticket_42_search.py"
            protected.write_text("def test_recipe_search_acceptance():\n    assert False\n")
            self.assertIn("was modified", factory.verify_qa_tests_unchanged(ticket, repo))


if __name__ == "__main__":
    unittest.main()
