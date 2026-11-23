"""Claude Code hooks: command hooks through skerry-cli (silent when Skerry is off), never "http" hooks."""
import json
import os
import socket
import subprocess
import sys

import pytest

from skerry import integrations

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class FakeSettings(dict):
    def get(self, key, default=None):
        return super().get(key, default)

    def set(self, key, value):
        self[key] = value


@pytest.fixture
def claude_settings(tmp_path, monkeypatch):
    path = tmp_path / ".claude" / "settings.json"
    monkeypatch.setattr(integrations, "CLAUDE_SETTINGS", str(path))
    return path


def test_install_writes_only_command_hooks(claude_settings):
    old = {"hooks": {"Stop": [{"hooks": [{"type": "http", "url": "http://127.0.0.1:47800/hook/Stop?agent=claude"}]},
                              {"hooks": [{"type": "command", "command": "other-tool notify"}]}]}}
    claude_settings.parent.mkdir(parents=True)
    claude_settings.write_text(json.dumps(old), encoding="utf-8")
    st = FakeSettings(port=47800, permission_wait=300)
    integrations.claude_install(st)
    data = json.loads(claude_settings.read_text(encoding="utf-8"))

    ours = [(ev, h) for ev, groups in data["hooks"].items() for g in groups for h in g["hooks"]
            if h.get("command") != "other-tool notify"]
    assert {ev for ev, _ in ours} == set(integrations.CLAUDE_EVENTS)
    assert all(h["type"] == "command" and "hook claude" in h["command"] for _, h in ours)
    assert "http" not in json.dumps(data["hooks"])                          # the old http hook is gone
    for ev, h in ours:
        if ev == "PermissionRequest":
            assert "async" not in h and h["timeout"] == 330                  # waits for the decision
        else:
            assert h["async"] is True                                      # no latency for the agent
    assert {"type": "command", "command": "other-tool notify"} in [h for g in data["hooks"]["Stop"] for h in g["hooks"]]
    assert st["hooks_version"] == integrations.HOOKS_VERSION >= 4
    assert integrations.claude_status()["installed"]

    integrations.claude_uninstall(st)
    data = json.loads(claude_settings.read_text(encoding="utf-8"))
    assert data["hooks"] == {"Stop": [{"hooks": [{"type": "command", "command": "other-tool notify"}]}]}


def test_cli_is_silent_when_skerry_is_not_running(tmp_path):
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()                                                              # nothing listens on this port
    appdata = tmp_path / "appdata"
    (appdata / "Skerry").mkdir(parents=True)
    (appdata / "Skerry" / "settings.json").write_text(json.dumps({"port": port}), encoding="utf-8")
    env = {**os.environ, "APPDATA": str(appdata), "LOCALAPPDATA": str(tmp_path / "local")}
    for event in ("Stop", "PreToolUse", "PermissionRequest"):
        payload = json.dumps({"hook_event_name": event, "session_id": "x", "tool_name": "Bash"})
        r = subprocess.run([sys.executable, os.path.join(ROOT, "cli.py"), "hook", "claude"], input=payload,
                           capture_output=True, text=True, env=env, timeout=60)
        assert (r.returncode, r.stdout, r.stderr) == (0, "", ""), event
