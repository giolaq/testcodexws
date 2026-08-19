import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from planner import approve_plan, dependency_waves, issue_body, render_review, validate_plan


def sample_plan():
    return {
        "plan_version": 1,
        "plan_id": "abc123",
        "source_prd": "/tmp/PRD.md",
        "project": {"name": "Example", "summary": "Build an example safely."},
        "open_questions": [],
        "tickets": [
            {
                "key": "T1", "title": "Create the core", "spec": "Add the core module.",
                "acceptance_criteria": ["The core test passes"], "dependencies": [], "agent": "codex",
            },
            {
                "key": "T2", "title": "Add the UI", "spec": "Render the core module.",
                "acceptance_criteria": ["The UI renders the result"], "dependencies": ["T1"], "agent": "codex",
            },
        ],
    }


class PlannerTests(unittest.TestCase):
    def test_valid_plan_returns_dependency_order(self):
        self.assertEqual(validate_plan(sample_plan()), ["T1", "T2"])

    def test_valid_plan_accepts_a_custom_adapter_name(self):
        plan = sample_plan()
        plan["tickets"][0]["agent"] = "my-agent"
        self.assertEqual(validate_plan(plan), ["T1", "T2"])

    def test_cycle_is_rejected(self):
        plan = sample_plan()
        plan["tickets"][0]["dependencies"] = ["T2"]
        with self.assertRaisesRegex(ValueError, "cycle"):
            validate_plan(plan)

    def test_unknown_dependency_is_rejected(self):
        plan = sample_plan()
        plan["tickets"][1]["dependencies"] = ["MISSING"]
        with self.assertRaisesRegex(ValueError, "unknown dependencies"):
            validate_plan(plan)

    def test_issue_body_uses_published_issue_numbers(self):
        body = issue_body(sample_plan()["tickets"][1], {"T1": 41}, "abc123")
        self.assertIn("Depends-on: #41", body)
        self.assertIn("agent: codex", body)
        self.assertIn("factory-plan:abc123:T2", body)

    def test_review_exposes_human_approval_step(self):
        plan = sample_plan()
        plan["_plan_path"] = "/tmp/plan.json"
        review = render_review(plan)
        self.assertIn("T2 — Add the UI", review)
        self.assertIn("factory approve /tmp/plan.json", review)
        self.assertIn("No issue or coding agent is created", review)
        self.assertIn("```mermaid", review)
        self.assertIn("N0 --> N1", review)
        self.assertIn("## Parallel waves", review)

    def test_dependency_waves_match_scheduler_order(self):
        self.assertEqual(dependency_waves(sample_plan()), [["T1"], ["T2"]])

    def test_open_questions_block_publication_before_github_calls(self):
        plan = sample_plan()
        plan["open_questions"] = ["Which identity provider should be used?"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "plan.json"
            path.write_text(json.dumps(plan))
            with self.assertRaisesRegex(ValueError, "resolve and remove"):
                approve_plan(Path(directory), path, None, True)

    def test_approval_rejects_two_project_selection_modes(self):
        with self.assertRaisesRegex(ValueError, "either --project-number"):
            approve_plan(Path("."), Path("missing.json"), 2, True, "Fresh board")


if __name__ == "__main__":
    unittest.main()
