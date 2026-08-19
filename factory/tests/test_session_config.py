import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from orchestrator import apply_session_defaults, parser
from session_config import configure_session, load_session_config, remember_project


class SessionConfigTests(unittest.TestCase):
    def test_claude_preset_is_saved_outside_tracked_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            path, value = configure_session(repo, "claude-workshop", 7)
            self.assertEqual(path, repo.resolve() / ".factory/local.toml")
            self.assertEqual(value["planning_agent"], "claude")
            self.assertEqual(value["qa_agent"], "claude")
            self.assertTrue(value["review_qa_tests"])
            self.assertEqual(value["max_parallel"], 2)
            self.assertEqual(value["project_number"], 7)
            self.assertEqual(load_session_config(repo), value)

    def test_run_uses_saved_defaults_and_cli_flags_override_them(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            configure_session(repo, "claude-workshop", 7)
            args = parser().parse_args(["run", "--max-parallel", "3"])
            args.repo = str(repo)
            apply_session_defaults(args, repo)
            self.assertEqual(args.agent, "claude")
            self.assertEqual(args.qa_agent, "claude")
            self.assertTrue(args.review_qa_tests)
            self.assertEqual(args.max_parallel, 3)
            self.assertEqual(args.project_number, 7)

    def test_mock_run_does_not_inherit_live_agent_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            configure_session(repo, "claude-workshop", 7)
            args = parser().parse_args(["run", "--mock"])
            args.repo = str(repo)
            apply_session_defaults(args, repo)
            self.assertIsNone(args.qa_agent)
            self.assertFalse(args.review_qa_tests)
            self.assertIsNone(args.project_number)

    def test_plan_uses_saved_planning_and_ticket_agents(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            configure_session(repo, "claude-workshop")
            args = parser().parse_args(["plan", "PRD.md"])
            args.repo = str(repo)
            apply_session_defaults(args, repo)
            self.assertEqual(args.planning_agent, "claude")
            self.assertEqual(args.default_agent, "claude")

    def test_custom_registered_agent_can_be_saved_and_used_by_commands(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            _, value = configure_session(
                repo, agent="my-agent", qa_agent="my-agent",
                planning_agent="claude", review_qa_tests=True, max_parallel=3,
            )
            self.assertEqual(value["agent"], "my-agent")
            self.assertEqual(value["qa_agent"], "my-agent")

            args = parser().parse_args(["run"])
            args.repo = str(repo)
            apply_session_defaults(args, repo)
            self.assertEqual(args.agent, "my-agent")
            self.assertEqual(args.qa_agent, "my-agent")
            self.assertEqual(args.max_parallel, 3)

    def test_configure_parser_accepts_custom_adapter_overrides(self):
        args = parser().parse_args([
            "configure", "--agent", "my-agent", "--qa-agent", "qa-wrapper",
            "--planning-agent", "codex", "--review-qa-tests", "--max-parallel", "2",
        ])
        self.assertEqual(args.agent, "my-agent")
        self.assertEqual(args.qa_agent, "qa-wrapper")
        self.assertEqual(args.planning_agent, "codex")

    def test_new_project_number_is_remembered_without_losing_preset(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            configure_session(repo, "claude-workshop")
            remember_project(repo, 11)
            value = load_session_config(repo)
            self.assertEqual(value["preset"], "claude-workshop")
            self.assertEqual(value["project_number"], 11)

    def test_new_project_title_does_not_reuse_saved_project_number(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            configure_session(repo, "claude-workshop", 7)
            args = parser().parse_args([
                "approve", "abc123", "--new-project-title", "New board",
            ])
            args.repo = str(repo)
            apply_session_defaults(args, repo)
            self.assertIsNone(args.project_number)


if __name__ == "__main__":
    unittest.main()
