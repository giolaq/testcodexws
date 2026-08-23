import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from factory_charter import FactoryCharter
from project_contract import ProjectContract
from triage import classify_controls, triage_ticket


class TriageTests(unittest.TestCase):
    def charter(self, root: Path) -> FactoryCharter:
        project = ProjectContract.detect(root)
        charter = FactoryCharter.draft(root, project)
        return charter

    def test_triage_distinguishes_information_planning_wait_and_implementation(self):
        with tempfile.TemporaryDirectory() as directory:
            charter = self.charter(Path(directory))
            body = "## Spec\nAdd search.\n\n## Acceptance criteria\n- [ ] Search returns matching recipes\n"
            self.assertEqual(triage_ticket("vague", dependencies_ready=True, planned=False, profile="standard", charter=charter)["result"], "NEEDS_INFORMATION")
            self.assertEqual(triage_ticket(body, dependencies_ready=False, planned=True, profile="standard", charter=charter)["result"], "WAIT")
            self.assertEqual(triage_ticket(body, dependencies_ready=True, planned=False, profile="standard", charter=charter)["result"], "READY_TO_PLAN")
            self.assertEqual(triage_ticket(body, dependencies_ready=True, planned=False, profile="lean", charter=charter)["result"], "READY_TO_IMPLEMENT")

    def test_load_bearing_path_can_never_select_a_weaker_gate_level(self):
        with tempfile.TemporaryDirectory() as directory:
            charter = self.charter(Path(directory))
            controls = classify_controls(charter, ["auth/session.py"])

            self.assertTrue(controls["load_bearing"])
            self.assertEqual(controls["gate_level"], "deep")
            self.assertEqual(controls["risk"], "load-bearing")


if __name__ == "__main__":
    unittest.main()
