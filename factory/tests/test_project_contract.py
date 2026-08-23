import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from project_contract import ProjectContract, ProjectContractError
from orchestrator import (
    initialize_project,
    prepare_project,
    reset_project,
    validate_protected_changes,
)


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, text=True, capture_output=True, check=True,
    ).stdout.strip()


class ProjectContractTests(unittest.TestCase):
    def make_repo(self, root: str) -> Path:
        repo = Path(root)
        git(repo, "init", "-q", "-b", "main")
        git(repo, "config", "user.name", "Factory Test")
        git(repo, "config", "user.email", "factory@example.invalid")
        return repo

    def test_detects_python_repository_without_demo_app_assumptions(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = self.make_repo(directory)
            (repo / "src/example").mkdir(parents=True)
            (repo / "tests").mkdir()
            (repo / "pyproject.toml").write_text('[project]\nname = "sample-api"\n')
            (repo / "tests/test_api.py").write_text("def test_api(): assert True\n")

            contract = ProjectContract.detect(repo)

            self.assertEqual(contract.name, "sample-api")
            self.assertIn("src", contract.source_roots)
            self.assertIn("tests", contract.test_roots)
            self.assertTrue(any("pytest" in gate["cmd"] for gate in contract.gates))
            self.assertNotIn("demo-app", contract.context())

    def test_detects_node_repository_and_writes_a_round_trippable_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = self.make_repo(directory)
            (repo / "src").mkdir()
            (repo / "test").mkdir()
            (repo / "package-lock.json").write_text("{}\n")
            (repo / "package.json").write_text(json.dumps({
                "name": "sample-web",
                "scripts": {"test": "vitest run", "lint": "eslint .", "build": "vite build"},
            }))

            detected = ProjectContract.detect(repo)
            path = detected.write()
            loaded = ProjectContract.load(repo, require=True)

            self.assertEqual(path, repo.resolve() / "factory.project.toml")
            self.assertEqual(loaded.name, "sample-web")
            self.assertEqual(loaded.setup_commands, ("npm ci",))
            self.assertEqual([gate["name"] for gate in loaded.gates], ["tests", "lint", "build"])

    def test_generic_repository_always_has_a_reviewable_integrity_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = self.make_repo(directory)
            (repo / "README.md").write_text("# Documentation project\n")

            contract = ProjectContract.detect(repo)

            self.assertEqual(contract.gates, ({
                "name": "repository-integrity", "cmd": "git diff --check", "required": True,
                "level": "fast",
            },))
            self.assertEqual(contract.test_roots, ("tests",))

    def test_contract_rejects_paths_that_escape_the_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = self.make_repo(directory)
            (repo / "factory.project.toml").write_text('''schema_version = 1
[project]
name = "unsafe"
default_branch = "main"
source_roots = ["../private"]
protected_paths = []
[environment]
required_tools = ["git"]
setup = []
ports = []
[qa]
test_roots = ["tests"]
test_file_patterns = ["test_ticket_{ticket}*.py"]
[[gate]]
name = "tests"
cmd = "pytest"
required = true
''')

            with self.assertRaisesRegex(ProjectContractError, "inside the repository"):
                ProjectContract.load(repo, require=True)

            text = (repo / "factory.project.toml").read_text().replace(
                'source_roots = ["../private"]', 'source_roots = ["/private"]',
            )
            (repo / "factory.project.toml").write_text(text)
            with self.assertRaisesRegex(ProjectContractError, "inside the repository"):
                ProjectContract.load(repo, require=True)

    def test_context_is_bounded_and_excludes_runtime_and_vendor_files(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = self.make_repo(directory)
            (repo / "src").mkdir()
            (repo / ".factory/logs").mkdir(parents=True)
            (repo / "node_modules/pkg").mkdir(parents=True)
            (repo / "src/main.py").write_text("print('ok')\n")
            (repo / ".factory/logs/secret.log").write_text("secret\n")
            (repo / "node_modules/pkg/index.js").write_text("vendor\n")
            git(repo, "add", ".")
            git(repo, "commit", "-qm", "fixture")

            context = ProjectContract.detect(repo).context(max_files=20)

            self.assertIn("src/main.py", context)
            self.assertNotIn("secret.log", context)
            self.assertNotIn("node_modules", context)

    def test_detection_uses_the_repository_default_branch_from_main(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = self.make_repo(directory)
            (repo / "README.md").write_text("# Project\n")
            git(repo, "add", ".")
            git(repo, "commit", "-qm", "initial")
            git(repo, "switch", "-qc", "feature/work")

            contract = ProjectContract.detect(repo)

            self.assertEqual(contract.default_branch, "main")

    def test_initialize_and_prepare_are_explicit_reviewable_steps(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = self.make_repo(directory)
            (repo / "package.json").write_text(json.dumps({"name": "generic-ui", "scripts": {}}))

            path = initialize_project(repo, None, False)
            self.assertIn(".factory/", (repo / ".gitignore").read_text())
            text = path.read_text().replace(
                'setup = ["npm install"]',
                'setup = ["printf prepared > setup-result.txt"]',
            )
            path.write_text(text)
            prepare_project(repo, assume_yes=True)

            self.assertEqual((repo / "setup-result.txt").read_text(), "prepared")

    def test_local_state_reset_never_invokes_the_repository_reset_adapter(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = self.make_repo(directory)
            (repo / "README.md").write_text("# Keep me\n")
            ProjectContract.detect(repo).write()
            contract = (repo / "factory.project.toml").read_text() + '''
[reset]
command = ["/usr/bin/touch", "adapter-ran"]
start_over_flag = "--start-over"
'''
            (repo / "factory.project.toml").write_text(contract)
            (repo / ".factory/logs").mkdir(parents=True)
            (repo / ".factory/logs/old.log").write_text("old\n")

            reset_project(
                repo, scenario="recipe-rebrand", start_over=True,
                local_state_only=True,
            )

            self.assertFalse((repo / "adapter-ran").exists())
            self.assertEqual((repo / "README.md").read_text(), "# Keep me\n")
            self.assertEqual(json.loads((repo / ".factory/state.json").read_text())["tickets"], [])

    def test_contract_rejects_unknown_command_placeholders(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = self.make_repo(directory)
            contract = ProjectContract.detect(repo)
            contract.write()
            path = repo / "factory.project.toml"
            path.write_text(path.read_text().replace("git diff --check", "echo {secret}"))

            with self.assertRaisesRegex(ProjectContractError, "unsupported placeholders"):
                ProjectContract.load(repo, require=True)

    def test_project_contract_and_declared_policy_paths_are_protected(self):
        errors = validate_protected_changes(
            [
                "src/main.py", ".github/workflows/release.yml",
                "factory.project.toml", "factory.charter.toml",
            ],
            (".github/workflows",),
            ("factory.charter.toml",),
        )

        self.assertEqual(len(errors), 3)
        self.assertTrue(all("protected" in error for error in errors))
        self.assertTrue(any("Factory Charter" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
