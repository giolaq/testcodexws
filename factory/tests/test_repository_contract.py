import subprocess
import unittest
from pathlib import Path


REPO = Path(__file__).parents[2]
EXEMPT_HISTORY = {
    "docs/specs/0001-evidence-driven-factory-workshop.md",
    "docs/workshop-design.md",
    "factory/tests/test_repository_contract.py",
    "workshop-guide/tests/rendered-html.test.mjs",
}
RETIRED_PATHS = {
    "factory/LIGHTS_OFF_EXPERIMENT.md",
    "factory/run_lights_off.py",
    "factory/scenarios/recipe-rebrand/lights-off-prompt.md",
    "factory/scenarios/recipe-rebrand/lights-off-sample-report.md",
    "factory/tests/test_lights_off.py",
}
RETIRED_LANGUAGE = {
    "LIGHTS" + "_OFF_EXPERIMENT.md",
    "test_" + "lights_off.py",
    "lights" + "-off control",
    "control" + " experiment",
    "run_" + "lights_off",
    "lights" + "-off-prompt",
    "lights" + "-off-sample-report",
    "two delivery" + " systems",
    "compare both" + " results",
}


class RepositoryContractTests(unittest.TestCase):
    def test_removed_control_has_no_live_repository_surface(self):
        tracked = set(
            subprocess.run(
                ["git", "ls-files"],
                cwd=REPO,
                text=True,
                capture_output=True,
                check=True,
            ).stdout.splitlines()
        )
        self.assertFalse(RETIRED_PATHS & tracked)

        offenders = []
        for relative in sorted(tracked - EXEMPT_HISTORY):
            path = REPO / relative
            if not path.is_file():
                continue
            text = path.read_text(errors="ignore").casefold()
            for phrase in RETIRED_LANGUAGE:
                if phrase.casefold() in text:
                    offenders.append(f"{relative}: {phrase}")

        self.assertEqual(offenders, [])

    def test_release_test_commands_use_an_environment_with_runtime_test_dependencies(self):
        workflow = (REPO / ".github/workflows/factory-verify.yml").read_text()
        install = "python3 -m pip install -r demo-app/requirements.txt"
        unit = "python3 -m unittest discover -s factory/tests -v"
        self.assertIn(install, workflow)
        self.assertLess(workflow.index(install), workflow.index(unit))

        for relative in ("factory/README.md", "factory/FACILITATOR.md"):
            text = (REPO / relative).read_text()
            self.assertIn(
                ".factory/venv/bin/python -m unittest discover -s factory/tests",
                text,
            )

    def test_release_workflow_uses_node_24_action_runtimes(self):
        workflow = (REPO / ".github/workflows/factory-verify.yml").read_text()

        self.assertEqual(workflow.count("uses: actions/checkout@v7"), 3)
        self.assertEqual(workflow.count("uses: actions/setup-python@v7"), 3)
        self.assertEqual(workflow.count("uses: actions/setup-node@v7"), 2)
        for retired in (
            "actions/checkout@v4",
            "actions/setup-python@v5",
            "actions/setup-node@v4",
        ):
            self.assertNotIn(retired, workflow)

    def test_release_workflow_does_not_duplicate_pull_request_runs(self):
        workflow = (REPO / ".github/workflows/factory-verify.yml").read_text()

        self.assertIn(
            "on:\n  push:\n    branches: [main]\n  pull_request:",
            workflow,
        )

    def test_rehearsal_workflow_asserts_the_human_merge_gate(self):
        workflow = (REPO / ".github/workflows/factory-verify.yml").read_text()

        self.assertIn(
            "assert in_review == [1, 3, 7]",
            workflow,
        )
        self.assertIn(
            "assert in_review == [1, 2]",
            workflow,
        )
        self.assertNotIn("assert all(ticket['status'] == 'Done'", workflow)
        self.assertNotIn("sum(t['status'] == 'Done'", workflow)

    def test_participant_surfaces_use_acceptance_test_terminology(self):
        guide = (REPO / "workshop-guide/app/page.tsx").read_text()
        orchestrator = (REPO / "factory/orchestrator.py").read_text()

        self.assertNotIn("reviewing QA tests", guide)
        self.assertNotIn("QA test revision", orchestrator)


if __name__ == "__main__":
    unittest.main()
