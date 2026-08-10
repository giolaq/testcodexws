import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parents[1]))

from doctor import version_tuple
from orchestrator import Factory, approve_qa_tests


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, text=True, capture_output=True, check=True,
    ).stdout.strip()


class RuntimeTests(unittest.TestCase):
    def factory_args(self, repo: Path):
        return SimpleNamespace(
            repo=str(repo), qa_agent=None, no_qa=True, mock=True, project_number=None,
            review_qa_tests=False, scenario="tv", agent="mock", dry_run=False,
            max_parallel=1, once=True,
        )

    def test_default_branch_sync_fast_forwards_before_new_work(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, remote, checkout = root / "source", root / "remote.git", root / "checkout"
            source.mkdir()
            git(source, "init", "-q", "-b", "main")
            git(source, "config", "user.name", "Factory Test")
            git(source, "config", "user.email", "factory@example.test")
            (source / ".gitignore").write_text(".factory/\n")
            (source / "value.txt").write_text("one\n")
            git(source, "add", ".")
            git(source, "commit", "-qm", "one")
            git(root, "clone", "-q", "--bare", str(source), str(remote))
            git(root, "clone", "-q", str(remote), str(checkout))
            git(source, "remote", "add", "origin", str(remote))
            (source / "value.txt").write_text("two\n")
            git(source, "add", "value.txt")
            git(source, "commit", "-qm", "two")
            git(source, "push", "-q", "origin", "main")

            factory = Factory(self.factory_args(checkout))
            factory.backend = SimpleNamespace(default_branch="main")
            synced = factory.sync_default_branch()
            self.assertEqual((checkout / "value.txt").read_text(), "two\n")
            self.assertEqual(synced, git(source, "rev-parse", "HEAD"))

    def test_qa_approval_writes_resume_marker_after_hash_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "repo"
            worktree = Path(directory) / "wt-12"
            repo.mkdir(); worktree.mkdir()
            git(worktree, "init", "-q", "-b", "main")
            git(worktree, "config", "user.name", "Factory Test")
            git(worktree, "config", "user.email", "factory@example.test")
            test = worktree / "demo-app/tests/test_ticket_12_search.py"
            test.parent.mkdir(parents=True)
            test.write_text("def test_search():\n    assert True\n")
            git(worktree, "add", ".")
            git(worktree, "commit", "-qm", "qa tests")
            commit = git(worktree, "rev-parse", "HEAD")
            blob = git(worktree, "hash-object", "demo-app/tests/test_ticket_12_search.py")
            state = {
                "tickets": [{
                    "number": 12, "title": "Search", "status": "QA Review",
                    "qa_commit": commit,
                    "qa_tests": {"demo-app/tests/test_ticket_12_search.py": blob},
                }],
            }
            state_path = repo / ".factory/state.json"
            state_path.parent.mkdir(parents=True)
            state_path.write_text(json.dumps(state))
            approve_qa_tests(repo, 12, assume_yes=True)
            self.assertTrue((repo / ".factory/qa-approvals/12").is_file())

    def test_version_parser_handles_cli_prefixes(self):
        self.assertEqual(version_tuple("v22.4.1"), (22, 4, 1))
        self.assertEqual(version_tuple("3.11.9"), (3, 11, 9))


if __name__ == "__main__":
    unittest.main()
