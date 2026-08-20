import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).parents[1]))

from control_center import ControlCenter, ControlCenterServer, InputError
from orchestrator import parser


class ControlCenterTests(unittest.TestCase):
    def make_repo(self, directory: str) -> Path:
        repo = Path(directory)
        (repo / "factory/control_center").mkdir(parents=True)
        factory = repo / "factory/factory"
        factory.write_text("#!/bin/sh\nprintf 'factory args: %s\\n' \"$*\"\n")
        factory.chmod(0o755)
        (repo / "factory/factory.toml").write_text(
            "[agents]\nmy-agent = './tools/my-agent {prompt}'\n"
        )
        (repo / "factory/FACTORY_CANVAS.md").write_text("# Factory Canvas\n")
        return repo

    def test_parser_exposes_loopback_control_center(self):
        args = parser().parse_args(["control-center", "--no-open"])

        self.assertEqual(args.host, "127.0.0.1")
        self.assertEqual(args.port, 5050)
        self.assertTrue(args.no_open)

    def test_configuration_is_allowlisted_and_never_uses_a_shell_command(self):
        with tempfile.TemporaryDirectory() as directory:
            center = ControlCenter(self.make_repo(directory))

            title, commands = center.build_commands("configure", {
                "profile": "standard",
                "planning_agent": "claude",
                "agent": "my-agent",
                "qa_agent": "codex",
                "review_qa_tests": True,
                "max_parallel": 2,
            })

            self.assertEqual(title, "Save factory configuration")
            self.assertIsInstance(commands[0], list)
            self.assertIn("my-agent", commands[0])
            self.assertIn("--review-qa-tests", commands[0])
            self.assertNotIn("sh", commands[0])

            with self.assertRaisesRegex(InputError, "Unknown agent adapter"):
                center.build_commands("configure", {"agent": "codex; rm -rf repo"})

    def test_planning_requires_a_saved_prd_and_uses_mock_explicitly(self):
        with tempfile.TemporaryDirectory() as directory:
            center = ControlCenter(self.make_repo(directory))
            with self.assertRaisesRegex(InputError, "Save the PRD"):
                center.build_commands("plan", {"mode": "rehearsal"})

            center.save_prd("# Recipe app\n\nBuild a recipe discovery experience.")
            _, commands = center.build_commands("plan", {
                "mode": "rehearsal", "profile": "standard",
            })

            self.assertEqual(commands[0][1], "plan")
            self.assertIn(str(center.prd_path), commands[0])
            self.assertIn("--mock", commands[0])

    def test_human_gate_commands_are_noninteractive(self):
        with tempfile.TemporaryDirectory() as directory:
            center = ControlCenter(self.make_repo(directory))
            plan = "a" * 12

            _, product = center.build_commands("approve-product", {"plan_id": plan})
            _, tests = center.build_commands("approve-tests", {"issue": 7})
            _, publish = center.build_commands("publish-plan", {
                "plan_id": plan, "mode": "rehearsal", "scenario": "recipe-rebrand",
            })

            self.assertIn("--yes", product[0])
            self.assertIn("--yes", tests[0])
            self.assertIn("--yes", publish[0])
            self.assertIn("approve-rehearsal", publish[0])

    def test_reset_actions_are_rehearsal_only_and_full_reset_requires_a_phrase(self):
        with tempfile.TemporaryDirectory() as directory:
            center = ControlCenter(self.make_repo(directory))
            (center.repo / "setup_demo.sh").write_text("#!/bin/sh\n")

            _, run_reset = center.build_commands("reset-run", {"mode": "rehearsal"})
            self.assertIn("--scenario", run_reset[0])
            self.assertNotIn("--start-over", run_reset[0])

            with self.assertRaisesRegex(InputError, "START OVER"):
                center.build_commands("reset-all", {"mode": "rehearsal"})
            _, full_reset = center.build_commands("reset-all", {
                "mode": "rehearsal", "confirm": "START OVER",
            })
            self.assertIn("--start-over", full_reset[0])

            with self.assertRaisesRegex(InputError, "fresh workshop repository"):
                center.build_commands("reset-run", {"mode": "live"})

    def test_live_publication_reuses_the_saved_github_project(self):
        with tempfile.TemporaryDirectory() as directory:
            center = ControlCenter(self.make_repo(directory))
            local = center.repo / ".factory/local.toml"
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_text("project_number = 42\n")

            _, commands = center.build_commands("publish-plan", {
                "plan_id": "a" * 12,
                "mode": "live",
                "project_title": "Ignored when a Project is connected",
            })

            self.assertIn("--project-number", commands[0])
            self.assertIn("42", commands[0])
            self.assertNotIn("--new-project-title", commands[0])

    def test_artifacts_cannot_escape_factory_evidence_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            center = ControlCenter(self.make_repo(directory))
            log = center.repo / ".factory/logs/agent.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            log.write_text("safe log\n")

            self.assertEqual(center.artifact(".factory/logs/agent.log"), "safe log\n")
            with self.assertRaisesRegex(InputError, "Invalid artifact path"):
                center.artifact("../private-key")
            with self.assertRaisesRegex(InputError, "Only factory evidence"):
                center.artifact(".factory/local.toml")

            private = center.repo / ".factory/local.toml"
            private.write_text("secret = 'not for the browser'\n")
            (center.repo / ".factory/logs/private-link").symlink_to(private)
            with self.assertRaisesRegex(InputError, "Artifact not found"):
                center.artifact(".factory/logs/private-link")

    def test_operation_runner_streams_an_allowlisted_command(self):
        with tempfile.TemporaryDirectory() as directory:
            center = ControlCenter(self.make_repo(directory))

            operation = center.start("doctor", {"full": True})
            deadline = time.monotonic() + 2
            while center.operation_snapshot().get("status") == "running" and time.monotonic() < deadline:
                time.sleep(0.01)
            finished = center.operation_snapshot()

            self.assertEqual(operation["action"], "doctor")
            self.assertEqual(finished["status"], "succeeded")
            self.assertIn("factory args: doctor --full", finished["output"])

    def test_http_api_serves_state_and_rejects_foreign_origins(self):
        with tempfile.TemporaryDirectory() as directory:
            center = ControlCenter(self.make_repo(directory))
            server = ControlCenterServer(("127.0.0.1", 0), center)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            try:
                with urlopen(base + "/api/snapshot", timeout=2) as response:
                    snapshot = json.load(response)
                self.assertEqual(snapshot["repo"]["name"], Path(directory).name)

                request = Request(
                    base + "/api/prd",
                    data=json.dumps({"text": "# Safe PRD"}).encode(),
                    headers={"Content-Type": "application/json"},
                    method="PUT",
                )
                with urlopen(request, timeout=2) as response:
                    saved = json.load(response)
                self.assertTrue(saved["saved"])

                foreign = Request(base + "/api/snapshot", headers={"Origin": "https://example.com"})
                try:
                    urlopen(foreign, timeout=2)
                except HTTPError as error:
                    self.assertEqual(error.code, 400)
                    error.close()
                else:
                    self.fail("A foreign origin must not access the Control Center")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_snapshot_combines_planning_ticket_and_operation_state(self):
        with tempfile.TemporaryDirectory() as directory:
            center = ControlCenter(self.make_repo(directory))
            (center.repo / ".factory/planning-state.json").write_text(json.dumps({"plan_id": "abc12345"}))
            (center.repo / ".factory/state.json").write_text(json.dumps({"tickets": [{"number": 1, "status": "Done"}]}))

            snapshot = center.snapshot()

            self.assertEqual(snapshot["planning"]["plan_id"], "abc12345")
            self.assertEqual(snapshot["factory"]["tickets"][0]["status"], "Done")
            self.assertIn("adapters", snapshot)
            self.assertIn("operation", snapshot)
            self.assertEqual(snapshot["journey"]["phase_label"], "Plan")

    def test_journey_names_the_active_role_and_human_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            center = ControlCenter(self.make_repo(directory))
            planning = {
                "plan_id": "abc12345",
                "status": "alignment_approved",
                "approvals": {"product": {"at": "now"}, "alignment": {"at": "now"}},
            }
            prd = {"saved": True}
            active_factory = {"tickets": [{
                "number": 3, "title": "Recipe details", "status": "In Progress",
                "phase": "qa", "qa_attempt": 1,
            }]}
            running = {"status": "running", "action": "run", "title": "Run the factory"}

            active = center.journey(planning, active_factory, running, prd, [])
            self.assertEqual(active["phase_label"], "Build & verify")
            self.assertEqual(active["ticket"], 3)
            self.assertIn("Independent QA", active["headline"])

            active_factory["tickets"][0]["status"] = "QA Review"
            review = center.journey(planning, active_factory, running, prd, [])
            self.assertEqual(review["state"], "attention")
            self.assertIn("need approval", review["headline"])
            self.assertEqual(review["next"]["view"], "tickets")

    def test_frontend_contains_the_complete_operator_workflow(self):
        source = (Path(__file__).parents[1] / "control_center/index.html").read_text()

        for label in (
            "Connect the factory",
            "Define the outcome",
            "Review the plan",
            "Operate the factory",
            "Verify the result",
            "Live log",
            "Diff",
            "Factory Canvas",
            "Current phase",
            "Reset or start again",
            "Start workshop over",
        ):
            self.assertIn(label, source)


if __name__ == "__main__":
    unittest.main()
