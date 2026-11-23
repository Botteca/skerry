"""Gemini CLI and GitHub Copilot CLI: event mapping, hook flow through Flask, connect/disconnect, silent CLI."""
import json
import os
import socket
import subprocess
import sys
import threading
import time

import pytest

from skerry import agents, integrations
from skerry.api import Api
from skerry.server import create_app
from skerry.settings import Settings
from skerry.store import Store

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CWD = "C:/rep/ExampleApp"


class FakeApp:
    def __init__(self, store, settings):
        self.store, self.settings = store, settings


@pytest.fixture
def env(tmp_path):
    settings = Settings(str(tmp_path / "settings.json"))
    settings.set("focus_terminal_after_decision", False)
    settings.set("permission_wait", 5)
    store = Store(settings)
    app = create_app(store, settings)
    return {"settings": settings, "store": store, "app": app, "client": app.test_client(),
            "api": Api(FakeApp(store, settings))}


def post(env, agent, event, payload):
    r = env["client"].post(f"/hook/{event}?agent={agent}", json=payload)
    assert r.status_code == 200
    return r.get_json()


def session(env, agent, sid="s1"):
    return next(s for s in env["store"].snapshot()["sessions"] if s["sid"] == f"{agent}:{sid}")


# ---------------------------------------------------------------- mapping

def test_copilot_fields_are_mapped():
    ev, p = agents.normalize("copilot", "preToolUse", {"sessionId": "s1", "cwd": CWD, "toolName": "bash",
                                                       "toolArgs": json.dumps({"command": "npm test"})})
    assert ev == "PreToolUse"
    assert (p["session_id"], p["tool_name"], p["tool_input"]) == ("s1", "bash", {"command": "npm test"})
    assert agents.normalize("copilot", "sessionStart", {"source": "new"})[1]["source"] == "startup"
    assert agents.normalize("copilot", "errorOccurred", {"error": {"message": "x"}, "recoverable": True})[0] is None
    ev, p = agents.normalize("copilot", "errorOccurred", {"error": {"message": "boom"}, "recoverable": False})
    assert (ev, p["error"]) == ("StopFailure", "boom")
    assert agents.normalize("copilot", "notification", {})[0] is None


def test_gemini_events_are_mapped():
    assert agents.normalize("gemini", "BeforeTool", {"tool_name": "run_shell_command"})[0] == "PreToolUse"
    assert agents.normalize("gemini", "AfterAgent", {"prompt_response": "Done."})[1]["last_assistant_message"] == "Done."
    ev, p = agents.normalize("gemini", "Notification", {"notification_type": "ToolPermission", "message": "?"})
    assert (ev, p["notification_type"]) == ("Notification", "permission_prompt")
    assert agents.normalize("gemini", "Notification", {"notification_type": "Other"})[0] is None
    assert agents.normalize("gemini", "BeforeModel", {})[0] is None


def test_copilot_reply_format():
    allow = {"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": {"behavior": "allow"}}}
    deny = {"hookSpecificOutput": {"decision": {"behavior": "deny", "message": "no"}}}
    assert agents.reply("copilot", allow) == {"behavior": "allow"}
    assert agents.reply("copilot", deny) == {"behavior": "deny", "message": "no"}
    assert agents.reply("copilot", {}) == {}
    assert agents.reply("claude", allow) is allow


# ---------------------------------------------------------------- flow

def test_copilot_permission_is_answered_from_the_island(env):
    result = {}

    def run():
        r = env["app"].test_client().post("/hook/permissionRequest?agent=copilot",
                                          json={"sessionId": "s1", "cwd": CWD, "toolName": "bash",
                                                "toolInput": {"command": "npm test"}})
        result["body"] = r.get_json()

    t = threading.Thread(target=run, daemon=True)
    t.start()
    deadline = time.time() + 5
    while not env["store"].snapshot()["pending"] and time.time() < deadline:
        time.sleep(0.01)
    (p,) = env["store"].snapshot()["pending"]
    assert (p["agent"], p["text"], p["can_always"]) == ("copilot", "npm test", False)
    env["api"].decide(p["id"], "allow")
    t.join(5)
    assert result["body"] == {"behavior": "allow"}


def test_gemini_shows_activity_and_a_terminal_permission(env):
    post(env, "gemini", "BeforeTool", {"hook_event_name": "BeforeTool", "session_id": "s1", "cwd": CWD,
                                       "tool_name": "write_file", "tool_input": {"file_path": "src/app.py"}})
    s = session(env, "gemini")
    assert (s["project"], s["status"], s["action"]) == ("ExampleApp", "working", "Writing app.py")
    post(env, "gemini", "Notification", {"hook_event_name": "Notification", "session_id": "s1",
                                         "notification_type": "ToolPermission", "message": "Allow?"})
    s = session(env, "gemini")
    assert s["status"] == "waiting" and "terminal" in s["action"]
    assert env["store"].snapshot()["pending"] == []        # nothing to approve in Skerry
    post(env, "gemini", "AfterAgent", {"hook_event_name": "AfterAgent", "session_id": "s1"})
    assert session(env, "gemini")["status"] == "done"


def test_module_off_ignores_the_agent(env):
    env["settings"].set("modules.copilot", False)
    assert post(env, "copilot", "preToolUse", {"sessionId": "s1", "toolName": "bash"}) == {}
    assert env["store"].snapshot()["sessions"] == []


# ---------------------------------------------------------------- connect / disconnect

class FakeSettings(dict):
    def get(self, key, default=None):
        return super().get(key, default)

    def set(self, key, value):
        self[key] = value


def test_gemini_connect_keeps_other_settings(tmp_path, monkeypatch):
    path = tmp_path / ".gemini" / "settings.json"
    monkeypatch.setattr(integrations, "GEMINI_SETTINGS", str(path))
    path.parent.mkdir()
    other = {"matcher": "write_file", "hooks": [{"type": "command", "command": "lint.sh"}]}
    path.write_text(json.dumps({"theme": "Dark", "hooks": {"BeforeTool": [other]}}), encoding="utf-8")

    integrations.gemini_install(FakeSettings())
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["theme"] == "Dark" and other in data["hooks"]["BeforeTool"]
    ours = [h for groups in data["hooks"].values() for g in groups for h in g["hooks"] if h["command"] != "lint.sh"]
    assert len(ours) == len(integrations.GEMINI_EVENTS)
    assert all("hook gemini" in h["command"] and h["timeout"] == 5000 for h in ours)
    assert integrations.gemini_status()["installed"]

    integrations.gemini_install(FakeSettings())                       # reconnecting does not duplicate
    data = json.loads(path.read_text(encoding="utf-8"))
    assert len(data["hooks"]["BeforeTool"]) == 2

    integrations.gemini_uninstall(FakeSettings())
    assert json.loads(path.read_text(encoding="utf-8")) == {"theme": "Dark", "hooks": {"BeforeTool": [other]}}


def test_copilot_connect_writes_its_own_file(tmp_path, monkeypatch):
    path = tmp_path / ".copilot" / "hooks" / "skerry.json"
    monkeypatch.setattr(integrations, "COPILOT_HOOKS", str(path))
    integrations.copilot_install(FakeSettings(permission_wait=300))
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["version"] == 1 and set(data["hooks"]) == set(integrations.COPILOT_EVENTS)
    (perm,) = data["hooks"]["permissionRequest"]
    assert perm["timeoutSec"] == 330 and perm["bash"].endswith("hook copilot permissionRequest")
    assert perm["powershell"] == "& " + perm["bash"]                  # a quoted path needs & in PowerShell
    assert integrations.copilot_status()["installed"]
    integrations.copilot_uninstall(FakeSettings())
    assert not path.exists() and not integrations.copilot_status()["installed"]


# ---------------------------------------------------------------- CLI with Skerry not running

def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.mark.parametrize("args, stdin, stdout", [
    (["copilot", "preToolUse"], {"sessionId": "x", "toolName": "bash", "toolArgs": "{}"}, ""),
    (["copilot", "permissionRequest"], {"sessionId": "x", "toolName": "bash"}, ""),
    (["gemini"], {"hook_event_name": "BeforeTool", "session_id": "x"}, "{}\n"),
])
def test_cli_never_blocks_when_skerry_is_off(tmp_path, args, stdin, stdout):
    appdata = tmp_path / "appdata"
    (appdata / "Skerry").mkdir(parents=True)
    (appdata / "Skerry" / "settings.json").write_text(json.dumps({"port": free_port()}), encoding="utf-8")
    env = {**os.environ, "APPDATA": str(appdata), "LOCALAPPDATA": str(tmp_path / "local")}
    r = subprocess.run([sys.executable, os.path.join(ROOT, "cli.py"), "hook", *args], input=json.dumps(stdin),
                       capture_output=True, text=True, env=env, timeout=60)
    assert (r.returncode, r.stdout, r.stderr) == (0, stdout, "")


# ---------------------------------------------------------------- OpenCode (plugin)

def post_new(env, agent, event, payload):
    """Like post(), with a client of its own (for requests made from another thread)."""
    return env["app"].test_client().post(f"/hook/{event}?agent={agent}", json=payload).get_json()

def test_opencode_tools_and_permission_are_mapped():
    ev, p = agents.normalize("opencode", "PreToolUse", {"session_id": "s1", "cwd": CWD, "tool_name": "edit",
                                                       "tool_input": {"filePath": "C:/rep/ExampleApp/a.py"}})
    assert (ev, p["tool_name"], p["tool_input"]["file_path"]) == ("PreToolUse", "Edit", "C:/rep/ExampleApp/a.py")
    ev, p = agents.normalize("opencode", "PermissionRequest", {"session_id": "s1", "cwd": CWD, "tool_name": "bash",
                                                              "tool_input": {"patterns": ["npm test"]}, "can_always": True})
    assert (ev, p["tool_name"], p["tool_input"]["command"]) == ("PermissionRequest", "Bash", "npm test")
    assert p["permission_suggestions"]
    assert agents.normalize("opencode", "PermissionResolved", {"session_id": "s1"})[0] == "PermissionResolved"


def test_opencode_reply_format():
    allow = {"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": {"behavior": "allow"}}}
    always = {"hookSpecificOutput": {"decision": {"behavior": "allow", "updatedPermissions": [{"type": "opencode"}]}}}
    deny = {"hookSpecificOutput": {"decision": {"behavior": "deny", "message": "no"}}}
    assert agents.reply("opencode", allow) == {"decision": "once"}
    assert agents.reply("opencode", always) == {"decision": "always"}
    assert agents.reply("opencode", deny) == {"decision": "reject"}
    assert agents.reply("opencode", {}) == {}


def test_opencode_permission_is_answered_from_the_island(env):
    res = {}

    def ask():
        res["out"] = post_new(env, "opencode", "PermissionRequest",
                          {"session_id": "s1", "cwd": CWD, "tool_name": "bash", "tool_input": {"patterns": ["npm test"]},
                           "can_always": True})
    th = threading.Thread(target=ask)
    th.start()
    deadline = time.time() + 10
    while not (pend := env["store"].snapshot()["pending"]) and time.time() < deadline:
        time.sleep(0.02)
    assert pend[0]["agent"] == "opencode" and pend[0]["can_always"]
    env["api"].decide(pend[0]["id"], "always")
    th.join(10)
    assert res["out"] == {"decision": "always"}


def test_opencode_answer_in_the_terminal_withdraws_the_request(env):
    res = {}
    th = threading.Thread(target=lambda: res.update(out=post_new(env, "opencode", "PermissionRequest", {
        "session_id": "s1", "cwd": CWD, "tool_name": "bash", "tool_input": {"patterns": ["ls"]}})))
    th.start()
    deadline = time.time() + 10
    while not env["store"].snapshot()["pending"] and time.time() < deadline:
        time.sleep(0.02)
    assert env["store"].snapshot()["pending"], "the request never reached the store"
    t0 = time.time()
    post(env, "opencode", "PermissionResolved", {"session_id": "s1", "cwd": CWD})
    th.join(10)
    assert res.get("out") == {} and env["store"].snapshot()["pending"] == []
    assert time.time() - t0 < 4          # withdrawn at once, not after permission_wait (5 s)


def test_opencode_connect_writes_its_plugin(tmp_path, monkeypatch):
    path = tmp_path / ".config" / "opencode" / "plugins" / "skerry.js"
    monkeypatch.setattr(integrations, "OPENCODE_PLUGIN", str(path))
    integrations.opencode_install(FakeSettings(permission_wait=300, port=47800))
    src = path.read_text(encoding="utf-8")
    assert src.startswith(integrations.OPENCODE_MARKER)
    assert "http://127.0.0.1:47800/hook/" in src and "(300 + 20) * 1000" in src and "__" not in src.split("\n", 1)[1][:200]
    assert integrations.opencode_status()["installed"]
    integrations.opencode_uninstall(FakeSettings())
    assert not path.exists()


def test_opencode_disconnect_keeps_a_users_own_file(tmp_path, monkeypatch):
    path = tmp_path / "skerry.js"
    path.write_text("export const Mine = async () => ({})\n", encoding="utf-8")
    monkeypatch.setattr(integrations, "OPENCODE_PLUGIN", str(path))
    integrations.opencode_uninstall(FakeSettings())
    assert path.exists()
