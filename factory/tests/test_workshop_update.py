import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


UPDATER = Path(__file__).parents[1] / "workshop_update.py"


class WorkshopUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.source = root / "source"
        self.target = root / "target"
        for repo, version, content in (
            (self.source, "workshop-v1.1.0", "new factory\n"),
            (self.target, "workshop-v1.0.0", "old factory\n"),
        ):
            (repo / "factory").mkdir(parents=True)
            (repo / "workshop-guide").mkdir()
            (repo / "factory/factory_contracts.py").write_text(
                f'WORKSHOP_VERSION = "{version}"\n'
            )
            (repo / "factory/tool.txt").write_text(content)
            (repo / "workshop-guide/guide.txt").write_text(f"guide {version}\n")
            (repo / "setup_demo.sh").write_text("#!/bin/sh\n")

    def tearDown(self):
        self.temp.cleanup()

    def run_update(self, *arguments):
        return subprocess.run(
            [sys.executable, str(UPDATER), "--target", str(self.target), *arguments],
            text=True,
            capture_output=True,
        )

    def test_preview_then_apply_updates_only_recorded_clean_files(self):
        recorded = self.run_update("--record-current")
        self.assertEqual(recorded.returncode, 0, recorded.stderr)

        preview = self.run_update("--source", str(self.source))
        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertIn("UPDATE factory/tool.txt", preview.stdout)
        self.assertIn("Preview only", preview.stdout)
        self.assertEqual((self.target / "factory/tool.txt").read_text(), "old factory\n")

        applied = self.run_update("--source", str(self.source), "--apply")
        self.assertEqual(applied.returncode, 0, applied.stderr)
        self.assertEqual((self.target / "factory/tool.txt").read_text(), "new factory\n")
        manifest = json.loads((self.target / ".factory/workshop-install.json").read_text())
        self.assertEqual(manifest["version"], "workshop-v1.1.0")
        self.assertNotIn("demo-app", "\n".join(manifest["files"]))

    def test_local_drift_fails_closed_without_overwriting(self):
        self.assertEqual(self.run_update("--record-current").returncode, 0)
        changed = self.target / "factory/tool.txt"
        changed.write_text("attendee customization\n")

        result = self.run_update("--source", str(self.source), "--apply")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DRIFT factory/tool.txt", result.stderr)
        self.assertIn("Resolve drift", result.stderr)
        self.assertEqual(changed.read_text(), "attendee customization\n")

    def test_update_requires_an_installed_baseline(self):
        result = self.run_update("--source", str(self.source), "--apply")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("No workshop install manifest", result.stderr)
        self.assertFalse((self.target / ".factory/workshop-install.json").exists())

    def test_removed_managed_file_is_reported_before_apply(self):
        obsolete = self.target / "factory/obsolete.txt"
        obsolete.write_text("old\n")
        self.assertEqual(self.run_update("--record-current").returncode, 0)

        preview = self.run_update("--source", str(self.source))
        self.assertEqual(preview.returncode, 0)
        self.assertIn("REMOVE factory/obsolete.txt", preview.stdout)
        self.assertTrue(obsolete.exists())

        applied = self.run_update("--source", str(self.source), "--apply")
        self.assertEqual(applied.returncode, 0, applied.stderr)
        self.assertFalse(obsolete.exists())


if __name__ == "__main__":
    unittest.main()
