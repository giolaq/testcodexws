import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).parents[1]))

from control_center import ControlCenter, ControlCenterServer, InputError, planning_recovery
from factory_charter import FactoryCharter
from orchestrator import parser
from project_contract import ProjectContract


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

    def write_plan_manifest(self, center: ControlCenter, plan: str, planning_agent: str):
        run = center.repo / ".factory/plans" / plan
        run.mkdir(parents=True, exist_ok=True)
        (run / "manifest.json").write_text(json.dumps({
            "plan_id": plan,
            "planning_agent": planning_agent,
        }))

    def test_parser_exposes_loopback_control_center(self):
        args = parser().parse_args(["control-center", "--no-open"])

        self.assertEqual(args.host, "127.0.0.1")
        self.assertEqual(args.port, 5050)
        self.assertTrue(args.no_open)

    def test_external_repository_uses_the_bundled_control_plane_and_can_be_initialized(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
            (repo / "src").mkdir()
            (repo / "src/main.py").write_text("print('hello')\n")

            center = ControlCenter(repo)
            title, commands = center.build_commands("init-project", {})
            snapshot = center.snapshot()

            self.assertEqual(title, "Initialize Project Contract")
            self.assertIn(str(repo.resolve()), commands[0])
            self.assertTrue(center.factory.is_file())
            self.assertNotEqual(center.factory, repo / "factory/factory")
            self.assertEqual(snapshot["project"]["source_roots"], ["src"])
            self.assertFalse(snapshot["project"]["configured"])

    def test_charter_is_a_visible_explicit_human_gate_before_planning(self):
        with tempfile.TemporaryDirectory() as directory:
            center = ControlCenter(self.make_repo(directory))
            project = ProjectContract.detect(center.repo)
            project.write()
            FactoryCharter.draft(center.repo, project).write()

            draft = center.snapshot()
            title, commands = center.build_commands("approve-charter", {})

            self.assertTrue(draft["charter"]["configured"])
            self.assertFalse(draft["charter"]["approved"])
            self.assertEqual(draft["journey"]["next"]["label"], "Review Factory Charter")
            self.assertEqual(title, "Approve Factory Charter")
            self.assertIn("approve-charter", commands[0])
            self.assertIn("--yes", commands[0])

            FactoryCharter.load(center.repo).approve()
            approved = center.snapshot()
            self.assertTrue(approved["charter"]["approved"])
            self.assertNotEqual(approved["charter"]["policy_sha256"], "")

            publish_title, publish_commands = center.build_commands("publish-setup", {})
            self.assertEqual(publish_title, "Publish repository setup")
            self.assertIn("publish-setup", publish_commands[0])
            self.assertIn("--yes", publish_commands[0])

    def test_monitor_actions_are_registered_and_publication_is_live_only(self):
        with tempfile.TemporaryDirectory() as temp:
            center = ControlCenter(self.make_repo(temp))
            title, commands = center.build_commands("monitor", {"mode": "rehearsal"})
            self.assertEqual(title, "Preview repository health")
            self.assertIn("monitor", commands[0])
            self.assertIn("--json", commands[0])
            with self.assertRaises(InputError):
                center.build_commands("publish-monitor", {"mode": "rehearsal"})
            title, commands = center.build_commands("publish-monitor", {"mode": "live"})
            self.assertEqual(title, "Publish monitor findings")
            self.assertIn("--publish", commands[0])

    def test_configuration_is_allowlisted_and_never_uses_a_shell_command(self):
        with tempfile.TemporaryDirectory() as directory:
            center = ControlCenter(self.make_repo(directory))

            title, commands = center.build_commands("configure", {
                "profile": "standard",
                "planning_agent": "claude",
                "agent": "my-agent",
                "qa_agent": "codex",
                "supervisor_agent": "my-agent",
                "review_agent": "my-agent",
                "review_qa_tests": True,
                "max_parallel": 2,
            })

            self.assertEqual(title, "Save factory configuration")
            self.assertIsInstance(commands[0], list)
            self.assertIn("my-agent", commands[0])
            self.assertIn("--supervisor-agent", commands[0])
            self.assertIn("--review-agent", commands[0])
            self.assertIn("--review-qa-tests", commands[0])
            self.assertNotIn("sh", commands[0])

            with self.assertRaisesRegex(InputError, "Unknown agent adapter"):
                center.build_commands("configure", {"agent": "codex; rm -rf repo"})

    def test_live_configuration_requires_and_connects_an_explicit_repository_url(self):
        with tempfile.TemporaryDirectory() as directory:
            center = ControlCenter(self.make_repo(directory))

            with self.assertRaisesRegex(InputError, "repository URL"):
                center.build_commands("configure", {
                    "mode": "live", "preset": "claude-workshop",
                })
            _, commands = center.build_commands("configure", {
                "mode": "live",
                "preset": "claude-workshop",
                "github_repository": "git@github.com:attendee/workshop.git",
            })

            self.assertEqual(commands[0][1], "checkout")
            self.assertIn("https://github.com/attendee/workshop", commands[0])
            self.assertIn("--github-repository", commands[1])
            self.assertIn("https://github.com/attendee/workshop", commands[1])
            self.assertIn("--repo", commands[1])

    def test_successful_live_configuration_activates_the_managed_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            host = self.make_repo(directory)
            factory = host / "factory/factory"
            factory.write_text(
                "#!/bin/sh\n"
                "if [ \"$1\" = checkout ]; then\n"
                "  shift 2\n"
                "  shift\n"
                "  mkdir -p \"$1/attendee/workshop/.git\"\n"
                "fi\n"
                "printf 'factory args: %s\\n' \"$*\"\n"
            )
            factory.chmod(0o755)
            center = ControlCenter(host)

            center.start("configure", {
                "mode": "live",
                "preset": "claude-workshop",
                "github_repository": "https://github.com/attendee/workshop",
            })
            deadline = time.monotonic() + 3
            while center.operation_snapshot().get("status") == "running" and time.monotonic() < deadline:
                time.sleep(0.02)

            target = center.repository_root / "attendee/workshop"
            self.assertEqual(center.operation_snapshot()["status"], "succeeded")
            self.assertEqual(center.repo, target.resolve())
            self.assertEqual(ControlCenter(host).repo, target.resolve())

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

    def test_planning_uses_the_profile_saved_for_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            center = ControlCenter(self.make_repo(directory))
            local = center.repo / ".factory/local.toml"
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_text('profile = "lean"\n')
            center.save_prd("# Recipe app\n")

            _, commands = center.build_commands("plan", {
                "mode": "rehearsal", "profile": "assured",
            })

            self.assertIn("lean", commands[0])
            self.assertNotIn("assured", commands[0])

    def test_autonomous_demo_requires_a_transient_visible_opt_in_for_plan_and_run(self):
        with tempfile.TemporaryDirectory() as directory:
            center = ControlCenter(self.make_repo(directory))
            local = center.repo / ".factory/local.toml"
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_text('profile = "autonomous-demo"\n')
            center.save_prd("# Deliberately autonomous workshop contrast\n")

            for action in ("plan", "run"):
                with self.subTest(action=action):
                    with self.assertRaisesRegex(InputError, "delegates final merge accountability"):
                        center.build_commands(action, {"mode": "rehearsal"})
                    _, commands = center.build_commands(action, {
                        "mode": "rehearsal",
                        "allow_autonomous_merge": True,
                    })
                    self.assertIn("--allow-autonomous-merge", commands[0])

            html = (Path(__file__).parents[1] / "control_center/index.html").read_text()
            javascript = (Path(__file__).parents[1] / "control_center/app.js").read_text()
            self.assertIn('value="autonomous-demo"', html)
            self.assertIn('id="autonomous-merge-opt-in"', html)
            self.assertIn("delegates final merge accountability", html)
            self.assertIn("allow_autonomous_merge", javascript)

    def test_human_gate_commands_are_noninteractive(self):
        with tempfile.TemporaryDirectory() as directory:
            center = ControlCenter(self.make_repo(directory))
            plan = "a" * 12
            self.write_plan_manifest(center, plan, "mock")

            _, product = center.build_commands("approve-product", {"plan_id": plan})
            _, tests = center.build_commands("approve-tests", {"issue": 7})
            _, merge = center.build_commands("merge", {"issue": 7, "mode": "rehearsal"})
            _, publish = center.build_commands("publish-plan", {
                "plan_id": plan, "mode": "rehearsal", "scenario": "recipe-rebrand",
            })

            self.assertIn("--yes", product[0])
            self.assertIn("--yes", tests[0])
            self.assertIn("--yes", merge[0])
            self.assertIn("--mock", merge[0])
            self.assertIn("--yes", publish[0])
            self.assertIn("approve-rehearsal", publish[0])

    def test_charter_selected_expert_gate_has_a_validated_control_center_action(self):
        with tempfile.TemporaryDirectory() as directory:
            center = ControlCenter(self.make_repo(directory))
            self.write_plan_manifest(center, "a1b2c3d4", "mock")

            title, commands = center.build_commands("approve-stage", {
                "plan_id": "a1b2c3d4",
                "stage": "system_architecture",
            })

            self.assertEqual(title, "Approve System Architecture")
            self.assertEqual(
                commands[0][-4:],
                ["approve-stage", "architecture", "a1b2c3d4", "--yes"],
            )
            with self.assertRaisesRegex(InputError, "[Aa]rchitecture or program"):
                center.build_commands("approve-stage", {
                    "plan_id": "a1b2c3d4",
                    "stage": "vertical_slices",
                })

    def test_journey_names_a_charter_selected_intermediate_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            center = ControlCenter(self.make_repo(directory))
            planning = {
                "plan_id": "a" * 12,
                "status": "awaiting_system_architecture_approval",
                "approvals": {"product": {"artifact_sha256": "a" * 64}},
                "stages": [],
            }

            journey = center.journey(
                planning, {"tickets": []}, {}, {"saved": True}, [],
            )

            self.assertEqual(journey["headline"], "System Architecture needs your approval")
            self.assertEqual(journey["next"]["label"], "Review System Architecture")
            self.assertEqual(journey["next"]["view"], "planning")

    def test_blocked_planning_can_retry_with_another_live_adapter(self):
        with tempfile.TemporaryDirectory() as directory:
            center = ControlCenter(self.make_repo(directory))
            plan = "a" * 12
            self.write_plan_manifest(center, plan, "claude")

            title, commands = center.build_commands("continue-plan", {
                "plan_id": plan,
                "planning_agent": "codex",
            })

            self.assertEqual(title, "Run architecture and delivery planning")
            self.assertEqual(commands[0][-2:], ["--planning-agent", "codex"])
            with self.assertRaisesRegex(InputError, "Claude or Codex"):
                center.build_commands("continue-plan", {
                    "plan_id": plan,
                    "planning_agent": "cursor",
                })

    def test_blocked_expert_decisions_revise_the_stage_then_resume_planning(self):
        with tempfile.TemporaryDirectory() as directory:
            center = ControlCenter(self.make_repo(directory))
            plan = "a" * 12
            self.write_plan_manifest(center, plan, "claude")

            title, commands = center.build_commands("revise-stage", {
                "plan_id": plan,
                "mode": "rehearsal",
                "stage": "system_architecture",
                "feedback": "Use this repository and keep analytics disabled for v1.",
            })

            self.assertEqual(title, "Resolve System Architecture decisions")
            self.assertEqual(len(commands), 2)
            self.assertEqual(commands[0][1:4], ["revise", plan, "architecture"])
            self.assertIn("--feedback-file", commands[0])
            self.assertEqual(commands[1][1:], ["continue-plan", plan])
            self.assertNotIn("--mock", commands[0])
            self.assertNotIn("--mock", commands[1])

            with self.assertRaisesRegex(InputError, "blocked technical"):
                center.build_commands("revise-stage", {
                    "plan_id": plan,
                    "stage": "product_review",
                    "feedback": "Answer",
                })

    def test_many_product_blocking_decisions_use_a_compact_feedback_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            center = ControlCenter(self.make_repo(directory))
            plan = "a" * 12
            self.write_plan_manifest(center, plan, "claude")
            questions = [
                f"Question {index}: " + ("Clarify this product decision. " * 8)
                for index in range(1, 21)
            ]
            planning_state = center.repo / ".factory/planning-state.json"
            planning_state.write_text(json.dumps({
                "plan_id": plan,
                "status": "blocked",
                "stages": [{
                    "id": "product_review",
                    "status": "blocked",
                    "questions": questions,
                }],
            }))
            decisions = [
                f"Use the documented default for decision {index}."
                for index in range(1, 21)
            ]

            title, commands = center.build_commands("revise-product", {
                "plan_id": plan,
                "decisions": decisions,
            })

            feedback_path = Path(commands[0][commands[0].index("--feedback-file") + 1])
            feedback = feedback_path.read_text()
            self.assertEqual(title, "Revise Product Review")
            self.assertIn("1. Use the documented default for decision 1.", feedback)
            self.assertIn("20. Use the documented default for decision 20.", feedback)
            self.assertNotIn(questions[0], feedback)
            self.assertLess(len(feedback), 4000)

    def test_legacy_product_question_payload_has_room_for_normal_answers(self):
        with tempfile.TemporaryDirectory() as directory:
            center = ControlCenter(self.make_repo(directory))
            plan = "a" * 12
            self.write_plan_manifest(center, plan, "claude")
            feedback = "\n".join(
                f"{index}. Question: {'Clarify this product decision. ' * 8}\n"
                f"Decision: Use the documented default for decision {index}."
                for index in range(1, 21)
            )

            title, commands = center.build_commands("revise-product", {
                "plan_id": plan,
                "feedback": feedback,
            })

            self.assertEqual(title, "Revise Product Review")
            self.assertIn("--feedback-file", commands[0])

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

            title, live_local_reset = center.build_commands("reset-run", {
                "mode": "live", "local_only": True, "scenario": "recipe-rebrand",
            })
            self.assertEqual(title, "Reset local Live Run state")
            self.assertIn("--scenario", live_local_reset[0])
            self.assertIn("--local-state-only", live_local_reset[0])

            _, live_local_start_over = center.build_commands("reset-all", {
                "mode": "live", "local_only": True,
                "scenario": "recipe-rebrand", "confirm": "START OVER",
            })
            self.assertIn("--start-over", live_local_start_over[0])

    def test_live_publication_reuses_the_saved_github_project(self):
        with tempfile.TemporaryDirectory() as directory:
            center = ControlCenter(self.make_repo(directory))
            local = center.repo / ".factory/local.toml"
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_text("project_number = 42\n")
            self.write_plan_manifest(center, "a" * 12, "claude")

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

    def test_shutdown_stops_and_joins_an_active_factory_process(self):
        with tempfile.TemporaryDirectory() as directory:
            center = ControlCenter(self.make_repo(directory))
            factory = center.repo / "factory/factory"
            factory.write_text("#!/bin/sh\nprintf 'started\\n'\nsleep 30\n")

            center.start("doctor", {})
            deadline = time.monotonic() + 2
            while center.process is None and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertIsNotNone(center.process)

            center.shutdown(timeout=2)

            self.assertIsNone(center.process)
            self.assertIsNone(center.worker)
            self.assertEqual(center.operation_snapshot()["status"], "stopped")

    def test_restart_recovers_an_operation_interrupted_while_stopping(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = self.make_repo(directory)
            center = ControlCenter(repo)
            center.operation_path.write_text(json.dumps({"status": "stopping"}))

            recovered = ControlCenter(repo).operation_snapshot()

            self.assertEqual(recovered["status"], "interrupted")
            self.assertIn("restarted while this operation was running", recovered["error"])

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
            project = ProjectContract.detect(center.repo)
            project.write()
            charter = FactoryCharter.draft(center.repo, project)
            charter.write()
            charter.approve()
            (center.repo / ".factory/planning-state.json").write_text(json.dumps({"plan_id": "abc12345"}))
            (center.repo / ".factory/state.json").write_text(json.dumps({"tickets": [{"number": 1, "status": "Done"}]}))
            supervisor = center.repo / ".factory/supervisor/state.json"
            supervisor.parent.mkdir(parents=True)
            supervisor.write_text(json.dumps({"status": "ready", "latest": {"id": "supervisor-1"}}))

            snapshot = center.snapshot()

            self.assertEqual(snapshot["planning"]["plan_id"], "abc12345")
            self.assertEqual(snapshot["factory"]["tickets"][0]["status"], "Done")
            self.assertIn("adapters", snapshot)
            self.assertIn("operation", snapshot)
            self.assertEqual(snapshot["supervisor"]["latest"]["id"], "supervisor-1")
            self.assertEqual(snapshot["journey"]["phase_label"], "Plan")

    def test_snapshot_uses_the_plan_manifest_as_the_authoritative_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            center = ControlCenter(self.make_repo(directory))
            plan = "a" * 12
            self.write_plan_manifest(center, plan, "claude")
            (center.repo / ".factory/planning-state.json").write_text(json.dumps({
                "plan_id": plan,
                "mode": "rehearsal",
            }))

            planning = center.snapshot()["planning"]

            self.assertEqual(planning["planning_agent"], "claude")
            self.assertEqual(planning["mode"], "live")

    def test_blocked_approved_planning_exposes_a_retry_path(self):
        with tempfile.TemporaryDirectory() as directory:
            center = ControlCenter(self.make_repo(directory))
            planning = {
                "plan_id": "abc12345",
                "status": "blocked",
                "approvals": {"product": {"approved_at": "now"}, "alignment": None},
                "stages": [
                    {"id": "product_review", "status": "complete"},
                    {"id": "system_architecture", "status": "complete"},
                    {"id": "program_design", "status": "blocked"},
                    {"id": "vertical_slices", "status": "pending"},
                ],
            }
            failed_publication = {
                "status": "failed",
                "action": "publish-plan",
                "title": "Publish tickets to GitHub",
                "error": "The operation failed.",
            }

            journey = center.journey(
                planning, {"tickets": []}, failed_publication,
                {"saved": True}, [],
            )

            self.assertEqual(journey["phase_label"], "Plan")
            self.assertEqual(journey["next"]["view"], "planning")
            self.assertEqual(journey["next"]["label"], "Open expert recovery")

            planning_state = center.repo / ".factory/planning-state.json"
            planning_state.write_text(json.dumps(planning))
            snapshot = center.snapshot()
            self.assertFalse(snapshot["planning"]["can_continue"])
            self.assertEqual(snapshot["planning"]["continue_label"], "Open recovery options")

    def test_blocking_questions_require_control_center_decisions_instead_of_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            center = ControlCenter(self.make_repo(directory))
            planning = {
                "plan_id": "abc12345",
                "status": "blocked",
                "approvals": {"product": {"approved_at": "now"}, "alignment": None},
                "stages": [
                    {"id": "product_review", "title": "Product Review", "status": "complete", "questions": []},
                    {"id": "system_architecture", "title": "System Architecture", "status": "blocked", "questions": ["Where does it live?"]},
                    {"id": "program_design", "title": "Program Design", "status": "pending", "questions": []},
                    {"id": "vertical_slices", "title": "Vertical Slices", "status": "pending", "questions": []},
                ],
            }
            (center.repo / ".factory/planning-state.json").write_text(json.dumps(planning))

            snapshot = center.snapshot()
            journey = center.journey(
                planning,
                {"tickets": []},
                {"status": "failed", "action": "continue-plan"},
                {"saved": True},
                [],
            )

            self.assertFalse(snapshot["planning"]["can_continue"])
            self.assertTrue(snapshot["planning"]["requires_decisions"])
            self.assertEqual(snapshot["planning"]["blocked_stage"], "system_architecture")
            self.assertEqual(snapshot["planning"]["continue_label"], "Answer expert questions")
            self.assertEqual(journey["headline"], "System Architecture is waiting for you")
            self.assertEqual(journey["next"]["label"], "Answer blocked questions")

    def test_validation_failure_exposes_rejected_artifact_and_guided_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            center = ControlCenter(self.make_repo(directory))
            planning = {
                "plan_id": "abc12345",
                "status": "blocked",
                "approvals": {"product": {"approved_at": "now"}, "alignment": None},
                "stages": [
                    {"id": "product_review", "title": "Product Review", "status": "complete", "questions": []},
                    {"id": "system_architecture", "title": "System Architecture", "status": "complete", "questions": []},
                    {"id": "program_design", "title": "Program Design", "status": "complete", "questions": []},
                    {
                        "id": "vertical_slices",
                        "title": "Vertical Slices",
                        "status": "blocked",
                        "questions": [],
                        "failure_kind": "validation",
                        "error": "T1 references unknown IDs: C1",
                        "validation_error": "T1 references unknown IDs: C1",
                        "rejected_artifact": ".factory/plans/abc12345/rejected/vertical_slices-attempt-1.json",
                    },
                ],
            }
            (center.repo / ".factory/planning-state.json").write_text(json.dumps(planning))

            snapshot = center.snapshot()
            journey = center.journey(
                planning,
                {"tickets": []},
                {"status": "failed", "action": "continue-plan"},
                {"saved": True},
                [],
            )

            self.assertEqual(snapshot["planning"]["failed_stage"], "vertical_slices")
            self.assertFalse(snapshot["planning"]["can_continue"])
            self.assertTrue(snapshot["planning"]["requires_correction"])
            self.assertEqual(
                snapshot["planning"]["continue_label"],
                "Enter a correction for Vertical Slices",
            )
            self.assertEqual(journey["headline"], "Vertical Slices failed validation")
            self.assertIn("T1 references unknown IDs: C1", journey["detail"])
            self.assertEqual(journey["next"]["view"], "planning")
            self.assertIn("with correction", journey["next"]["label"])

    def test_provider_capacity_failure_disables_blind_retry_and_offers_adapter_switch(self):
        with tempfile.TemporaryDirectory() as directory:
            center = ControlCenter(self.make_repo(directory))
            plan = "a" * 12
            self.write_plan_manifest(center, plan, "claude")
            planning = {
                "plan_id": plan,
                "status": "blocked",
                "approvals": {"product": {"approved_at": "now"}, "alignment": None},
                "stages": [
                    {"id": "product_review", "title": "Product Review", "status": "complete", "questions": []},
                    {
                        "id": "system_architecture",
                        "title": "System Architecture",
                        "status": "blocked",
                        "questions": [],
                        "failure_kind": "agent",
                        "error": "You've hit your session limit · resets 2:40pm (Europe/London)",
                    },
                ],
            }
            (center.repo / ".factory/planning-state.json").write_text(json.dumps(planning))

            snapshot = center.snapshot()

            self.assertFalse(snapshot["planning"]["can_continue"])
            self.assertEqual(snapshot["planning"]["continue_label"], "Open recovery options")
            self.assertEqual(snapshot["planning"]["recovery"]["kind"], "provider_capacity")
            self.assertFalse(snapshot["planning"]["recovery"]["retry_same_adapter"])
            self.assertIn("codex", snapshot["planning"]["recovery"]["alternative_adapters"])
            journey = center.journey(
                {**planning, "planning_agent": "claude"},
                {"tickets": []},
                {"status": "failed", "action": "continue-plan"},
                {"saved": True},
                [],
            )
            self.assertEqual(journey["next"]["label"], "Switch planning adapter or wait")

    def test_unknown_agent_failure_has_an_explicit_same_adapter_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            center = ControlCenter(self.make_repo(directory))
            plan = "b" * 12
            self.write_plan_manifest(center, plan, "claude")
            planning = {
                "plan_id": plan,
                "status": "blocked",
                "approvals": {"product": {"approved_at": "now"}, "alignment": None},
                "stages": [
                    {"id": "product_review", "title": "Product Review", "status": "complete", "questions": []},
                    {
                        "id": "system_architecture",
                        "title": "System Architecture",
                        "status": "blocked",
                        "questions": [],
                        "failure_kind": "agent",
                        "error": "The agent process exited unexpectedly.",
                    },
                ],
            }
            (center.repo / ".factory/planning-state.json").write_text(json.dumps(planning))

            snapshot = center.snapshot()

            self.assertFalse(snapshot["planning"]["can_continue"])
            self.assertEqual(snapshot["planning"]["recovery"]["kind"], "agent_process")
            self.assertTrue(snapshot["planning"]["recovery"]["retry_same_adapter"])
            self.assertEqual(snapshot["planning"]["continue_label"], "Open recovery options")

    def test_repeated_agent_failure_stops_blind_retry_and_recommends_a_switch(self):
        recovery = planning_recovery(
            {
                "id": "system_architecture",
                "status": "blocked",
                "failure_kind": "agent",
                "failure_count": 2,
                "error": "The agent process exited unexpectedly.",
            },
            "claude",
            ["claude", "codex"],
        )

        self.assertEqual(recovery["kind"], "repeated_agent_failure")
        self.assertEqual(recovery["recommended_action"], "switch_adapter")
        self.assertEqual(recovery["recommended_adapter"], "codex")
        self.assertEqual(recovery["attempts"], 2)
        self.assertFalse(recovery["retry_same_adapter"])
        self.assertIn("failed 2 times", recovery["summary"])

    def test_stale_governance_requires_a_control_center_replan_instead_of_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            center = ControlCenter(self.make_repo(directory))
            project = ProjectContract.detect(center.repo)
            project.write()
            charter = FactoryCharter.draft(center.repo, project)
            charter.write()
            charter.approve()
            center.prd_path.parent.mkdir(parents=True, exist_ok=True)
            center.prd_path.write_text("# Current PRD\n")
            plan = "a" * 12
            self.write_plan_manifest(center, plan, "claude")
            planning = {
                "plan_id": plan,
                "status": "stale_factory_charter",
                "approvals": {"product": None, "alignment": None},
                "stages": [
                    {
                        "id": "product_review",
                        "title": "Product Review",
                        "status": "complete",
                        "questions": [],
                    },
                    {
                        "id": "system_architecture",
                        "title": "System Architecture",
                        "status": "blocked",
                        "questions": [],
                        "failure_kind": "agent",
                        "error": "Planning Run predates Factory Charter governance",
                    },
                ],
            }
            (center.repo / ".factory/planning-state.json").write_text(json.dumps(planning))

            snapshot = center.snapshot()

            self.assertTrue(snapshot["planning"]["requires_replan"])
            self.assertFalse(snapshot["planning"]["can_continue"])
            self.assertEqual(
                snapshot["planning"]["continue_label"],
                "Restart planning with current governance",
            )
            self.assertEqual(snapshot["journey"]["headline"], "Planning governance changed")
            self.assertEqual(snapshot["journey"]["next"]["label"], "Restart planning safely")
            self.assertEqual(snapshot["journey"]["next"]["view"], "planning")

    def test_restart_plan_preserves_the_prd_and_live_planning_adapter(self):
        with tempfile.TemporaryDirectory() as directory:
            center = ControlCenter(self.make_repo(directory))
            center.prd_path.parent.mkdir(parents=True, exist_ok=True)
            center.prd_path.write_text("# Current PRD\n")
            plan = "a" * 12
            self.write_plan_manifest(center, plan, "claude")
            (center.repo / ".factory/planning-state.json").write_text(json.dumps({
                "plan_id": plan,
                "status": "stale_factory_charter",
            }))

            title, commands = center.build_commands("restart-plan", {"plan_id": plan})

            self.assertEqual(title, "Restart planning with current governance")
            self.assertEqual(commands[0][1:3], ["plan", str(center.prd_path)])
            self.assertIn("--planning-agent", commands[0])
            self.assertIn("claude", commands[0])
            self.assertNotIn("--mock", commands[0])

    def test_restart_plan_rejects_a_non_stale_planning_run(self):
        with tempfile.TemporaryDirectory() as directory:
            center = ControlCenter(self.make_repo(directory))
            center.prd_path.parent.mkdir(parents=True, exist_ok=True)
            center.prd_path.write_text("# Current PRD\n")
            plan = "a" * 12
            self.write_plan_manifest(center, plan, "claude")
            (center.repo / ".factory/planning-state.json").write_text(json.dumps({
                "plan_id": plan,
                "status": "blocked",
            }))

            with self.assertRaisesRegex(InputError, "does not require a full restart"):
                center.build_commands("restart-plan", {"plan_id": plan})

    def test_published_plan_never_advertises_a_blocked_expert_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            center = ControlCenter(self.make_repo(directory))
            planning = {
                "plan_id": "abc12345",
                "status": "published",
                "approvals": {
                    "product": {"approved_at": "now"},
                    "alignment": {"approved_at": "now"},
                },
                "stages": [
                    {"id": "product_review", "status": "complete", "questions": []},
                    {"id": "system_architecture", "status": "complete", "questions": []},
                    {"id": "program_design", "status": "complete", "questions": []},
                    {"id": "vertical_slices", "status": "complete", "questions": []},
                ],
            }
            (center.repo / ".factory/planning-state.json").write_text(json.dumps(planning))

            snapshot = center.snapshot()

            self.assertFalse(snapshot["planning"]["can_continue"])
            self.assertEqual(snapshot["planning"]["continue_label"], "Planning complete")
            self.assertFalse(snapshot["planning"]["failed_stage"])

    def test_lean_snapshot_marks_supervisor_disabled_before_a_run(self):
        with tempfile.TemporaryDirectory() as directory:
            center = ControlCenter(self.make_repo(directory))
            local = center.repo / ".factory/local.toml"
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_text('profile = "lean"\n')

            snapshot = center.snapshot()

            self.assertEqual(snapshot["supervisor"]["status"], "disabled")

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

            active_factory["tickets"].append({
                "number": 4, "title": "Ready slice", "status": "Ready",
            })
            active_factory["human_attention"] = {
                "dispatch_paused": True,
                "reason": "human review queue 3 / limit 3",
                "oldest": {"ticket": 3, "status": "QA Review"},
            }
            paused = center.journey(planning, active_factory, {}, prd, [])
            self.assertEqual(paused["headline"], "NEEDS YOU — new dispatch is paused")
            self.assertIn("queue 3 / limit 3", paused["detail"])
            self.assertEqual(paused["ticket"], 3)

    def test_control_center_can_release_only_a_recorded_live_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            center = ControlCenter(self.make_repo(directory))
            title, commands = center.build_commands("release-claim", {
                "mode": "live",
                "issue": 8,
                "owner_run_id": "run-owner-1",
                "reason": "Operator confirmed the runner was abandoned",
            })

            self.assertEqual(title, "Release abandoned claim for ticket #8")
            self.assertIn("release-claim", commands[0])
            self.assertIn("--owner-run-id", commands[0])
            self.assertIn("run-owner-1", commands[0])
            self.assertIn("--yes", commands[0])

    def test_frontend_contains_the_complete_operator_workflow(self):
        frontend = Path(__file__).parents[1] / "control_center"
        source = (frontend / "index.html").read_text()
        javascript = (frontend / "app.js").read_text()

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
            "Plan, build, verify, review",
            "Agent supervisor",
            "Handoff Receipts",
            "GitHub repository URL",
            "Monitor repository health",
            "Read-only by contract",
        ):
            self.assertIn(label, source)

        self.assertIn("app.selectedPlanning !== selectedId", javascript)
        self.assertNotIn("app.selectedPlanning === id", javascript)
        self.assertIn("planning.blocked_stage || planning.failed_stage", javascript)
        self.assertIn("if (item.planning)", javascript)
        self.assertNotIn('id="planning-profile"', source)
        self.assertIn('id="connect-mode"', source)
        self.assertIn('full: mode() === "live"', javascript)
        self.assertIn("planning.can_continue", javascript)
        self.assertIn("planning.continue_label", javascript)
        self.assertIn("renderExpertPanel", javascript)
        self.assertIn("Answer every blocking question", javascript)
        self.assertIn('action(actionName, { stage: item.id, decisions: answers })', javascript)
        self.assertNotIn("Question: ${question}", javascript)
        self.assertIn('id="planning-recovery-feedback"', javascript)
        self.assertIn("Apply correction and continue", javascript)
        self.assertIn("Switch adapter and continue", javascript)
        self.assertIn("Fix with", javascript)
        self.assertIn("Same-agent retry disabled", javascript)
        self.assertIn("Retry same adapter", javascript)
        self.assertIn('action("revise-stage", { stage: item.id, feedback })', javascript)
        self.assertIn("Restart planning safely", javascript)
        self.assertIn('action("restart-plan")', javascript)
        self.assertIn("Causal acceptance evidence", javascript)
        self.assertIn("RED NOT PROVED", javascript)
        self.assertIn("GREEN NOT PROVED", javascript)
        self.assertIn("NEEDS YOU · Dispatch paused", javascript)
        self.assertIn("Release abandoned claim", javascript)
        self.assertIn("Merge exact revision", javascript)
        self.assertIn('action("merge", { issue: ticket.number })', javascript)
        self.assertIn("renderMonitor", javascript)
        self.assertIn("finding.summary || finding.title || finding.id", javascript)
        self.assertIn("payload.mode = mode()", javascript)


if __name__ == "__main__":
    unittest.main()
