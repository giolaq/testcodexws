import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).parents[1]))

from code_review import CodeReviewError, extract_review, render_review_comment, validate_review
from factory_charter import FactoryCharter
from orchestrator import Factory
from project_contract import ProjectContract


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, text=True, capture_output=True, check=True,
    ).stdout.strip()


class CodeReviewTests(unittest.TestCase):
    def test_live_smoke_review_fixture_requests_one_changed_path_rework(self):
        with tempfile.TemporaryDirectory() as directory:
            prompt = Path(directory) / "review.md"
            prompt.write_text(
                "## Ticket\nfactory-release-smoke:review-rework\n\n"
                "## Changed paths\n\n- `demo-app/app.py`\n- `demo-app/tests/test_ticket_9.py`\n\n"
                "## Recorded gates\n\n- tests: PASS\n"
            )
            script = Path(__file__).parents[1] / "mock_review_agent.py"
            first = subprocess.run(
                [sys.executable, str(script), "9", str(prompt), "--attempt", "1"],
                text=True, capture_output=True, check=True,
            )
            second = subprocess.run(
                [sys.executable, str(script), "9", str(prompt), "--attempt", "2"],
                text=True, capture_output=True, check=True,
            )

            requested = json.loads(first.stdout)
            approved = json.loads(second.stdout)
            self.assertEqual(requested["decision"], "REQUEST_CHANGES")
            self.assertEqual(requested["findings"][0]["path"], "demo-app/app.py")
            self.assertEqual(approved["decision"], "APPROVE")

    def test_extracts_and_validates_last_json_result(self):
        raw = extract_review('progress\n{"ignored":true}\n{"schema_version":2,"decision":"APPROVE","summary":"Ready.","findings":[]}')
        review = validate_review(raw, {"demo-app/app.py"})
        self.assertEqual(review["decision"], "APPROVE")

    def test_block_requires_blocking_finding_on_changed_path(self):
        payload = {
            "schema_version": 2,
            "decision": "REQUEST_CHANGES",
            "summary": "A regression remains.",
            "findings": [{
                "severity": "blocking",
                "path": "demo-app/app.py",
                "line": 12,
                "message": "The error branch returns a successful status.",
            }],
        }
        review = validate_review(
            extract_review("adapter output\n" + json.dumps(payload)), {"demo-app/app.py"},
        )
        self.assertEqual(review["findings"][0]["line"], 12)

    def test_rejects_unchanged_or_traversing_path(self):
        for path in ("README.md", "../demo-app/app.py"):
            with self.subTest(path=path), self.assertRaises(CodeReviewError):
                validate_review({
                    "schema_version": 2,
                    "decision": "REQUEST_CHANGES",
                    "summary": "Unsafe finding.",
                    "findings": [{
                        "severity": "blocking", "path": path, "line": None, "message": "Problem.",
                    }],
                }, {"demo-app/app.py"})

    def test_approve_rejects_any_comment(self):
        with self.assertRaisesRegex(CodeReviewError, "APPROVE"):
            validate_review({
                "schema_version": 2,
                "decision": "APPROVE",
                "summary": "Contradictory.",
                "findings": [{
                    "severity": "blocking", "path": "app.py", "line": 1, "message": "Problem.",
                }],
            }, {"app.py"})

    def test_renders_supervisor_merge_boundary(self):
        comment = render_review_comment({
            "decision": "APPROVE", "summary": "Ready for @team.", "findings": [],
        }, 7, 2)
        self.assertIn("Factory Code Review · APPROVE", comment)
        self.assertIn("Supervisor may recommend only this approved revision", comment)
        self.assertIn("human exact-revision merge", comment)
        self.assertNotIn("@team", comment)

    def test_orchestrator_records_blocking_review_without_mutating_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            source = Path(__file__).parents[1]
            (repo / "factory").mkdir()
            for name in ("roles.json", "policy.json"):
                shutil.copy2(source / name, repo / "factory" / name)
            (repo / ".gitignore").write_text(".factory/\n")
            git(repo, "init", "-q", "-b", "main")
            git(repo, "config", "user.name", "Factory Test")
            git(repo, "config", "user.email", "factory@example.test")
            (repo / "app.py").write_text("value = 1\n")
            project = ProjectContract.detect(repo)
            project.write()
            charter = FactoryCharter.draft(repo, project)
            charter.write()
            charter.approve()
            git(repo, "add", ".")
            git(repo, "commit", "-qm", "base")
            base = git(repo, "rev-parse", "HEAD")
            (repo / "app.py").write_text("value = 2\n")
            git(repo, "add", "app.py")
            git(repo, "commit", "-qm", "candidate")

            factory = Factory.__new__(Factory)
            factory.repo = repo
            factory.review_agent = "reviewer"
            factory.args = SimpleNamespace(scenario="tv", mock=False)
            factory.record_receipt = mock.Mock()
            factory.verify_qa_tests_unchanged = mock.Mock(return_value="")
            response = json.dumps({
                "schema_version": 2,
                "decision": "REQUEST_CHANGES",
                "summary": "The candidate changes the public value unexpectedly.",
                "findings": [{
                    "severity": "blocking",
                    "path": "app.py",
                    "line": 1,
                    "message": "Preserve the documented value contract.",
                }],
            })
            factory.run_adapter = mock.Mock(return_value=(0, response))
            ticket = {
                "number": 4, "title": "Preserve value", "body": "## Spec\nKeep the value stable.",
                "attempt": 1, "gate_results": [], "qa_tests": {}, "current_log": "",
            }

            failure = factory.run_code_review(ticket, repo, base, "https://example.test/pull/4")

            self.assertIn("Code Review requested changes", failure)
            self.assertEqual(ticket["code_review"]["result"]["decision"], "REQUEST_CHANGES")
            self.assertTrue((repo / ticket["code_review"]["artifact"]).is_file())
            factory.record_receipt.assert_called_once()
            self.assertEqual(git(repo, "status", "--porcelain"), "")


if __name__ == "__main__":
    unittest.main()
