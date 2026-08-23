import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).parents[1]))

from doctor import baseline_check, run_doctor, version_tuple
from orchestrator import (
    Factory,
    approve_qa_tests,
    human_merge_ticket,
    publish_repository_setup,
    recover_remote_ticket_state,
    worktree_path,
)
from factory_charter import FactoryCharter
from planner import governance_marker
from project_contract import ProjectContract


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, text=True, capture_output=True, check=True,
    ).stdout.strip()


def install_approved_charter(repo: Path, merge_authority: str = "human") -> None:
    project = ProjectContract.load(repo) if (repo / "factory.project.toml").is_file() else ProjectContract.detect(repo)
    charter = FactoryCharter.draft(repo, project)
    charter.write()
    if merge_authority != "human":
        path = repo / "factory.charter.toml"
        path.write_text(path.read_text().replace(
            'merge_authority = "human"', f'merge_authority = "{merge_authority}"',
        ))
    FactoryCharter.load(repo).approve()


class RuntimeTests(unittest.TestCase):
    def test_publish_repository_setup_commits_and_pushes_only_approved_governance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            remote = root / "remote.git"
            repo.mkdir()
            git(repo, "init", "-q", "-b", "main")
            git(repo, "config", "user.name", "Factory Test")
            git(repo, "config", "user.email", "factory@example.test")
            git(root, "init", "-q", "--bare", str(remote))
            git(repo, "remote", "add", "origin", str(remote))
            project = ProjectContract.detect(repo)
            project.write()
            charter = FactoryCharter.draft(repo, project)
            charter.write()
            charter.approve()
            (repo / ".gitignore").write_text(".factory/\n")

            commit = publish_repository_setup(repo, assume_yes=True)

            self.assertEqual(commit, git(repo, "rev-parse", "HEAD"))
            self.assertEqual(commit, git(root, "--git-dir", str(remote), "rev-parse", "refs/heads/main"))
            self.assertEqual(
                set(git(repo, "show", "--pretty=", "--name-only", "HEAD").splitlines()),
                {".gitignore", "factory.charter.toml", "factory.project.toml"},
            )

    def test_worktree_paths_are_scoped_to_the_repository(self):
        root = Path("/tmp/workshops")
        first = worktree_path(root / "attendee-one", 4)
        second = worktree_path(root / "attendee-two", 4)

        self.assertEqual(first, root / "attendee-one-wt-4")
        self.assertEqual(second, root / "attendee-two-wt-4")
        self.assertNotEqual(first, second)

    def test_dispatch_pauses_when_human_review_capacity_is_full(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "repo"
            source = Path(__file__).parents[2]
            shutil.copytree(source / "factory", repo / "factory")
            install_approved_charter(repo)
            factory = Factory(self.factory_args(repo))
            ready = {"number": 9, "status": "Ready", "history": []}
            factory.tickets = {
                1: {"number": 1, "status": "In Review", "history": []},
                2: {"number": 2, "status": "QA Review", "history": []},
                3: {"number": 3, "status": "In Review", "history": []},
                9: ready,
            }

            self.assertEqual(factory.coordinate_ready([ready]), [])
            attention = factory.store.data["human_attention"]
            self.assertTrue(attention["dispatch_paused"])
            self.assertEqual(attention["awaiting_review"], 3)
            self.assertEqual(attention["review_limit"], 3)
            self.assertIn("queue 3 / limit 3", attention["reason"])
            factory.tickets[1]["status"] = "Done"
            resumed = factory.coordinate_ready([ready])
            self.assertEqual(resumed, [ready])
            self.assertFalse(factory.store.data["human_attention"]["dispatch_paused"])

    def test_losing_remote_claim_never_creates_a_worktree_or_starts_an_agent(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "repo"
            source = Path(__file__).parents[2]
            shutil.copytree(source / "factory", repo / "factory")
            install_approved_charter(repo)
            factory = Factory(self.factory_args(repo))
            factory.backend = mock.Mock()
            factory.backend.claim_ticket.return_value = {
                "owned": False,
                "owner_run_id": "other-run",
                "ref": "refs/heads/factory-claims/ticket-9",
            }
            ticket = {
                "number": 9, "title": "Claimed work", "status": "Ready",
                "history": [], "failure": "", "branch": "", "qa_commit": "",
                "qa_approved": False,
            }
            factory.tickets = {9: ticket}

            with mock.patch.object(
                factory, "git", return_value=SimpleNamespace(stdout="a" * 40 + "\n")
            ), mock.patch.object(factory, "create_worktree") as create:
                factory.process(ticket)

            create.assert_not_called()
            self.assertEqual(ticket["status"], "Blocked")
            self.assertIn("other-run", ticket["failure"])

    def factory_args(self, repo: Path):
        return SimpleNamespace(
            repo=str(repo), qa_agent=None, no_qa=True, mock=True, project_number=None,
            review_qa_tests=False, scenario="tv", agent="mock", dry_run=False,
            max_parallel=1, once=True, profile="lean",
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
            install_approved_charter(source)
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

    def test_blocked_state_retains_the_phase_where_failure_occurred(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "repo"
            repo.mkdir()
            install_approved_charter(repo)
            factory = Factory(self.factory_args(repo))
            ticket = {
                "number": 7,
                "status": "Verifying",
                "phase": "verifying",
                "history": [],
            }
            factory.tickets = {7: ticket}

            factory.transition(ticket, "Blocked", "Required gate failed")

            self.assertEqual(ticket["status"], "Blocked")
            self.assertEqual(ticket["phase"], "verifying")

    def test_fresh_checkout_recovers_exact_pr_review_and_next_human_action(self):
        approved = "d" * 40
        summary = {
            "schema_version": 1,
            "run_id": "remote-run",
            "ticket": 7,
            "status": "In Review",
            "plan_id": "plan12345",
            "revisions": {"base": "a" * 40, "qa": "b" * 40, "approved_head": approved},
            "verdicts": {"red": "RED PROVED", "green": "GREEN PROVED", "code_review": "APPROVE"},
            "gates": [{"name": "tests", "required": True, "classification": "PASS", "exit_code": 0}],
            "metrics": {"attempts": 2, "qa_attempts": 1, "retry_count": 1},
            "human_decisions": {"qa_approved": True, "merge_executed_by": ""},
        }
        raw = {
            "status": "In Review",
            "pr_url": "https://github.test/pull/9",
            "pull_request": {
                "state": "OPEN", "mergedAt": None, "headRefName": "factory/7-slice",
                "headRefOid": approved, "mergeCommit": None,
            },
        }

        recovered = recover_remote_ticket_state(raw, summary)

        self.assertEqual(recovered["status"], "In Review")
        self.assertEqual(recovered["approved_head"], approved)
        self.assertEqual(recovered["branch"], "factory/7-slice")
        self.assertEqual(recovered["code_review"]["result"]["decision"], "APPROVE")
        self.assertTrue(recovered["qa_approved"])
        self.assertEqual(recovered["next_human_action"], "merge_exact_revision")

    def test_fresh_checkout_blocks_when_pr_head_no_longer_matches_remote_approval(self):
        summary = {
            "schema_version": 1, "run_id": "remote-run", "ticket": 7,
            "revisions": {"approved_head": "a" * 40},
            "verdicts": {"code_review": "APPROVE"},
        }
        raw = {
            "status": "In Review",
            "pull_request": {"state": "OPEN", "headRefOid": "b" * 40},
        }

        recovered = recover_remote_ticket_state(raw, summary)

        self.assertEqual(recovered["status"], "Blocked")
        self.assertIn("changed after the remote approval", recovered["failure"])
        self.assertEqual(recovered["next_human_action"], "rerun_code_review")

    def test_load_tickets_reconstructs_remote_pr_and_claim_without_local_state(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "repo"
            source = Path(__file__).parents[2]
            shutil.copytree(source / "factory", repo / "factory")
            install_approved_charter(repo)
            args = self.factory_args(repo)
            args.mock = False
            args.no_qa = False
            args.profile = "standard"
            args.agent = args.qa_agent = "claude"
            args.supervisor_agent = args.review_agent = "claude"
            factory = Factory(args)
            approved = "d" * 40
            remote_summary = {
                "schema_version": 1, "run_id": "remote-run", "ticket": 7,
                "status": "In Review", "plan_id": "",
                "revisions": {"base": "a" * 40, "qa": "b" * 40, "approved_head": approved},
                "verdicts": {"red": "RED PROVED", "green": "GREEN PROVED", "code_review": "APPROVE"},
                "human_decisions": {"qa_approved": True},
            }
            backend = SimpleNamespace(
                project_number=3,
                load=mock.Mock(return_value=[{
                    "number": 7, "title": "Recovered slice", "body": "", "labels": [],
                    "status": "In Review", "url": "https://github.test/issues/7",
                    "pr_url": "https://github.test/pull/9",
                    "pull_request": {
                        "url": "https://github.test/pull/9", "state": "OPEN",
                        "headRefName": "factory/7-recovered-slice", "headRefOid": approved,
                        "mergedAt": None, "mergeCommit": None,
                    },
                    "remote_run_summary": remote_summary,
                }]),
                read_claim=mock.Mock(return_value={
                    "ticket": 7, "run_id": "remote-run", "owner_run_id": "remote-run",
                    "base_revision": "a" * 40, "claim_sha": "c" * 40,
                }),
                set_status=mock.Mock(),
            )
            factory.backend = backend

            factory.load_tickets()

            ticket = factory.tickets[7]
            self.assertEqual(ticket["status"], "In Review")
            self.assertEqual(ticket["approved_head"], approved)
            self.assertEqual(ticket["remote_claim"]["run_id"], "remote-run")
            self.assertEqual(ticket["next_human_action"], "merge_exact_revision")
            backend.set_status.assert_not_called()

    def test_required_skipped_gate_is_misconfigured_not_green(self):
        factory = Factory.__new__(Factory)
        factory.cfg = {
            "factory": {"gate_timeout": 10},
            "gate": [{
                "name": "tests", "cmd": "printf '1 skipped\\n'",
                "required": True, "level": "full",
            }],
        }
        factory.project = SimpleNamespace(render_command=lambda command, python: command)
        factory.charter = SimpleNamespace(gate_level="full")
        factory.python = sys.executable
        factory._sync_store = mock.Mock()
        ticket = {"triage": {"controls": {"gate_level": "full"}}}

        failure = factory.verify(ticket, Path.cwd())

        self.assertIn("[tests] exit 0", failure)
        self.assertEqual(ticket["gate_results"][0]["classification"], "MISCONFIGURED")

    def test_live_agents_have_no_presentation_timeout(self):
        factory = Factory.__new__(Factory)
        factory.cfg = {"factory": {"agent_timeout": 900}}
        factory.capabilities = {}
        factory.args = SimpleNamespace(mock=False)
        self.assertIsNone(factory.adapter_timeout())

        factory.args.mock = True
        self.assertEqual(factory.adapter_timeout(), 900)

    def test_read_only_role_mutation_is_discarded_and_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "repo"
            repo.mkdir()
            git(repo, "init", "-q", "-b", "main")
            git(repo, "config", "user.name", "Factory Test")
            git(repo, "config", "user.email", "factory@example.test")
            (repo / "source.txt").write_text("before\n")
            git(repo, "add", ".")
            git(repo, "commit", "-qm", "base")
            before = git(repo, "rev-parse", "HEAD")
            prompt = Path(directory) / "prompt.md"; prompt.write_text("review\n")
            factory = Factory.__new__(Factory)
            factory.repo = repo
            factory.git = lambda *args, cwd=None, **kwargs: subprocess.run(
                ["git", *args], cwd=cwd or repo, text=True, capture_output=True,
                check=kwargs.get("check", True),
            )
            factory.make_role_prompt = mock.Mock(return_value=prompt)
            def mutate(*_args, **_kwargs):
                (repo / "source.txt").write_text("changed\n")
                (repo / "untracked.txt").write_text("leak\n")
                git(repo, "add", "source.txt")
                git(repo, "commit", "-qm", "forbidden review edit")
                return 0, "APPROVE"
            factory.run_adapter = mutate
            factory.verify_qa_tests_unchanged = mock.Mock(return_value="")
            factory.record_receipt = mock.Mock()
            ticket = {"number": 4, "agent": "codex", "attempt": 1}

            failure = factory.run_profile_role(
                ticket, repo, "critic", before, read_only=True,
            )

            self.assertIn("modified the worktree", failure)
            self.assertEqual(git(repo, "rev-parse", "HEAD"), before)
            self.assertEqual((repo / "source.txt").read_text(), "before\n")
            self.assertFalse((repo / "untracked.txt").exists())

    def test_rehearsal_loads_materialized_approved_slices_before_static_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "repo"
            source = Path(__file__).parents[2]
            shutil.copytree(source / "factory", repo / "factory")
            install_approved_charter(repo)
            plan_id = "approved-plan"
            governance = FactoryCharter.load(repo, require_approved=True).governance("lean")
            tickets_path = repo / ".factory/rehearsal" / plan_id / "tickets.json"
            tickets_path.parent.mkdir(parents=True)
            tickets_path.write_text(json.dumps([{
                "number": 1,
                "title": "Approved PRD-derived slice",
                "body": (
                    f"## Spec\nReviewed behavior\n\nagent: mock\n\n"
                    f"<!-- factory-plan:{plan_id}:T1 -->\n{governance_marker(governance)}"
                ),
                "labels": ["agent-ready"],
                "mock_action": "recipe-api",
            }]))
            latest = repo / ".factory/plans/latest.json"
            latest.parent.mkdir(parents=True, exist_ok=True)
            latest.write_text(json.dumps({"plan_id": plan_id}))

            factory = Factory(self.factory_args(repo))
            factory.load_tickets()

            self.assertEqual(factory.tickets[1]["title"], "Approved PRD-derived slice")
            self.assertEqual(factory.tickets[1]["plan_id"], plan_id)

    def test_execution_rejects_a_ticket_planned_under_different_governance(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "repo"
            source = Path(__file__).parents[2]
            shutil.copytree(source / "factory", repo / "factory")
            install_approved_charter(repo)
            charter = FactoryCharter.load(repo, require_approved=True)
            drifted = charter.governance("standard")
            plan_id = "drifted-plan"
            tickets_path = repo / ".factory/rehearsal" / plan_id / "tickets.json"
            tickets_path.parent.mkdir(parents=True)
            tickets_path.write_text(json.dumps([{
                "number": 1,
                "title": "Slice planned with another profile",
                "body": (
                    f"## Spec\nReviewed behavior\n\nagent: mock\n\n"
                    f"<!-- factory-plan:{plan_id}:T1 -->\n{governance_marker(drifted)}"
                ),
                "labels": ["agent-ready"],
                "mock_action": "recipe-api",
            }]))
            latest = repo / ".factory/plans/latest.json"
            latest.parent.mkdir(parents=True, exist_ok=True)
            latest.write_text(json.dumps({"plan_id": plan_id}))

            factory = Factory(self.factory_args(repo))
            with self.assertRaisesRegex(ValueError, "governance does not match"):
                factory.load_tickets()

    def test_legacy_approved_tickets_fail_with_a_governance_migration_instruction(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "repo"
            source = Path(__file__).parents[2]
            shutil.copytree(source / "factory", repo / "factory")
            install_approved_charter(repo)
            plan_id = "legacy-plan"
            tickets_path = repo / ".factory/rehearsal" / plan_id / "tickets.json"
            tickets_path.parent.mkdir(parents=True)
            tickets_path.write_text(json.dumps([{
                "number": 1,
                "title": "Legacy approved slice",
                "body": (
                    f"## Spec\nReviewed behavior\n\nagent: mock\n\n"
                    f"<!-- factory-plan:{plan_id}:T1 -->"
                ),
                "labels": ["agent-ready"],
                "mock_action": "recipe-api",
            }]))
            latest = repo / ".factory/plans/latest.json"
            latest.parent.mkdir(parents=True, exist_ok=True)
            latest.write_text(json.dumps({"plan_id": plan_id}))

            factory = Factory(self.factory_args(repo))
            with self.assertRaisesRegex(ValueError, "predates governed Tickets.*republish"):
                factory.load_tickets()

    def test_existing_run_cannot_silently_switch_to_a_new_charter_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "repo"
            source = Path(__file__).parents[2]
            shutil.copytree(source / "factory", repo / "factory")
            install_approved_charter(repo)
            args = self.factory_args(repo)
            Factory(args).load_tickets()

            charter_path = repo / "factory.charter.toml"
            charter_path.write_text(
                charter_path.read_text().replace(
                    "max_diff_lines = 800", "max_diff_lines = 801",
                )
            )
            FactoryCharter.load(repo).approve()

            with self.assertRaisesRegex(ValueError, "Factory Run governance changed.*reset"):
                Factory(args)

    def test_existing_standard_qa_run_requires_causal_evidence_migration(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "repo"
            source = Path(__file__).parents[2]
            shutil.copytree(source / "factory", repo / "factory")
            install_approved_charter(repo)
            args = self.factory_args(repo)
            args.profile = "standard"
            args.no_qa = False
            governance = Factory(args).governance
            state_path = repo / ".factory/state.json"
            state_path.parent.mkdir(parents=True)
            state_path.write_text(json.dumps({
                "profile": "standard",
                "governance": governance,
                "tickets": [{"number": 12, "qa_commit": "abc123", "qa_tests": {"tests/test_x.py": "blob"}}],
            }))

            with self.assertRaisesRegex(ValueError, "predates causal Acceptance Test evidence"):
                Factory(args)

    def test_qa_approval_writes_resume_marker_after_hash_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "repo"
            worktree = Path(directory) / "repo-wt-12"
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
            with self.assertRaisesRegex(ValueError, "RED PROVED"):
                approve_qa_tests(repo, 12, assume_yes=True)
            state["tickets"][0]["qa_evidence"] = {
                "focused_test_command": "python -m pytest -q demo-app/tests/test_ticket_12_search.py",
                "focused_test_command_sha256": Factory._command_sha256(
                    "python -m pytest -q demo-app/tests/test_ticket_12_search.py"
                ),
                "test_revision": commit,
                "red": {
                    "result": "RED PROVED",
                    "classification": "behavior_assertion",
                    "revision": commit,
                    "output": "assertion failed because search is not implemented",
                },
            }
            state_path.write_text(json.dumps(state))
            approve_qa_tests(repo, 12, assume_yes=True)
            self.assertTrue((repo / ".factory/qa-approvals/12").is_file())

    def test_version_parser_handles_cli_prefixes(self):
        self.assertEqual(version_tuple("v22.4.1"), (22, 4, 1))
        self.assertEqual(version_tuple("3.11.9"), (3, 11, 9))

    def test_basic_doctor_does_not_call_agent_authentication(self):
        config = {
            "agents": {},
            "qa": {"agent": "mock-qa", "max_retries": 1, "test_roots": ["tests"]},
            "gate": [{"name": "tests", "cmd": "true"}],
        }
        with tempfile.TemporaryDirectory() as directory:
            with (
                mock.patch("doctor.shutil.which", return_value=None) as which,
                mock.patch("doctor.codex_candidates", side_effect=AssertionError("agent auth called")),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                run_doctor(Path(directory), config, full=False)

        which.assert_not_called()

    def test_doctor_fails_closed_for_missing_unapproved_or_incompatible_charter(self):
        config = {
            "agents": {},
            "qa": {"agent": "mock-qa", "max_retries": 1, "test_roots": ["tests"]},
            "gate": [{"name": "tests", "cmd": "true"}],
        }
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            ProjectContract.detect(repo).write()

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = run_doctor(repo, config, full=False)
            self.assertEqual(result, 1)
            self.assertRegex(output.getvalue(), r"\[FAIL\].*Factory Charter.*not found")

            FactoryCharter.draft(repo, ProjectContract.load(repo)).write()
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = run_doctor(repo, config, full=False)
            self.assertEqual(result, 1)
            self.assertRegex(output.getvalue(), r"\[FAIL\].*Factory Charter.*not approved")

            FactoryCharter.load(repo).approve()
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = run_doctor(
                    repo, config, full=False, profile_name="autonomous-demo",
                )
            self.assertEqual(result, 1)
            self.assertRegex(
                output.getvalue(),
                r"\[FAIL\].*Factory Charter.*requires supervisor merge authority",
            )

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

    def test_start_over_clears_workshop_state_but_keeps_local_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "repo"
            repo.mkdir()
            git(repo, "init", "-q", "-b", "main")
            git(repo, "config", "user.name", "Factory Test")
            git(repo, "config", "user.email", "factory@example.test")
            (repo / "demo-app").mkdir()
            (repo / "demo-app/app.py").write_text("")
            (repo / "demo-app/requirements.txt").write_text("")
            (repo / "factory").mkdir()
            (repo / "factory/orchestrator.py").write_text("")
            git(repo, "add", ".")
            git(repo, "commit", "-qm", "chore: establish factory workshop baseline")
            (repo / "demo-app/finished.txt").write_text("rehearsal\n")
            git(repo, "add", ".")
            git(repo, "commit", "-qm", "feat: finish rehearsal")

            script = repo / "factory/setup_demo.sh"
            script.write_bytes((Path(__file__).parents[1] / "setup_demo.sh").read_bytes())
            script.chmod(0o755)
            stub = repo / ".factory/venv/bin"
            stub.mkdir(parents=True)
            (stub / "python").write_text("#!/bin/sh\nexit 0\n")
            (stub / "python").chmod(0o755)
            (repo / ".factory/plans/run").mkdir(parents=True)
            (repo / ".factory/plans/run/manifest.json").write_text("{}\n")
            (repo / ".factory/rehearsal/run").mkdir(parents=True)
            (repo / ".factory/rehearsal/run/tickets.json").write_text("[]\n")
            (repo / ".factory/control-center/evidence-run").mkdir(parents=True)
            (repo / ".factory/control-center/evidence-run/evidence-manifest.json").write_text("{}\n")
            (repo / ".factory/control-center/workshop-prd.md").write_text("# PRD\n")
            (repo / ".factory/control-center/factory-canvas.md").write_text("# Canvas\n")
            (repo / ".factory/control-center/operation.json").write_text("{}\n")
            (repo / ".factory/planning-state.json").write_text("{}\n")
            (repo / ".factory/local.toml").write_text("agent = 'claude'\n")

            proc = subprocess.run(
                ["sh", str(script), "--scenario", "recipe-rebrand", "--force", "--start-over"],
                cwd=repo, text=True, capture_output=True, timeout=120,
            )

            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertFalse((repo / ".factory/plans").exists())
            self.assertFalse((repo / ".factory/rehearsal").exists())
            self.assertFalse((repo / ".factory/planning-state.json").exists())
            self.assertFalse((repo / ".factory/control-center/workshop-prd.md").exists())
            self.assertFalse((repo / ".factory/control-center/factory-canvas.md").exists())
            self.assertTrue((repo / ".factory/control-center/operation.json").is_file())
            self.assertTrue((repo / ".factory/local.toml").is_file())
            state = json.loads((repo / ".factory/state.json").read_text())
            self.assertEqual(state["tickets"], [])

    def test_recipe_mobile_ticket_fails_verification_once_then_passes_with_receipts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            source = Path(__file__).parents[2]
            shutil.copytree(source / "factory", repo / "factory")
            shutil.copy2(source / "factory.project.toml", repo / "factory.project.toml")
            baseline_archive = root / "baseline.tar"
            subprocess.run([
                "git", "archive", "--format=tar", "factory-baseline",
                "demo-app", "-o", str(baseline_archive),
            ], cwd=source, check=True)
            subprocess.run([
                "tar", "-xf", str(baseline_archive), "-C", str(repo),
            ], check=True)
            for prerequisite in ("1", "2"):
                shutil.copytree(
                    source / "factory/scenarios/recipe-rebrand/steps" / prerequisite / "demo-app",
                    repo / "demo-app",
                    dirs_exist_ok=True,
                )
            ticket = {
                "number": 3,
                "title": "Build the mobile TableStory experience",
                "labels": ["agent-ready"],
                "mock_action": "recipe-mobile",
                "body": (
                    "## Spec\nBuild mobile browse, detail, and cookbook behavior.\n\n"
                    "## Acceptance criteria\n- TableStory renders\n- Recipe detail opens\n\n"
                    "factory-plan:retry-demo:T3\n\nagent: mock"
                ),
            }
            (repo / "factory/scenarios/recipe-rebrand/tickets.json").write_text(
                json.dumps([ticket], indent=2) + "\n"
            )
            (repo / ".gitignore").write_text(".factory/\n")
            install_approved_charter(repo)
            git(repo, "init", "-q", "-b", "main")
            git(repo, "config", "user.name", "Factory Test")
            git(repo, "config", "user.email", "factory@example.test")
            git(repo, "add", ".")
            git(repo, "commit", "-qm", "baseline")
            args = SimpleNamespace(
                repo=str(repo),
                qa_agent=None,
                no_qa=False,
                mock=True,
                project_number=None,
                review_qa_tests=False,
                scenario="recipe-rebrand",
                agent="mock",
                dry_run=False,
                max_parallel=1,
                once=True,
                profile="standard",
            )

            Factory(args).run_loop()

            state = json.loads((repo / ".factory/state.json").read_text())
            waiting = state["tickets"][0]
            self.assertEqual(waiting["status"], "In Review", waiting.get("failure"))
            self.assertEqual(waiting["attempt"], 2)
            self.assertEqual(waiting["qa_evidence"]["red"]["result"], "RED PROVED")
            self.assertEqual(waiting["qa_evidence"]["green"]["result"], "GREEN PROVED")
            self.assertEqual(
                waiting["qa_evidence"]["focused_test_command_sha256"],
                Factory._command_sha256(waiting["qa_evidence"]["focused_test_command"]),
            )
            self.assertTrue(any(item["note"].startswith("Retry 1") for item in waiting["history"]))
            receipts = [json.loads((repo / path).read_text()) for path in waiting["receipts"]]
            verification = [item for item in receipts if item["role"] == "verification"]
            self.assertEqual([item["claimed_result"] for item in verification], ["Verification failed", "Verification passed"])
            self.assertEqual(
                verification[0]["unresolved_risks"],
                ["Required verification did not pass; inspect gate results in factory state."],
            )
            self.assertEqual(verification[1]["unresolved_risks"], [])
            self.assertIn("RED PROVED", " ".join(verification[1]["verification"]))
            self.assertIn("GREEN PROVED", " ".join(verification[1]["verification"]))
            self.assertEqual(waiting["code_review"]["result"]["decision"], "APPROVE")
            self.assertTrue((repo / waiting["code_review"]["artifact"]).is_file())
            self.assertNotEqual(receipts[-1]["role"], "human_review")

            human_merge_ticket(repo, 3, mock=True, project_number=None, assume_yes=True)

            completed = json.loads((repo / ".factory/state.json").read_text())["tickets"][0]
            receipts = [json.loads((repo / path).read_text()) for path in completed["receipts"]]
            self.assertEqual(completed["status"], "Done", completed.get("failure"))
            self.assertEqual(receipts[-1]["role"], "human_review")
            self.assertFalse((repo / "demo-app/rehearsal-attempt.txt").exists())

    def test_code_review_rework_stops_at_human_merge_gate_then_exact_head_can_merge(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            source = Path(__file__).parents[2]
            shutil.copytree(source / "factory", repo / "factory")
            shutil.copy2(source / "factory.project.toml", repo / "factory.project.toml")
            baseline_archive = root / "baseline.tar"
            subprocess.run([
                "git", "archive", "--format=tar", "factory-baseline",
                "demo-app", "-o", str(baseline_archive),
            ], cwd=source, check=True)
            subprocess.run(["tar", "-xf", str(baseline_archive), "-C", str(repo)], check=True)
            ticket = {
                "number": 1,
                "title": "Add the recipe data model and API",
                "labels": ["agent-ready"],
                "mock_action": "recipe-api",
                "body": (
                    "## Spec\nAdd deterministic recipe data and lookup APIs.\n\n"
                    "## Acceptance criteria\n- Recipe IDs are unique.\n\n"
                    "factory-plan:review-loop:T1\n\nagent: mock"
                ),
            }
            (repo / "factory/scenarios/recipe-rebrand/tickets.json").write_text(
                json.dumps([ticket], indent=2) + "\n"
            )
            (repo / ".gitignore").write_text(".factory/\n__pycache__/\n*.pyc\n")
            install_approved_charter(repo)
            git(repo, "init", "-q", "-b", "main")
            git(repo, "config", "user.name", "Factory Test")
            git(repo, "config", "user.email", "factory@example.test")
            git(repo, "add", ".")
            git(repo, "commit", "-qm", "baseline")
            args = SimpleNamespace(
                repo=str(repo), qa_agent=None, no_qa=False, mock=True,
                project_number=None, review_qa_tests=False,
                scenario="recipe-rebrand", agent="mock", dry_run=False,
                max_parallel=1, once=True, profile="standard",
            )

            Factory(args).run_loop()

            state = json.loads((repo / ".factory/state.json").read_text())
            waiting = state["tickets"][0]
            self.assertEqual(waiting["status"], "In Review", waiting.get("failure"))
            self.assertEqual(waiting["attempt"], 2)
            self.assertTrue(any(item["note"].startswith("Retry 1") for item in waiting["history"]))
            receipts = [json.loads((repo / path).read_text()) for path in waiting["receipts"]]
            reviews = [item for item in receipts if item["role"] == "code_review"]
            self.assertEqual(
                [item["output_revisions"]["decision"] for item in reviews],
                ["REQUEST_CHANGES", "APPROVE"],
            )
            self.assertNotEqual(receipts[-1]["role"], "human_review")
            self.assertEqual(waiting["merge_authority"], "human")
            self.assertEqual(waiting["approved_head"], waiting["code_review"]["head"])

            human_merge_ticket(repo, 1, mock=True, project_number=None, assume_yes=True)

            completed = json.loads((repo / ".factory/state.json").read_text())["tickets"][0]
            receipts = [json.loads((repo / path).read_text()) for path in completed["receipts"]]
            self.assertEqual(completed["status"], "Done", completed.get("failure"))
            self.assertEqual(receipts[-1]["role"], "human_review")
            self.assertIn("Recipe IDs must be unique", (repo / "demo-app/recipe_api.py").read_text())

    def test_autonomous_demo_requires_opt_in_then_records_supervisor_merge(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            source = Path(__file__).parents[2]
            shutil.copytree(source / "factory", repo / "factory")
            shutil.copy2(source / "factory.project.toml", repo / "factory.project.toml")
            baseline_archive = root / "baseline.tar"
            subprocess.run([
                "git", "archive", "--format=tar", "factory-baseline",
                "demo-app", "-o", str(baseline_archive),
            ], cwd=source, check=True)
            subprocess.run(["tar", "-xf", str(baseline_archive), "-C", str(repo)], check=True)
            ticket = {
                "number": 1,
                "title": "Autonomous Demo recipe API slice",
                "labels": ["agent-ready"],
                "mock_action": "recipe-api",
                "body": (
                    "## Spec\nAdd the recipe API.\n\n"
                    "## Acceptance criteria\n- Recipe data is available.\n\n"
                    "factory-plan:autonomous-demo:T1\n\nagent: mock"
                ),
            }
            (repo / "factory/scenarios/recipe-rebrand/tickets.json").write_text(
                json.dumps([ticket], indent=2) + "\n"
            )
            (repo / ".gitignore").write_text(".factory/\n__pycache__/\n*.pyc\n")
            install_approved_charter(repo, merge_authority="supervisor")
            git(repo, "init", "-q", "-b", "main")
            git(repo, "config", "user.name", "Factory Test")
            git(repo, "config", "user.email", "factory@example.test")
            git(repo, "add", ".")
            git(repo, "commit", "-qm", "baseline")
            args = SimpleNamespace(
                repo=str(repo), qa_agent=None, no_qa=False, mock=True,
                project_number=None, review_qa_tests=False,
                scenario="recipe-rebrand", agent="mock", dry_run=False,
                max_parallel=1, once=True, profile="autonomous-demo",
                allow_autonomous_merge=False,
            )

            with self.assertRaisesRegex(ValueError, "explicit autonomous-merge opt-in"):
                Factory(args)

            args.allow_autonomous_merge = True
            Factory(args).run_loop()

            state = json.loads((repo / ".factory/state.json").read_text())
            completed = state["tickets"][0]
            receipts = [json.loads((repo / path).read_text()) for path in completed["receipts"]]
            self.assertEqual(completed["status"], "Done", completed.get("failure"))
            self.assertEqual(completed["merge_authority"], "supervisor")
            self.assertEqual(completed["merge_executed_by"], "supervisor")
            self.assertTrue(state["governance"]["explicit_autonomy"])
            self.assertEqual(receipts[-1]["role"], "supervisor_merge")

    def test_lean_and_assured_profiles_execute_complete_role_and_gate_sequences(self):
        expected_roles = {
            "lean": ["implementation", "verification", "human_review"],
            "assured": [
                "supervisor",
                "qa",
                "implementation",
                "cleanup",
                "architecture_conformance",
                "hardening",
                "verification",
                "critic",
                "negative_proof",
                "final_verifier",
                "code_review",
                "supervisor",
                "human_review",
            ],
        }
        for profile_name, roles in expected_roles.items():
            with self.subTest(profile=profile_name), tempfile.TemporaryDirectory() as directory:
                repo = Path(directory) / "repo"
                source = Path(__file__).parents[2]
                shutil.copytree(source / "factory", repo / "factory")
                shutil.copy2(source / "factory.project.toml", repo / "factory.project.toml")
                baseline_archive = Path(directory) / "baseline.tar"
                subprocess.run([
                    "git", "archive", "--format=tar", "factory-baseline",
                    "demo-app", "-o", str(baseline_archive),
                ], cwd=source, check=True)
                subprocess.run([
                    "tar", "-xf", str(baseline_archive), "-C", str(repo),
                ], check=True)
                ticket = {
                    "number": 1,
                    "title": f"{profile_name.title()} recipe API slice",
                    "labels": ["agent-ready"],
                    "mock_action": "recipe-api",
                    "body": (
                        "## Spec\nAdd the recipe API.\n\n"
                        "## Acceptance criteria\n- Recipe data is available.\n\n"
                        f"factory-plan:{profile_name}-profile:T1\n\nagent: mock"
                    ),
                }
                (repo / "factory/scenarios/recipe-rebrand/tickets.json").write_text(
                    json.dumps([ticket], indent=2) + "\n"
                )
                (repo / ".gitignore").write_text(".factory/\n__pycache__/\n*.pyc\n")
                install_approved_charter(repo)
                git(repo, "init", "-q", "-b", "main")
                git(repo, "config", "user.name", "Factory Test")
                git(repo, "config", "user.email", "factory@example.test")
                git(repo, "add", ".")
                git(repo, "commit", "-qm", "baseline")
                args = SimpleNamespace(
                    repo=str(repo),
                    qa_agent=None,
                    no_qa=False,
                    mock=True,
                    project_number=None,
                    review_qa_tests=False,
                    scenario="recipe-rebrand",
                    agent="mock",
                    dry_run=False,
                    max_parallel=1,
                    once=True,
                    profile=profile_name,
                )

                Factory(args).run_loop()

                waiting = json.loads((repo / ".factory/state.json").read_text())["tickets"][0]
                self.assertEqual(waiting["status"], "In Review", waiting.get("failure"))

                human_merge_ticket(repo, 1, mock=True, project_number=None, assume_yes=True)

                completed = json.loads((repo / ".factory/state.json").read_text())["tickets"][0]
                receipts = [json.loads((repo / path).read_text()) for path in completed["receipts"]]
                self.assertEqual(completed["status"], "Done", completed.get("failure"))
                self.assertEqual([receipt["role"] for receipt in receipts], roles)
                self.assertTrue(completed["gate_results"])
                self.assertTrue(all(
                    gate["exit_code"] == 0
                    for gate in completed["gate_results"]
                    if gate["required"]
                ))
                self.assertEqual(bool(completed["qa_tests"]), profile_name == "assured")


if __name__ == "__main__":
    unittest.main()
