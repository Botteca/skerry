"""Hook -> Store flow through the real Flask app (test client, no sockets).

A PermissionRequest blocks its HTTP request until the UI decides through js_api (Api.decide),
the wait expires, or the session moves on (PostToolUse, Stop, UserPromptSubmit, SessionEnd).
"""
import threading
import time

import pytest

from skerry.api import Api
from skerry.server import create_app
from skerry.settings import Settings
from skerry.store import Store

SID = "s-123"
BASH = {"session_id": SID, "cwd": "C:/rep/ExampleApp", "tool_name": "Bash",
        "tool_input": {"command": "npm test"}}


class FakeApp:
    """The bits of SkerryApp that Api.decide uses."""

    def __init__(self, store, settings):
        self.store, self.settings = store, settings


@pytest.fixture
def env(tmp_path):
    settings = Settings(str(tmp_path / "settings.json"))
    settings.set("focus_terminal_after_decision", False)
    settings.set("permission_wait", 5)
    events = []
    store = Store(settings, on_event=events.append)
    app = create_app(store, settings)
    return {"settings": settings, "store": store, "app": app, "client": app.test_client(),
            "api": Api(FakeApp(store, settings)), "events": events}


def post(env, event, payload, agent="claude"):
    r = env["client"].post(f"/hook/{event}?agent={agent}", json={"hook_event_name": event, **payload})
    assert r.status_code == 200
    return r.get_json()


def start_permission(env, payload=BASH, agent="claude"):
    """Send a PermissionRequest in a background thread; return (thread, result holder)."""
    result = {}

    def run():
        client = env["app"].test_client()  # one client per thread
        r = client.post(f"/hook/PermissionRequest?agent={agent}",
                        json={"hook_event_name": "PermissionRequest", **payload})
        result["status"], result["body"] = r.status_code, r.get_json()

    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t, result


def wait_pending(store, count=1, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        pending = store.snapshot()["pending"]
        if len(pending) >= count:
            return pending
        time.sleep(0.01)
    raise AssertionError("permission request never reached the store")


def finish(thread, result):
    thread.join(5)
    assert not thread.is_alive(), "the hook request is still blocked"
    assert result["status"] == 200
    return result["body"]


def session(store, agent="claude"):
    return next(s for s in store.snapshot()["sessions"] if s["sid"] == f"{agent}:{SID}")


def test_activity_events_update_the_session(env):
    post(env, "SessionStart", {"session_id": SID, "cwd": "C:/rep/ExampleApp", "source": "startup"})
    post(env, "PreToolUse", BASH)
    s = session(env["store"])
    assert (s["project"], s["status"], s["action"]) == ("ExampleApp", "working", "npm test")

    post(env, "Stop", {"session_id": SID, "last_assistant_message": "All tests pass."})
    s = session(env["store"])
    assert (s["status"], s["done_msg"]) == ("done", "All tests pass.")
    assert "done" in env["events"]

    post(env, "SessionEnd", {"session_id": SID})
    assert env["store"].snapshot()["sessions"] == []


def test_permission_allowed_from_ui(env):
    t, result = start_permission(env)
    (p,) = wait_pending(env["store"])
    assert (p["agent"], p["tool"], p["project"], p["can_always"]) == ("claude", "Bash", "ExampleApp", False)
    assert "event" not in p and "_suggestions" not in p  # internals never reach the UI
    assert session(env["store"])["status"] == "permission"
    assert "permission" in env["events"]

    assert env["api"].decide(p["id"], "allow") is True
    assert finish(t, result) == {"hookSpecificOutput": {"hookEventName": "PermissionRequest",
                                                        "decision": {"behavior": "allow"}}}
    assert env["store"].snapshot()["pending"] == []
    assert session(env["store"])["status"] == "working"
    assert env["api"].decide(p["id"], "deny") is False  # already resolved


def test_permission_denied(env):
    t, result = start_permission(env)
    (p,) = wait_pending(env["store"])
    env["api"].decide(p["id"], "deny")
    decision = finish(t, result)["hookSpecificOutput"]["decision"]
    assert decision["behavior"] == "deny"
    assert decision["message"]


def test_permission_always_returns_the_suggested_rules(env):
    suggestions = [{"type": "addRules", "rules": [{"toolName": "Bash", "ruleContent": "npm test"}],
                    "behavior": "allow", "destination": "localSettings"}]
    t, result = start_permission(env, {**BASH, "permission_suggestions": suggestions})
    (p,) = wait_pending(env["store"])
    assert p["can_always"] is True
    env["api"].decide(p["id"], "always")
    assert finish(t, result)["hookSpecificOutput"]["decision"] == {"behavior": "allow",
                                                                  "updatedPermissions": suggestions}


def test_terminal_hands_the_decision_back(env):
    t, result = start_permission(env)
    (p,) = wait_pending(env["store"])
    env["api"].decide(p["id"], "terminal")
    assert finish(t, result) == {}


def test_unknown_behavior_is_rejected(env):
    t, result = start_permission(env)
    (p,) = wait_pending(env["store"])
    assert env["api"].decide(p["id"], "allow-everything") is False
    assert len(env["store"].snapshot()["pending"]) == 1
    env["api"].decide(p["id"], "deny")
    finish(t, result)


def test_post_tool_use_cancels_the_pending_request(env):
    t, result = start_permission(env)
    wait_pending(env["store"])
    post(env, "PostToolUse", BASH)  # the user answered in the terminal and the tool ran
    assert finish(t, result) == {}
    assert env["store"].snapshot()["pending"] == []
    assert session(env["store"])["status"] == "working"


def test_post_tool_use_of_another_tool_does_not_cancel(env):
    t, result = start_permission(env)
    (p,) = wait_pending(env["store"])
    post(env, "PostToolUse", {"session_id": SID, "tool_name": "Read", "tool_input": {"file_path": "a.py"}})
    time.sleep(0.1)
    assert t.is_alive()
    env["api"].decide(p["id"], "allow")
    assert finish(t, result)["hookSpecificOutput"]["decision"]["behavior"] == "allow"


@pytest.mark.parametrize("event", ["Stop", "UserPromptSubmit", "SessionEnd"])
def test_session_moving_on_cancels(env, event):
    t, result = start_permission(env)
    wait_pending(env["store"])
    post(env, event, {"session_id": SID})
    assert finish(t, result) == {}


def test_other_session_events_do_not_cancel(env):
    t, result = start_permission(env)
    (p,) = wait_pending(env["store"])
    post(env, "Stop", {"session_id": "another-session"})
    time.sleep(0.1)
    assert t.is_alive()
    env["api"].decide(p["id"], "allow")
    finish(t, result)


def test_timeout_returns_empty(env):
    env["settings"].set("permission_wait", 0.2)
    t, result = start_permission(env)
    assert finish(t, result) == {}
    assert env["store"].snapshot()["pending"] == []


def test_codex_permission(env):
    t, result = start_permission(env, {"session_id": SID, "tool_name": "shell",
                                       "tool_input": {"command": ["git", "status"]}}, agent="codex")
    (p,) = wait_pending(env["store"])
    assert (p["agent"], p["text"]) == ("codex", "git status")
    env["api"].decide(p["id"], "allow")
    assert finish(t, result)["hookSpecificOutput"]["decision"]["behavior"] == "allow"


def test_disabled_module_answers_immediately(env):
    env["settings"].set("modules.claude", False)
    assert post(env, "PermissionRequest", BASH) == {}
    assert env["store"].snapshot()["pending"] == []


def test_no_http_endpoint_touches_permissions(env):
    """Permission decisions go only through js_api: the server only receives hooks."""
    rules = {(r.rule, tuple(sorted(r.methods - {"HEAD", "OPTIONS"}))) for r in env["app"].url_map.iter_rules()
             if r.endpoint != "static"}
    assert rules == {("/hook/<event>", ("POST",)), ("/statusline", ("POST",)),
                     ("/ui/show", ("POST",)), ("/health", ("GET",))}


# ---------------------------------------------------------------- "allow for N minutes"

def test_timed_rule_auto_approves_the_same_tool_in_the_same_project(env):
    t, result = start_permission(env)
    (p,) = wait_pending(env["store"])
    assert p["can_grant"] is True and "_cwd" not in p
    assert env["api"].decide(p["id"], "grant:15") is True
    assert finish(t, result)["hookSpecificOutput"]["decision"] == {"behavior": "allow"}
    (g,) = env["store"].snapshot()["grants"]
    assert (g["tool"], g["project"]) == ("Bash", "ExampleApp")
    assert 14 * 60 < g["until"] - time.time() <= 15 * 60

    # same project and tool: answered at once, nothing waits in the UI
    again = post(env, "PermissionRequest", {**BASH, "tool_input": {"command": "npm run lint"}})
    assert again["hookSpecificOutput"]["decision"] == {"behavior": "allow"}

    # another project, another tool or another agent still ask
    for payload, agent in (({**BASH, "cwd": "C:/rep/OtherApp"}, "claude"),
                           ({**BASH, "tool_name": "PowerShell"}, "claude"), (BASH, "codex")):
        t, result = start_permission(env, payload, agent)
        (p,) = wait_pending(env["store"])
        env["api"].decide(p["id"], "deny")
        finish(t, result)


@pytest.mark.parametrize("command", ["rm -rf build", "del /q *.log", "git push --force", "git push -f origin main",
                                     "sqlcmd -Q \"DROP TABLE Orders\"", "type C:/Users/x/secret.txt", "cat ../x"])
def test_timed_rule_never_covers_dangerous_commands(env, command):
    t, result = start_permission(env)
    (p,) = wait_pending(env["store"])
    env["api"].decide(p["id"], "grant:60")
    finish(t, result)

    t, result = start_permission(env, {**BASH, "tool_input": {"command": command}})
    (p,) = wait_pending(env["store"])
    assert p["can_grant"] is False
    assert env["api"].decide(p["id"], "grant:5") is False  # a dangerous request cannot start a rule either
    env["api"].decide(p["id"], "deny")
    assert finish(t, result)["hookSpecificOutput"]["decision"]["behavior"] == "deny"


def test_timed_rule_expires_and_can_be_revoked(env):
    t, result = start_permission(env)
    (p,) = wait_pending(env["store"])
    env["api"].decide(p["id"], "grant:5")
    finish(t, result)
    (g,) = env["store"].snapshot()["grants"]

    env["store"]._grants[0]["until"] = time.time() - 1  # expired
    assert env["store"].snapshot()["grants"] == []
    t, result = start_permission(env)
    (p,) = wait_pending(env["store"])
    env["api"].decide(p["id"], "grant:5")
    finish(t, result)

    (g,) = env["store"].snapshot()["grants"]
    env["api"].revoke_grant(g["id"])
    assert env["store"].snapshot()["grants"] == []
    t, result = start_permission(env)
    wait_pending(env["store"])
    post(env, "Stop", {"session_id": SID})
    assert finish(t, result) == {}


def test_only_offered_durations_are_accepted(env):
    t, result = start_permission(env)
    (p,) = wait_pending(env["store"])
    assert env["api"].decide(p["id"], "grant:9999") is False
    env["api"].decide(p["id"], "deny")
    finish(t, result)


@pytest.mark.parametrize("tool", ["ExitPlanMode", "AskUserQuestion"])
def test_plan_approval_and_questions_go_to_the_terminal(env, tool):
    """Claude Code's own dialog answers these: Skerry must not hold them, nor show Allow/Deny."""
    t0 = time.time()
    out = post(env, "PermissionRequest", {**BASH, "tool_name": tool, "tool_input": {"plan": "1. Do things"}})
    assert out == {} and time.time() - t0 < 2
    assert env["store"].snapshot()["pending"] == []
    s = next(x for x in env["store"].snapshot()["sessions"] if x["sid"].endswith(SID))
    assert s["status"] == "waiting"
