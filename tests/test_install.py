import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from corvox import install

SETTINGS = """{
  "theme": "dark",
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "notify-send done"
          }
        ]
      }
    ]
  }
}"""
AGENTS_MD = "- Be direct.\n- No compliments.\n"


class InstallTests(unittest.TestCase):
    """Install and uninstall against throwaway agent config folders."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.claude, self.codex = root / "claude", root / "codex"
        self.claude.mkdir()
        self.codex.mkdir()
        (self.claude / "settings.json").write_text(SETTINGS, encoding="utf-8")
        (self.codex / "AGENTS.md").write_text(AGENTS_MD, encoding="utf-8")
        self.env = mock.patch.dict(os.environ, {
            "CLAUDE_CONFIG_DIR": str(self.claude), "CODEX_HOME": str(self.codex),
            "CORVOX_HOME": str(root / "home")})
        self.env.start()
        self.exe = mock.patch.object(install, "corvox_exe", return_value="D:/Tools/corvox/venv/Scripts/corvox.exe")
        self.exe.start()

    def tearDown(self):
        self.exe.stop()
        self.env.stop()
        self.tmp.cleanup()

    def run_cli(self, remove=False):
        with mock.patch("builtins.print"):
            return install.run(["claude", "codex"], remove=remove, dry_run=False, yes=True)

    def test_install_adds_hooks_and_keeps_existing_ones(self):
        self.run_cli()
        settings = json.loads((self.claude / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(settings["theme"], "dark")
        stop_commands = [h["command"] for g in settings["hooks"]["Stop"] for h in g["hooks"]]
        self.assertEqual(stop_commands, ["notify-send done", "D:/Tools/corvox/venv/Scripts/corvox.exe hook claude stop"])
        codex_hooks = json.loads((self.codex / "hooks.json").read_text(encoding="utf-8"))
        self.assertEqual(codex_hooks["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"],
                         "D:/Tools/corvox/venv/Scripts/corvox.exe hook codex prompt")
        agents_md = (self.codex / "AGENTS.md").read_text(encoding="utf-8")
        self.assertTrue(agents_md.startswith(AGENTS_MD))
        self.assertIn(install.BLOCK_START, agents_md)
        self.assertTrue((self.claude / "commands" / "corvox-last.md").exists())

    def test_reinstall_changes_nothing(self):
        self.run_cli()
        self.assertEqual(install.plan(["claude", "codex"]), [])

    def test_uninstall_restores_original_files_exactly(self):
        self.run_cli()
        self.run_cli(remove=True)
        self.assertEqual((self.claude / "settings.json").read_text(encoding="utf-8"), SETTINGS)
        self.assertEqual((self.codex / "AGENTS.md").read_text(encoding="utf-8"), AGENTS_MD)
        self.assertFalse((self.codex / "hooks.json").exists())
        self.assertFalse((self.claude / "CLAUDE.md").exists())
        self.assertFalse((self.claude / "commands").exists())

    def test_backups_written_before_changes(self):
        self.run_cli()
        backups = list((Path(os.environ["CORVOX_HOME"]) / "backups").glob("*/*"))
        self.assertEqual(sorted(p.name for p in backups), ["claude-settings.json", "codex-AGENTS.md"])

    def test_foreign_command_file_is_left_alone(self):
        (self.claude / "commands").mkdir()
        (self.claude / "commands" / "corvox-last.md").write_text("mine", encoding="utf-8")
        self.run_cli()
        self.run_cli(remove=True)
        self.assertEqual((self.claude / "commands" / "corvox-last.md").read_text(encoding="utf-8"), "mine")

    def test_uninstall_without_install_creates_nothing(self):
        self.assertEqual([c.path.name for c in install.plan(["claude", "codex"], remove=True)], [])

    def test_paths_with_spaces(self):
        claude = install._handler("C:/Program Files/corvox.exe", "claude", "stop", exec_form=True)
        self.assertEqual(claude["args"], ["hook", "claude", "stop"])
        codex = install._handler("C:/Program Files/corvox.exe", "codex", "stop", exec_form=False)
        self.assertEqual(codex["command"], '"C:/Program Files/corvox.exe" hook codex stop')
        self.assertTrue(install._is_ours(claude) and install._is_ours(codex))


if __name__ == "__main__":
    unittest.main()
