import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1]))

from run_lights_off import agent_command


class LightsOffLauncherTests(unittest.TestCase):
    @patch("run_lights_off.resolve_codex_cli", return_value="/current/codex")
    def test_codex_uses_the_authenticated_current_cli(self, resolve):
        command = agent_command("codex", "control prompt")

        resolve.assert_called_once_with()
        self.assertEqual(command[:5], [
            "/current/codex", "exec", "--sandbox", "workspace-write", "--ephemeral",
        ])
        self.assertEqual(command[-1], "control prompt")

    @patch("run_lights_off.shutil.which", return_value="/bin/claude")
    def test_claude_uses_noninteractive_edit_mode(self, which):
        self.assertEqual(agent_command("claude", "control prompt"), [
            "/bin/claude", "-p", "control prompt", "--permission-mode", "acceptEdits",
        ])
        which.assert_called_once_with("claude")


if __name__ == "__main__":
    unittest.main()
