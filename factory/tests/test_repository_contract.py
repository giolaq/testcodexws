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


if __name__ == "__main__":
    unittest.main()
