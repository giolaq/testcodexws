import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parents[1]))

from github_repository import (
    GitHubRepositoryError,
    checkout_github_repository,
    connect_github_repository,
    managed_checkout_path,
    parse_github_repository,
)


def completed(command, returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(command, returncode, stdout, stderr)


class GitHubRepositoryTests(unittest.TestCase):
    def test_normalizes_https_ssh_and_owner_name_inputs(self):
        expected = "https://github.com/example/workshop"
        for value in (
            expected,
            expected + ".git",
            "git@github.com:example/workshop.git",
            "example/workshop",
        ):
            with self.subTest(value=value):
                self.assertEqual(parse_github_repository(value).url, expected)

    def test_rejects_non_github_and_command_like_values(self):
        for value in (
            "https://gitlab.com/example/workshop",
            "https://github.com/example/workshop/issues",
            "example/workshop; rm -rf repo",
        ):
            with self.subTest(value=value):
                with self.assertRaises(GitHubRepositoryError):
                    parse_github_repository(value)

    def test_connect_rejects_a_different_origin_instead_of_rewriting_it(self):
        calls = []

        def runner(command, **kwargs):
            calls.append(command)
            if command[:3] == ["gh", "repo", "view"]:
                return completed(command, stdout=json.dumps({"nameWithOwner": "attendee/demo"}))
            if command[:4] == ["git", "remote", "get-url", "origin"]:
                return completed(command, stdout="https://github.com/giolaq/software-refactory-workshop.git\n")
            return completed(command)

        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "github_repository.shutil.which", return_value="/usr/local/bin/gh",
        ):
            with self.assertRaisesRegex(GitHubRepositoryError, "different GitHub repository"):
                connect_github_repository(
                    Path(directory), "https://github.com/attendee/demo", runner=runner,
                )

        self.assertNotIn("set-url", [part for call in calls for part in call])

    def test_checkout_clones_to_an_isolated_managed_path(self):
        calls = []

        def runner(command, **kwargs):
            calls.append(command)
            if command[:3] == ["gh", "repo", "view"]:
                return completed(command, stdout=json.dumps({"nameWithOwner": "attendee/demo"}))
            if command[:3] == ["gh", "repo", "clone"]:
                destination = Path(command[4])
                (destination / ".git").mkdir(parents=True)
            return completed(command)

        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "github_repository.shutil.which", return_value="/usr/local/bin/gh",
        ):
            root = Path(directory)
            expected = managed_checkout_path(root, parse_github_repository("attendee/demo"))
            result = checkout_github_repository(root, "https://github.com/attendee/demo", runner=runner)

        self.assertEqual(Path(result["path"]), expected)
        self.assertEqual(result["action"], "cloned")
        self.assertIn(["gh", "repo", "clone", "attendee/demo", str(expected)], calls)


if __name__ == "__main__":
    unittest.main()
