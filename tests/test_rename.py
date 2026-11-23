"""Checks for the rename: one-time data migration and clean replacement of pre-rename agent hooks.

Run:  python -m unittest discover -s tests
"""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from skerry import integrations, paths


class FakeSettings:
    def __init__(self, **values):
        self.values = {"port": 47800, "permission_wait": 300, **values}

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value


class MigrationTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.env = mock.patch.dict(os.environ, {"APPDATA": self.root, "LOCALAPPDATA": self.root})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.root, ignore_errors=True)

    def _legacy(self, name, settings):
        d = os.path.join(self.root, name)
        os.makedirs(os.path.join(d, "logs"))
        with open(os.path.join(d, "settings.json"), "w", encoding="utf-8") as f:
            json.dump(settings, f)
        with open(os.path.join(d, "logs", "old.log"), "w") as f:
            f.write("x")
        return d

    def _settings(self):
        with open(paths.settings_file(), encoding="utf-8") as f:
            return json.load(f)

    @mock.patch.object(paths, "LEGACY_NAMES", ("Island", "Older Island"))  # second name is invented
    def test_copies_newest_legacy_folder_once(self):
        for name, theme in zip(paths.LEGACY_NAMES, ("light", "dark")):
            self._legacy(name, {"theme": theme, "update_url": "https://example.invalid/old"})
        self.assertEqual(self._settings(), {"theme": "light"})  # newest legacy wins, old update URL dropped
        self.assertTrue(os.path.exists(os.path.join(paths.log_dir(), "old.log")))
        self.assertTrue(os.path.isdir(os.path.join(self.root, paths.LEGACY_NAMES[0])))  # copied, not moved

        with open(paths.settings_file(), "w", encoding="utf-8") as f:
            json.dump({"theme": "mine"}, f)
        self.assertEqual(self._settings(), {"theme": "mine"})  # never migrates again

    def test_no_legacy_folder(self):
        self.assertTrue(os.path.isdir(paths.config_dir()))
        self.assertFalse(os.path.exists(paths.settings_file()))


class LegacyHooksTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.claude = os.path.join(self.root, ".claude", "settings.json")
        self.codex = os.path.join(self.root, ".codex", "hooks.json")
        self.patches = [mock.patch.object(integrations, "CLAUDE_SETTINGS", self.claude),
                        mock.patch.object(integrations, "CODEX_DIR", os.path.dirname(self.codex)),
                        mock.patch.object(integrations, "CODEX_HOOKS", self.codex),
                        mock.patch.dict(os.environ, {"LOCALAPPDATA": self.root})]
        for p in self.patches:
            p.start()
        old = '"C:/Users/someone/AppData/Local/Programs/Island/island-cli.exe"'
        other = {"hooks": [{"type": "command", "command": "other-tool notify"}]}
        self._write(self.claude, {
            "hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": f"{old} hook claude"}]}, other],
                      "Stop": [{"hooks": [{"type": "http", "url": "http://127.0.0.1:47800/hook/Stop?agent=claude"}]}]},
            "statusLine": {"type": "command", "command": f"{old} statusline"}})
        self._write(self.codex, {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": f"{old} hook codex"}]}]}})

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        shutil.rmtree(self.root, ignore_errors=True)

    @staticmethod
    def _write(path, data):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)

    @staticmethod
    def _read(path):
        with open(path, encoding="utf-8") as f:
            return f.read()

    def test_install_replaces_legacy_hooks(self):
        st = FakeSettings()
        self.assertTrue(integrations.claude_status()["installed"])  # legacy hooks count as ours
        integrations.claude_install(st)
        integrations.codex_install(st)
        for path in (self.claude, self.codex):
            text = self._read(path)
            self.assertNotIn("island-cli", text)
        data = json.loads(self._read(self.claude))
        self.assertIn("other-tool notify", self._read(self.claude))  # foreign hooks untouched
        self.assertEqual(len(data["hooks"]["Stop"]), 1)  # no duplicate http hook
        self.assertIn("statusline", data["statusLine"]["command"])
        self.assertIsNone(st.get("chained_statusline"))  # old status line not chained to itself

    def test_uninstall_removes_legacy_hooks(self):
        st = FakeSettings()
        integrations.claude_uninstall(st)
        integrations.codex_uninstall(st)
        self.assertNotIn("island-cli", self._read(self.claude) + self._read(self.codex))
        self.assertIn("other-tool notify", self._read(self.claude))


if __name__ == "__main__":
    unittest.main()
