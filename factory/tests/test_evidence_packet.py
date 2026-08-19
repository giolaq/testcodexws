import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


FACTORY = Path(__file__).parents[1] / "orchestrator.py"
sys.path.insert(0, str(Path(__file__).parents[1]))

from evidence_packet import validate_canvas


class EvidencePacketTests(unittest.TestCase):
    def test_unedited_canvas_template_is_rejected(self):
        template = Path(__file__).parents[1] / "FACTORY_CANVAS.md"
        with self.assertRaisesRegex(ValueError, "Factory Profile"):
            validate_canvas(template)

    def test_cli_exports_selected_sanitized_evidence_with_completed_canvas(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            fake_token = "sk-" + "a" * 24
            fake_environment = "OPENAI_API_KEY=" + "b" * 24
            metadata_token = "ghp_" + "c" * 24
            run = repo / ".factory/plans/demo-plan"
            run.mkdir(parents=True)
            stages = {}
            for name, filename, title in (
                ("product_review", "01-product-review", "Product Review"),
                ("system_architecture", "02-system-architecture", "System Architecture"),
                ("program_design", "03-program-design", "Program Design"),
                ("vertical_slices", "04-vertical-slices", "Vertical Slices"),
            ):
                (run / f"{filename}.md").write_text(f"# {title}\n\nAuditable content for {fake_token}.\n")
                (run / f"{filename}.json").write_text("{}\n")
                stages[name] = {"status": "complete", "sha256": f"sha-{name}"}
            (run / "traceability.json").write_text(json.dumps({
                "rows": [{
                    "requirement_id": "R3",
                    "product_behavior": "Complete the mobile journey",
                    "architecture_contracts": ["C1"],
                    "program_elements": ["FLOW-1"],
                    "slices": ["T3"],
                    "qa_evidence": [f"Mobile journey test {metadata_token}"],
                }],
            }))
            receipt_path = repo / ".factory/receipts/demo-plan/build-qa-ticket-12.json"
            receipt_path.parent.mkdir(parents=True)
            receipt_path.write_text(json.dumps({
                "role": "qa",
                "phase": "Build",
                "claimed_result": "Protected Acceptance Tests created",
                "verification": ["Policy passed"],
                "unresolved_risks": [],
                "policy_hashes": {"engineering": "abc"},
                "timestamp": "2026-08-19T10:00:00+00:00",
            }))
            manifest = {
                "plan_id": "demo-plan",
                "project": "TableStory",
                "profile": "standard",
                "status": "published",
                "policy": {"version": "workshop-policy-v1", "hashes": {"engineering": "abc"}},
                "approvals": {
                    "product": {"approved_at": "2026-08-19T09:00:00+00:00"},
                    "alignment": {"approved_at": "2026-08-19T09:30:00+00:00"},
                },
                "stages": stages,
                "revisions": [{
                    "revision": 1,
                    "stage": "product_review",
                    "feedback": "Replace the walkthrough with objective keyboard evidence.",
                    "before_sha256": "before-product",
                    "after_sha256": "after-product",
                    "created_at": "2026-08-19T08:45:00+00:00",
                }],
                "receipts": [str(receipt_path.relative_to(repo))],
                "publication": {"url": "https://github.com/example/repo/issues/12"},
            }
            (run / "manifest.json").write_text(json.dumps(manifest))
            state_path = repo / ".factory/state.json"
            state_path.write_text(json.dumps({
                "tickets": [{
                    "number": 12,
                    "plan_id": "demo-plan",
                    "title": f"Mobile recipe journey {metadata_token}",
                    "status": "Done",
                    "dependencies": [10, 11],
                    "issue_url": "https://github.com/example/repo/issues/12",
                    "pr_url": "",
                    "qa_tests": {"demo-app/tests/test_ticket_12_mobile.py": "blob-sha"},
                    "gate_results": [{
                        "name": "api-tests", "required": True, "exit_code": 0,
                        "output": fake_environment, "duration_seconds": 1.2,
                    }],
                    "receipts": [str(receipt_path.relative_to(repo))],
                    "current_prompt": ".factory/prompts/raw-secret.md",
                    "current_log": ".factory/logs/raw-secret.log",
                }, {
                    "number": 99,
                    "plan_id": "another-plan",
                    "title": "Unrelated run must not leak into this packet",
                    "status": "Done",
                }],
            }))
            canvas = repo / "factory-canvas.md"
            canvas.write_text("""# Factory Canvas

Version: 1

## Use case
Change a recipe journey safely.

## Factory Profile
Standard, because user-visible behavior needs independent evidence.

## Agent Roles
Product, architecture, program, slices, QA, implementation, and review.

## Human Gates
Product, alignment, Acceptance Test, and merge approval.

## Execution environment
Isolated local Git worktrees.

## Required evidence
Planning trace, protected tests, gates, receipts, and review links.

## Recovery policy
Retry twice, then block for human diagnosis.

## First Vertical Slice
Browse, open, and save one recipe on mobile.

## Peer review
Reviewed by Sam; reduce Assured controls until the data becomes regulated.
""")

            result = subprocess.run(
                [
                    sys.executable,
                    str(FACTORY),
                    "evidence",
                    "demo-plan",
                    "--repo",
                    str(repo),
                    "--canvas",
                    "factory-canvas.md",
                    "--ticket",
                    "12",
                ],
                text=True,
                capture_output=True,
                check=True,
            )

            output = repo / ".factory/evidence/demo-plan"
            packet = (output / "evidence-packet.md").read_text()
            exported = json.loads((output / "manifest.json").read_text())
            self.assertIn(str(output / "evidence-packet.md"), result.stdout)
            self.assertIn("# Evidence Packet — TableStory", packet)
            self.assertIn("## Factory Canvas", packet)
            self.assertIn("Mobile recipe journey", packet)
            self.assertNotIn("Unrelated run", packet)
            self.assertIn("Protected Acceptance Tests created", packet)
            self.assertIn("Replace the walkthrough with objective keyboard evidence.", packet)
            self.assertIn("before-product", packet)
            self.assertIn("after-product", packet)
            self.assertIn("Missing evidence", packet)
            self.assertIn("Pull request link is missing", packet)
            self.assertEqual(exported["tickets"], [12])
            combined = packet + json.dumps(exported)
            for secret in (
                fake_token, fake_environment, metadata_token,
                "OPENAI_API_KEY", "raw-secret",
            ):
                self.assertNotIn(secret, combined)


if __name__ == "__main__":
    unittest.main()
