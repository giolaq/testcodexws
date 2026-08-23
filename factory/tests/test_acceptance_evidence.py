import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from acceptance_evidence import classify_focused_result, focused_test_command


class AcceptanceEvidenceTests(unittest.TestCase):
    def test_builds_a_bounded_command_for_the_exact_python_test_files(self):
        command = focused_test_command(
            ["tests/test_ticket_7_search.py", "tests/test_ticket_7_errors.py"],
            "/tmp/factory python",
        )

        self.assertEqual(
            command,
            "'/tmp/factory python' -m pytest -q "
            "tests/test_ticket_7_errors.py tests/test_ticket_7_search.py",
        )

    def test_rejects_a_mixed_or_unsupported_focused_test_set(self):
        with self.assertRaisesRegex(ValueError, "one supported test runner"):
            focused_test_command(
                ["tests/test_ticket_7_search.py", "tests/ticket-7-search.test.js"],
                sys.executable,
            )
        with self.assertRaisesRegex(ValueError, "supported focused test runner"):
            focused_test_command(["tests/Ticket7SearchTest.java"], sys.executable)

    def test_classifies_only_behavior_assertions_as_valid_red_evidence(self):
        self.assertEqual(
            classify_focused_result(1, "FAILED test_search - AssertionError: expected recipe"),
            "behavior_assertion",
        )
        self.assertEqual(
            classify_focused_result(1, "not ok 1 - search\ncode: ERR_ASSERTION"),
            "behavior_assertion",
        )
        self.assertEqual(
            classify_focused_result(2, "ERROR collecting test_search.py\nModuleNotFoundError: flask"),
            "collection_error",
        )
        self.assertEqual(classify_focused_result(124, "timed out"), "timeout")
        self.assertEqual(classify_focused_result(127, "pytest: command not found"), "command_error")
        self.assertEqual(classify_focused_result(1, "process exited unexpectedly"), "unrelated_failure")

    def test_rejects_skipped_or_already_passing_tests_as_red_evidence(self):
        self.assertEqual(classify_focused_result(0, "1 passed"), "pass")
        self.assertEqual(classify_focused_result(0, "1 skipped"), "skipped")
        self.assertEqual(classify_focused_result(0, "# tests 1\n# skipped 1"), "skipped")


if __name__ == "__main__":
    unittest.main()
