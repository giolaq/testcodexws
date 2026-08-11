import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parents[1]))

from doctor import baseline_check, version_tuple
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

    def baseline_repo(self, root: Path) -> Path:
        """Build a repo whose history holds a mobile baseline and a later rehearsal."""
        repo = root / "repo"
        repo.mkdir()
        git(repo, "init", "-q", "-b", "main")
        git(repo, "config", "user.name", "Factory Test")
        git(repo, "config", "user.email", "factory@example.test")
        (repo / "demo-app").mkdir()
        (repo / "demo-app/tests").mkdir()
        (repo / "demo-app/tests/test_app.py").write_text("def test_app():\n    assert True\n")
        git(repo, "add", ".")
        git(repo, "commit", "-qm", "chore: establish factory workshop baseline")
        for name in ("test_device_mode.py", "test_rails.py", "test_tv_detail.py"):
            (repo / "demo-app/tests" / name).write_text("def test_tv():\n    assert True\n")
        git(repo, "add", ".")
        git(repo, "commit", "-qm", "feat: finish the TV rehearsal")
        return repo

    def test_baseline_check_rejects_tag_left_on_a_finished_rehearsal(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = self.baseline_repo(Path(directory))
            git(repo, "tag", "factory-baseline", "HEAD")
            result = baseline_check(repo)
            self.assertEqual(result.level, "FAIL")
            self.assertIn("test_device_mode.py", result.detail)
            self.assertIn("rerun setup_demo.sh", result.detail)

    def test_baseline_check_accepts_the_mobile_workpiece(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = self.baseline_repo(Path(directory))
            baseline = git(repo, "rev-list", "--max-count=1", "--grep=^chore: establish", "HEAD")
            git(repo, "tag", "factory-baseline", baseline)
            self.assertEqual(baseline_check(repo).level, "PASS")

    def test_baseline_check_reports_an_unrecoverable_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "repo"
            repo.mkdir()
            git(repo, "init", "-q", "-b", "main")
            git(repo, "config", "user.name", "Factory Test")
            git(repo, "config", "user.email", "factory@example.test")
            (repo / "demo-app/tests").mkdir(parents=True)
            (repo / "demo-app/tests/test_rails.py").write_text("def test_tv():\n    assert True\n")
            git(repo, "add", ".")
            git(repo, "commit", "-qm", "chore: import workshop without history")
            git(repo, "tag", "factory-baseline", "HEAD")
            result = baseline_check(repo)
            self.assertEqual(result.level, "FAIL")
            self.assertIn("re-clone", result.detail)

    def test_setup_repoints_a_baseline_tag_left_on_a_rehearsal(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = self.baseline_repo(Path(directory))
            (repo / "factory").mkdir()
            (repo / "factory/orchestrator.py").write_text("")
            (repo / "demo-app/app.py").write_text("")
            (repo / "demo-app/requirements.txt").write_text("")
            # The script resolves its repository from its own location, so it has
            # to run from a copy inside the fixture rather than from the checkout.
            script = repo / "factory/setup_demo.sh"
            script.write_bytes((Path(__file__).parents[1] / "setup_demo.sh").read_bytes())
            script.chmod(0o755)
            # A stub interpreter keeps the dependency install out of a unit test.
            stub = repo / ".factory/venv/bin"
            stub.mkdir(parents=True)
            (stub / "python").write_text("#!/bin/sh\nexit 0\n")
            (stub / "python").chmod(0o755)
            git(repo, "add", ".")
            git(repo, "commit", "-qm", "chore: add factory scaffolding")
            rehearsal = git(repo, "rev-parse", "HEAD")
            git(repo, "tag", "factory-baseline", rehearsal)
            proc = subprocess.run(
                ["sh", str(script), "--scenario", "recipe-rebrand", "--force"],
                cwd=repo, text=True, capture_output=True, timeout=120,
            )
            tagged = git(repo, "rev-parse", "refs/tags/factory-baseline^{commit}")
            expected = git(repo, "rev-list", "--max-count=1", "--grep=^chore: establish", "HEAD")
            self.assertEqual(tagged, expected, proc.stdout + proc.stderr)
            self.assertNotEqual(tagged, rehearsal)


if __name__ == "__main__":
    unittest.main()
