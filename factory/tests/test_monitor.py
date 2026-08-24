import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parents[1]))

from factory_charter import FactoryCharter
from monitor import FactoryMonitor
from project_contract import ProjectContract


class MonitorTests(unittest.TestCase):
    def test_monitor_is_read_only_and_finds_review_pressure_and_repetition(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
            project = ProjectContract.detect(repo); project.write()
            charter = FactoryCharter.draft(repo, project); charter.write(); charter.approve()
            state = {
                "human_attention": {"dispatch_paused": True, "reason": "human review queue 3 / limit 3"},
                "tickets": [
                    {"code_review": {"result": {"findings": [{"message": "Missing boundary test"}]}}},
                    {"code_review": {"result": {"findings": [{"message": "Missing boundary test"}]}}},
                ],
            }
            runtime = repo / ".factory"; runtime.mkdir()
            (runtime / "state.json").write_text(json.dumps(state))
            before = subprocess.run(["git", "status", "--porcelain"], cwd=repo, text=True, capture_output=True).stdout

            report = FactoryMonitor(repo).collect()
            after = subprocess.run(["git", "status", "--porcelain"], cwd=repo, text=True, capture_output=True).stdout

            self.assertEqual(before, after)
            self.assertEqual(report["mode"], "read-only")
            self.assertIn("review-wait", {item["kind"] for item in report["findings"]})
            self.assertIn("repeated-verifier-finding", {item["kind"] for item in report["findings"]})

    def test_monitor_publication_updates_the_same_finding(self):
        backend = mock.Mock()
        backend.owner, backend.name = "attendee", "project"
        finding = {"id": "abc123", "summary": "CI failed", "detail": "One run failed."}
        backend.json.return_value = [{
            "number": 9, "url": "https://github.test/issues/9",
            "body": "<!-- factory-monitor:v1 id=abc123 -->\nold",
        }]

        published = FactoryMonitor(Path.cwd(), backend).publish({"findings": [finding]})

        self.assertEqual(published[0]["mode"], "updated")
        self.assertEqual(backend.gh.call_args.args[:3], ("issue", "edit", 9))

    def test_monitor_finds_a_stale_remote_claim_without_releasing_it(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "Factory Test"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.email", "factory@example.test"], cwd=repo, check=True)
            project = ProjectContract.detect(repo); project.write()
            charter = FactoryCharter.draft(repo, project); charter.write(); charter.approve()
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-qm", "base"], cwd=repo, check=True)
            backend = mock.Mock()
            backend.load.return_value = [{"number": 7, "status": "Done", "state": "CLOSED"}]
            backend._git.return_value = subprocess.CompletedProcess(
                ["git"], 0, "abc refs/heads/factory-claims/ticket-7\n", "",
            )
            backend.read_claim.return_value = {
                "ticket": 7, "run_id": "run-1", "base_revision": "abc1234",
                "claimed_at": "2026-08-20T00:00:00+00:00",
            }
            backend.json.side_effect = [[], []]

            report = FactoryMonitor(repo, backend).collect()

            self.assertIn("stale-claim", {item["kind"] for item in report["findings"]})
            backend.release_claim.assert_not_called()
            self.assertIn("--branch", backend.json.call_args_list[0].args)
            self.assertIn("main", backend.json.call_args_list[0].args)

    def test_monitor_reports_stale_blocked_ticket_and_review_wait(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
            project = ProjectContract.detect(repo); project.write()
            charter = FactoryCharter.draft(repo, project); charter.write(); charter.approve()
            backend = mock.Mock()
            backend.load.return_value = [
                {"number": 4, "status": "Blocked", "updatedAt": "2000-01-01T00:00:00Z"},
                {"number": 5, "status": "In Review", "updatedAt": "2000-01-01T00:00:00Z"},
            ]
            backend._git.return_value = subprocess.CompletedProcess(["git"], 0, "", "")
            backend.json.side_effect = [[], []]

            report = FactoryMonitor(repo, backend).collect()

            kinds = {item["kind"] for item in report["findings"]}
            self.assertIn("stale-ticket", kinds)
            self.assertIn("review-wait", kinds)

    def test_latest_success_clears_an_older_failure_for_the_same_workflow(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
            project = ProjectContract.detect(repo); project.write()
            charter = FactoryCharter.draft(repo, project); charter.write(); charter.approve()
            backend = mock.Mock()
            backend.load.return_value = []
            backend._git.return_value = subprocess.CompletedProcess(["git"], 0, "", "")
            backend.default_branch = "main"
            backend.owner, backend.name = "attendee", "project"
            backend.json.side_effect = [
                [
                    {
                        "databaseId": 2,
                        "workflowName": "Factory rehearsal",
                        "status": "completed",
                        "conclusion": "success",
                    },
                    {
                        "databaseId": 1,
                        "workflowName": "Factory rehearsal",
                        "status": "completed",
                        "conclusion": "failure",
                    },
                ],
                [],
            ]

            report = FactoryMonitor(repo, backend).collect()

            self.assertNotIn(
                "default-branch-ci",
                {item["kind"] for item in report["findings"]},
            )
            self.assertEqual(len(report["ci"]), 2)


if __name__ == "__main__":
    unittest.main()
