import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from supervisor import (
    AgentSupervisor,
    SupervisorError,
    extract_decision,
    extract_merge_decision,
    validate_decision,
    validate_merge_decision,
)
from factory_charter import FactoryCharter
from project_contract import ProjectContract


class SupervisorTests(unittest.TestCase):
    def make_repo(self, directory: str) -> Path:
        repo = Path(directory)
        factory = repo / "factory"
        factory.mkdir()
        source = Path(__file__).parents[1]
        shutil.copy(source / "roles.json", factory / "roles.json")
        shutil.copy(source / "policy.json", factory / "policy.json")
        charter = FactoryCharter.draft(repo, ProjectContract.detect(repo))
        charter.write()
        charter.approve()
        return repo

    def ticket(self, number: int, status="Ready", receipts=None) -> dict:
        return {
            "number": number,
            "title": f"Ticket {number}",
            "body": "## Spec\nDeliver one vertical slice.",
            "status": status,
            "phase": "ready",
            "dependencies": [],
            "attempt": 0,
            "failure": "",
            "receipts": receipts or [],
        }

    def supervisor(self, repo: Path, response: dict) -> AgentSupervisor:
        return AgentSupervisor(
            repo,
            agent="test-supervisor",
            template="unused",
            python=sys.executable,
            codex_bin="",
            scenario="recipe-rebrand",
            mock=True,
            agent_timeout=10,
            invoke=lambda prompt: (0, "adapter preface\n" + json.dumps(response)),
        )

    def test_coordinate_returns_validated_dispatch_and_records_worker_reports(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = self.make_repo(directory)
            receipt = repo / ".factory/receipts/run/build-ticket-1.json"
            receipt.parent.mkdir(parents=True)
            receipt.write_text(json.dumps({
                "ticket": 1,
                "role": "implementation",
                "phase": "Build",
                "claimed_result": "Implementation committed",
                "verification": ["Adapter exited successfully."],
                "unresolved_risks": [],
                "output_revisions": {"implementation_commit": "abc123"},
            }))
            response = {
                "schema_version": 1,
                "summary": "Start the independent slices together.",
                "dispatch": [
                    {"ticket": 1, "instruction": "Preserve the data contract."},
                    {"ticket": 2, "instruction": "Avoid files owned by ticket 1."},
                ],
                "block": [],
            }

            decision = self.supervisor(repo, response).coordinate([
                self.ticket(1, receipts=[str(receipt.relative_to(repo))]),
                self.ticket(2),
            ], 2)

            self.assertEqual([item["ticket"] for item in decision["dispatch"]], [1, 2])
            self.assertEqual(decision["worker_reports"][0]["claimed_result"], "Implementation committed")
            prompt = (repo / decision["prompt"]).read_text()
            self.assertIn("## Approved Factory Charter", prompt)
            self.assertIn(
                FactoryCharter.load(repo, require_approved=True).policy_sha256(),
                prompt,
            )
            state = json.loads((repo / ".factory/supervisor/state.json").read_text())
            self.assertEqual(state["status"], "ready")
            self.assertEqual(state["latest"]["id"], "supervisor-1")

    def test_coordinate_repairs_one_invalid_adapter_decision(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = self.make_repo(directory)
            responses = iter([
                {
                    "schema_version": 1,
                    "summary": "Dispatch the ready Ticket.",
                    "dispatch": [{"ticket": 1, "instruction": "x" * 1201}],
                    "block": [],
                },
                {
                    "schema_version": 1,
                    "summary": "Dispatch the ready Ticket with a bounded instruction.",
                    "dispatch": [{"ticket": 1, "instruction": "Implement the approved Ticket scope."}],
                    "block": [],
                },
            ])
            prompts = []

            supervisor = AgentSupervisor(
                repo,
                agent="test-supervisor",
                template="unused",
                python=sys.executable,
                codex_bin="",
                scenario="recipe-rebrand",
                mock=True,
                agent_timeout=10,
                invoke=lambda prompt: (
                    prompts.append(Path(prompt)) or 0,
                    json.dumps(next(responses)),
                ),
            )

            decision = supervisor.coordinate([self.ticket(1)], 1)

            self.assertEqual(
                decision["dispatch"][0]["instruction"],
                "Implement the approved Ticket scope.",
            )
            self.assertEqual(len(prompts), 2)
            repair_prompt = prompts[1].read_text()
            self.assertIn("longer than 1200 characters", repair_prompt)

    def test_coordinate_fails_closed_after_one_invalid_repair(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = self.make_repo(directory)
            calls = []
            invalid = {
                "schema_version": 1,
                "summary": "Dispatch the ready Ticket.",
                "dispatch": [{"ticket": 1, "instruction": "x" * 1201}],
                "block": [],
            }
            supervisor = AgentSupervisor(
                repo,
                agent="test-supervisor",
                template="unused",
                python=sys.executable,
                codex_bin="",
                scenario="recipe-rebrand",
                mock=True,
                agent_timeout=10,
                invoke=lambda prompt: (calls.append(Path(prompt)) or 0, json.dumps(invalid)),
            )

            with self.assertRaisesRegex(SupervisorError, "longer than 1200 characters"):
                supervisor.coordinate([self.ticket(1)], 1)

            self.assertEqual(len(calls), 2)
            state = json.loads((repo / ".factory/supervisor/state.json").read_text())
            self.assertEqual(state["status"], "failed")
            self.assertEqual(len(state["attempts"]), 2)
            self.assertTrue(all(item["validation_error"] for item in state["attempts"]))

    def test_invalid_or_silent_decisions_are_rejected(self):
        with self.assertRaisesRegex(SupervisorError, "unavailable ticket"):
            validate_decision({
                "schema_version": 1,
                "summary": "Wrong ticket.",
                "dispatch": [{"ticket": 9, "instruction": "Start."}],
                "block": [],
            }, {1}, 1)
        with self.assertRaisesRegex(SupervisorError, "silent stalls"):
            validate_decision({
                "schema_version": 1,
                "summary": "Wait.",
                "dispatch": [],
                "block": [],
            }, {1}, 1)

    def test_block_command_requires_a_concrete_reason(self):
        decision = validate_decision({
            "schema_version": 1,
            "summary": "Stop unsafe work.",
            "dispatch": [],
            "block": [{"ticket": 3, "reason": "The latest verification receipt reports a contract failure."}],
        }, {3}, 2)
        self.assertEqual(decision["block"][0]["ticket"], 3)

    def test_last_structured_object_wins_over_adapter_noise(self):
        output = 'noise {"not":"a decision"}\n' + json.dumps({
            "schema_version": 1,
            "summary": "Dispatch.",
            "dispatch": [{"ticket": 1, "instruction": "Start."}],
            "block": [],
        })
        self.assertEqual(extract_decision(output)["summary"], "Dispatch.")

    def test_merge_requires_matching_approved_revision_and_passing_gates(self):
        ticket = self.ticket(4, status="In Review")
        ticket.update({
            "pr_url": "https://github.test/example/pull/4",
            "gate_results": [{"name": "tests", "required": True, "exit_code": 0}],
            "code_review": {
                "head": "abc123",
                "result": {"decision": "APPROVE"},
                "publication": {"published": True, "official": False},
            },
        })
        raw = {
            "schema_version": 1,
            "summary": "Approval and gates match this candidate.",
            "action": "MERGE",
            "ticket": 4,
            "pull_request": ticket["pr_url"],
            "candidate_head": "abc123",
        }

        decision = validate_merge_decision(extract_merge_decision(json.dumps(raw)), ticket)
        self.assertEqual(decision["action"], "MERGE")

        raw["candidate_head"] = "stale"
        with self.assertRaisesRegex(SupervisorError, "stale"):
            validate_merge_decision(raw, ticket)

        raw["candidate_head"] = "abc123"
        ticket["gate_results"] = [{"name": "lint", "required": False, "exit_code": 0}]
        with self.assertRaisesRegex(SupervisorError, "required gates"):
            validate_merge_decision(raw, ticket)

    def test_authorize_merge_records_a_distinct_supervisor_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = self.make_repo(directory)
            ticket = self.ticket(7, status="In Review")
            ticket.update({
                "pr_url": "https://github.test/example/pull/7",
                "gate_results": [{"name": "tests", "required": True, "exit_code": 0}],
                "code_review": {
                    "head": "deadbeef",
                    "result": {"decision": "APPROVE"},
                    "publication": {"published": True, "official": True},
                },
            })
            response = {
                "schema_version": 1,
                "summary": "Merge the approved candidate.",
                "action": "MERGE",
                "ticket": 7,
                "pull_request": ticket["pr_url"],
                "candidate_head": "deadbeef",
            }

            decision = self.supervisor(repo, response).authorize_merge(ticket)

            self.assertEqual(decision["action"], "MERGE")
            self.assertEqual(decision["kind"], "merge")
            state = json.loads((repo / ".factory/supervisor/state.json").read_text())
            self.assertEqual(state["latest"]["id"], "supervisor-merge-1")


if __name__ == "__main__":
    unittest.main()
