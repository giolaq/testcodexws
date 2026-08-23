import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from run_summary import (
    factory_run_summary,
    parse_factory_run_summary,
    render_factory_run_summary,
)
from sensitive_data import contains_credentials


class RunSummaryTests(unittest.TestCase):
    def test_summary_is_bounded_revision_specific_and_excludes_local_secrets(self):
        secret = "sk-" + "proj-" + "abcdefghijklmnopqrstuvwxyz123456"
        state = {
            "run_id": "run-123", "profile": "standard",
            "governance": {"charter_sha256": "c" * 64, "merge_authority": "human"},
            "policy": {"hashes": {"engineering": "p" * 64}},
            "supervisor_agent": "claude",
        }
        ticket = {
            "number": 4, "status": "In Review", "plan_id": "plan12345",
            "agent": "claude", "qa_agent": "codex", "review_agent": "claude",
            "base_sha": "a" * 40, "qa_commit": "b" * 40, "approved_head": "d" * 40,
            "failure": f"local log contained {secret}", "current_log": secret,
            "qa_evidence": {"red": {"result": "RED PROVED"}, "green": {"result": "GREEN PROVED"}},
            "gate_results": [{"name": "tests", "level": "full", "required": True, "classification": "PASS", "exit_code": 0, "duration_seconds": 1.2, "output": secret}],
            "triage": {"result": "READY_TO_IMPLEMENT", "controls": {"risk": "shared", "gate_level": "full"}},
            "metrics": {"agent_seconds": 2.5, "gate_seconds": 1.2, "human_wait_seconds": 3, "retry_count": 1, "verifier_rejections": 1},
            "remote_claim": {"owner_run_id": "run-123", "claimed_at": "2026-08-23T12:00:00+00:00"},
            "merge_authority": "human",
            "policy_required_human_merge": True,
        }

        summary = factory_run_summary(state, ticket)
        rendered = render_factory_run_summary(summary)

        self.assertFalse(contains_credentials(rendered))
        self.assertNotIn(secret, rendered)
        self.assertEqual(summary["revisions"]["approved_head"], "d" * 40)
        self.assertNotIn("output", summary["gates"][0])
        self.assertNotIn("failure", summary)
        self.assertEqual(summary["metrics"]["agent_seconds"], 2.5)
        self.assertEqual(summary["metrics"]["retry_count"], 1)
        self.assertEqual(summary["claim"]["claimed_at"], "2026-08-23T12:00:00+00:00")
        self.assertEqual(summary["input_hashes"]["charter"], "c" * 64)
        self.assertEqual(summary["input_hashes"]["base_revision"], "a" * 40)
        self.assertEqual(summary["unresolved_risks"], ["local log contained [REDACTED]"])
        self.assertTrue(summary["human_decisions"]["policy_required_human_merge"])
        self.assertEqual(summary["human_decisions"]["effective_merge_authority"], "human")

    def test_rendered_summary_can_be_validated_and_recovered_from_a_comment(self):
        payload = {
            "schema_version": 1,
            "run_id": "run-123",
            "ticket": 4,
            "status": "In Review",
            "plan_id": "plan12345",
            "governance": {"charter_sha256": "c" * 64},
            "revisions": {"approved_head": "d" * 40},
            "verdicts": {"code_review": "APPROVE"},
        }

        recovered = parse_factory_run_summary(render_factory_run_summary(payload), ticket=4)

        self.assertEqual(recovered, payload)
        self.assertIsNone(parse_factory_run_summary("ordinary human comment", ticket=4))
        self.assertIsNone(parse_factory_run_summary(render_factory_run_summary(payload), ticket=5))


if __name__ == "__main__":
    unittest.main()
