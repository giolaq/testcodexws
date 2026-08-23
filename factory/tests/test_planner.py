import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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

    def test_issue_body_preserves_the_reviewed_delivery_contract(self):
        ticket = sample_plan()["tickets"][0] | {
            "vertical_outcome": "A user can complete the core journey.",
            "requirement_ids": ["R1"],
            "contract_ids": ["CT-API"],
            "program_element_ids": ["FN-LOAD"],
            "file_ownership": ["src/core.py"],
            "qa_evidence": ["Core journey acceptance test"],
        }

        body = issue_body(ticket, {}, "abc123")

        self.assertIn("## Vertical outcome", body)
        self.assertIn("**Requirements:** R1", body)
        self.assertIn("## File ownership\n- src/core.py", body)
        self.assertIn("## QA evidence", body)

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

    def test_publication_adds_only_the_approved_tickets_to_the_project(self):
        class RecordingBackend:
            instance = None

            def __init__(self, repo, project_number=None):
                type(self).instance = self
                self.owner = "giolaq"
                self.name = "test1"
                self.project_number = project_number
                self.created = []
                self.added = []

            def preflight(self):
                return None

            def json(self, *args):
                if args[:2] == ("project", "create"):
                    return {"number": 12}
                if args[:2] == ("issue", "list"):
                    return []
                if args[:2] == ("project", "view"):
                    return {"url": "https://github.test/users/giolaq/projects/12"}
                raise AssertionError(f"unexpected GitHub JSON call: {args}")

            def gh(self, *args):
                if args[:2] == ("issue", "create"):
                    number = 40 + len(self.created) + 1
                    url = f"https://github.test/giolaq/test1/issues/{number}"
                    self.created.append((number, url))
                    return subprocess.CompletedProcess(args, 0, url + "\n", "")
                return subprocess.CompletedProcess(args, 0, "", "")

            def add_issue_to_project(self, number, url):
                self.added.append((number, url))

            def load(self):
                return [
                    {"number": number, "labels": ["agent-ready"]}
                    for number, _ in self.created
                ]

            def set_status(self, ticket, status, note):
                ticket["status"] = status

        plan = sample_plan()
        plan["tickets"] = plan["tickets"][:1]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "plan.json"
            path.write_text(json.dumps(plan))

            with mock.patch("planner.GitHubBackend", RecordingBackend):
                approve_plan(
                    Path(directory), path, None, True,
                    new_project_title="Fresh smoke board",
                )

        backend = RecordingBackend.instance
        self.assertEqual(backend.added, backend.created)


if __name__ == "__main__":
    unittest.main()
