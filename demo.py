"""Simulate Claude Code and Codex to try Skerry without running them.
Start Skerry first, then:  python demo.py
"""
import json
import threading
import time
import urllib.request

from skerry.settings import load_raw

BASE = f"http://127.0.0.1:{load_raw()['port']}"


def post(path, payload, timeout=5):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"{}")


def hook(agent, sid, cwd, event, **kw):
    return post(f"/hook/{event}?agent={agent}",
                {"session_id": sid, "cwd": cwd, "hook_event_name": event, **kw}, timeout=400)


def claude():
    sid, cwd = "demo-claude", "C:/rep/ExampleApp"
    now = int(time.time())
    post("/statusline", {"session_id": sid, "cwd": cwd, "model": {"display_name": "Opus"},
                         "context_window": {"used_percentage": 34},
                         "rate_limits": {"five_hour": {"used_percentage": 82.5, "resets_at": now + 5400},
                                         "seven_day": {"used_percentage": 41.2, "resets_at": now + 300000}}})
    hook("claude", sid, cwd, "SessionStart", source="startup")
    hook("claude", sid, cwd, "UserPromptSubmit", prompt="Aggiungi il login a ExampleApp")
    time.sleep(2)
    todos = [{"content": "Leggere la configurazione", "activeForm": "Leggo la configurazione", "status": "completed"},
             {"content": "Aggiungere MSAL", "activeForm": "Aggiungo MSAL", "status": "in_progress"},
             {"content": "Scrivere i test", "activeForm": "Scrivo i test", "status": "pending"}]
    hook("claude", sid, cwd, "PreToolUse", tool_name="TodoWrite", tool_input={"todos": todos})
    for tool, inp in [("Read", {"file_path": "C:/rep/ExampleApp/app.py"}), ("Grep", {"pattern": "msal"}),
                      ("Edit", {"file_path": "C:/rep/ExampleApp/auth.py"})]:
        hook("claude", sid, cwd, "PreToolUse", tool_name=tool, tool_input=inp)
        time.sleep(2)
    print("Claude: richiesta di permesso, rispondi sull'isola…")
    res = hook("claude", sid, cwd, "PermissionRequest", tool_name="Bash",
               tool_input={"command": "pip install msal && pytest -q"},
               permission_suggestions=[{"type": "addRules", "rules": [{"toolName": "Bash", "ruleContent": "pytest:*"}],
                                        "behavior": "allow", "destination": "localSettings"}])
    print("Claude → risposta:", res or "{} (terminale)")
    todos[1]["status"], todos[2]["status"] = "completed", "in_progress"
    hook("claude", sid, cwd, "PreToolUse", tool_name="TodoWrite", tool_input={"todos": todos})
    hook("claude", sid, cwd, "PreToolUse", tool_name="Bash", tool_input={"command": "pytest -q"})
    time.sleep(3)
    hook("claude", sid, cwd, "Stop", last_assistant_message="Login aggiunto con MSAL: 12 test ok.")


def codex():
    sid, cwd = "demo-codex", "C:/rep/SampleService"
    time.sleep(4)
    hook("codex", sid, cwd, "SessionStart", source="startup")
    hook("codex", sid, cwd, "UserPromptSubmit")
    for cmd in (["rg", "todo_items"], ["python", "-m", "pytest", "tests/test_search.py"]):
        hook("codex", sid, cwd, "PreToolUse", tool_name="shell", tool_input={"command": cmd})
        time.sleep(3)
    hook("codex", sid, cwd, "Stop", last_assistant_message="Indice di ricerca ricostruito, test verdi.")


threads = [threading.Thread(target=claude), threading.Thread(target=codex)]
[t.start() for t in threads]
[t.join() for t in threads]
print("Fine demo.")
