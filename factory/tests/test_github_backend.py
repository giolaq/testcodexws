import subprocess
import sys
import unittest
import tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parents[1]))

from github_backend import GitHubBackend, GitHubError
from orchestrator import reset_project


def completed(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(["gh"], returncode, stdout, stderr)


class GitHubReviewTests(unittest.TestCase):
    def test_remote_claim_is_atomic_resumable_and_explicitly_released(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            remote = root / "remote.git"
            first = root / "first"
            second = root / "second"
            source.mkdir()
            subprocess.run(["git", "init", "-q", "-b", "main"], cwd=source, check=True)
            subprocess.run(["git", "config", "user.name", "Factory Test"], cwd=source, check=True)
            subprocess.run(["git", "config", "user.email", "factory@example.test"], cwd=source, check=True)
            (source / "README.md").write_text("target\n")
            subprocess.run(["git", "add", "."], cwd=source, check=True)
            subprocess.run(["git", "commit", "-qm", "base"], cwd=source, check=True)
            subprocess.run(["git", "clone", "-q", "--bare", str(source), str(remote)], cwd=root, check=True)
            subprocess.run(["git", "clone", "-q", str(remote), str(first)], cwd=root, check=True)
            subprocess.run(["git", "clone", "-q", str(remote), str(second)], cwd=root, check=True)
            base = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=first, text=True, capture_output=True, check=True,
            ).stdout.strip()
            one = GitHubBackend(first)
            two = GitHubBackend(second)
            for backend in (one, two):
                backend.owner, backend.name = "attendee", "project"
                backend.gh = mock.Mock(return_value=completed())

            won = one.claim_ticket({"number": 7}, "run-one", base)
            lost = two.claim_ticket({"number": 7}, "run-two", base)
            resumed = one.claim_ticket({"number": 7}, "run-one", base)

            self.assertTrue(won["owned"])
            self.assertRegex(won["claimed_at"], r"^\d{4}-\d{2}-\d{2}T")
            self.assertFalse(lost["owned"])
            self.assertEqual(lost["owner_run_id"], "run-one")
            self.assertTrue(resumed["resumed"])
            reset_project(
                first, scenario="recipe-rebrand", start_over=False, local_state_only=True,
            )
            self.assertEqual(two.read_claim(7)["run_id"], "run-one")
            with self.assertRaisesRegex(GitHubError, "owned by run-one"):
                two.release_claim(7, "run-two", reason="abandoned runner")
            released = one.release_claim(7, "run-one", reason="operator confirmed abandonment")
            self.assertTrue(released["released"])
            remote_ref = subprocess.run(
                ["git", "ls-remote", "origin", "refs/heads/factory-claims/ticket-7"],
                cwd=first, text=True, capture_output=True, check=True,
            ).stdout.strip()
            self.assertEqual(remote_ref, "")

    def test_preflight_uses_the_saved_repository_instead_of_gh_default(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            local = repo / ".factory/local.toml"
            local.parent.mkdir()
            local.write_text('github_repository = "https://github.com/attendee/workshop"\n')
            backend = GitHubBackend(repo)
            backend.gh = mock.Mock(side_effect=[
                completed(),
                completed(stdout='{"nameWithOwner":"attendee/workshop","defaultBranchRef":{"name":"main"}}'),
            ])
            origin = completed(stdout="https://github.com/attendee/workshop.git\n")

            with mock.patch("github_backend.shutil.which", return_value="/usr/bin/gh"), mock.patch(
                "github_backend.subprocess.run", return_value=origin,
            ):
                backend.preflight()

        self.assertEqual(
            backend.gh.call_args_list[1].args[:4],
            ("repo", "view", "attendee/workshop", "--json"),
        )

    def test_publishes_a_formal_github_approval_when_identity_allows_it(self):
        backend = GitHubBackend(Path.cwd())
        backend.gh = mock.Mock(return_value=completed())

        with mock.patch.dict("os.environ", {"FACTORY_REVIEW_GH_TOKEN": ""}):
            result = backend.submit_agent_review(
                "https://github.test/example/pull/7", "APPROVE", "Approved candidate.",
            )

        self.assertEqual(result, {
            "published": True, "official": True, "mode": "github-review",
        })
        backend.gh.assert_called_once_with(
            "pr", "review", "https://github.test/example/pull/7", "--approve",
            "--body", "Approved candidate.", check=False,
        )

    def test_falls_back_to_an_explicit_factory_comment_for_self_review(self):
        backend = GitHubBackend(Path.cwd())
        backend.gh = mock.Mock(side_effect=[
            completed(1, stderr="Can not approve your own pull request"),
            completed(),
        ])

        with mock.patch.dict("os.environ", {"FACTORY_REVIEW_GH_TOKEN": ""}):
            result = backend.submit_agent_review(
                "https://github.test/example/pull/7", "APPROVE", "Approved candidate.",
            )

        self.assertFalse(result["official"])
        self.assertEqual(result["mode"], "factory-comment")
        fallback = backend.gh.call_args_list[1].args
        self.assertEqual(fallback[:3], ("pr", "comment", "https://github.test/example/pull/7"))
        self.assertIn("does not satisfy branch-protection", fallback[-1])

    def test_optional_reviewer_token_is_scoped_to_the_review_command(self):
        backend = GitHubBackend(Path.cwd())
        backend.gh = mock.Mock(return_value=completed())

        with mock.patch.dict("os.environ", {"FACTORY_REVIEW_GH_TOKEN": "reviewer-secret"}):
            result = backend.submit_agent_review(
                "https://github.test/example/pull/7", "APPROVE", "Approved candidate.",
            )

        self.assertTrue(result["official"])
        review_env = backend.gh.call_args.kwargs["env"]
        self.assertEqual(review_env["GH_TOKEN"], "reviewer-secret")

    def test_remote_run_summary_updates_instead_of_duplicating(self):
        backend = GitHubBackend(Path.cwd())
        backend.owner, backend.name = "attendee", "project"
        marker = "<!-- factory-run:v1 ticket=7 run=run-1 -->"
        backend.json = mock.Mock(side_effect=[
            [{"url": "https://api.github.test/comments/9", "html_url": "https://github.test/comment/9", "body": marker + "\nold"}],
            {"html_url": "https://github.test/comment/9"},
        ])

        result = backend.publish_run_summary(7, "run-1", marker + "\nnew")

        self.assertEqual(result["mode"], "updated")
        self.assertEqual(backend.json.call_args_list[1].args[1:3], ("--method", "PATCH"))

    def test_latest_remote_run_summary_is_recovered_from_issue_comments(self):
        from run_summary import render_factory_run_summary

        backend = GitHubBackend(Path.cwd())
        backend.owner, backend.name = "attendee", "project"
        old = {
            "schema_version": 1, "run_id": "run-old", "ticket": 7,
            "status": "Verifying", "revisions": {"approved_head": "a" * 40},
        }
        latest = {
            "schema_version": 1, "run_id": "run-new", "ticket": 7,
            "status": "In Review", "revisions": {"approved_head": "b" * 40},
        }
        backend.json = mock.Mock(return_value=[
            {"body": render_factory_run_summary(latest), "updated_at": "2026-08-23T12:00:00Z"},
            {"body": "unrelated", "updated_at": "2026-08-23T13:00:00Z"},
            {"body": render_factory_run_summary(old), "updated_at": "2026-08-23T11:00:00Z"},
        ])

        recovered = backend.read_run_summary(7)

        self.assertEqual(recovered["run_id"], "run-new")
        self.assertEqual(recovered["revisions"]["approved_head"], "b" * 40)

    def test_rejects_a_pr_head_that_changed_after_approval(self):
        backend = GitHubBackend(Path.cwd())
        backend.json = mock.Mock(return_value={"headRefOid": "new-head"})

        with self.assertRaisesRegex(GitHubError, "changed after"):
            backend.assert_pr_head("https://github.test/example/pull/7", "approved-head")


if __name__ == "__main__":
    unittest.main()
