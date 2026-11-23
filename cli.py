"""CLI used by Claude Code and Codex (skerry-cli.exe in the package).

  skerry-cli hook <claude|codex>   forward a hook event (JSON on stdin) to Skerry
  skerry-cli statusline            Claude Code status line (+ forwards the rate limits)
  skerry-cli connect | disconnect  connect/disconnect Claude Code and Codex
"""
import json
import subprocess
import sys
import urllib.request

from skerry.settings import load_raw

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdin.reconfigure(encoding="utf-8")
except Exception:
    pass


def _post(port, path, payload, timeout):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8")


def _read_stdin():
    try:
        raw = sys.stdin.read()
        return raw, (json.loads(raw) if raw.strip() else {})
    except Exception:
        return "", {}


def cmd_hook(agent):
    s = load_raw()
    _, payload = _read_stdin()
    event = payload.get("hook_event_name", "")
    if event == "SessionStart":
        try:
            from skerry.terminal import find_terminal_hwnd
            payload["terminal_hwnd"] = find_terminal_hwnd()
        except Exception:
            pass
    timeout = int(s.get("permission_wait", 300)) + 20 if event == "PermissionRequest" else 4
    try:
        body = _post(s["port"], f"/hook/{event}?agent={agent}", payload, timeout)
    except Exception:
        return 0  # Skerry not running: no decision, the agent carries on normally
    body = (body or "").strip()
    if body and body != "{}":
        print(body)
    return 0


def cmd_statusline():
    s = load_raw()
    raw, data = _read_stdin()
    try:
        _post(s["port"], "/statusline", data, 1.0)
    except Exception:
        pass
    chained = s.get("chained_statusline")
    if chained:
        try:
            out = subprocess.run(chained, input=raw, shell=True, capture_output=True, text=True,
                                 encoding="utf-8", timeout=5)
            if out.returncode == 0 and out.stdout.strip():
                sys.stdout.write(out.stdout)
                return 0
        except Exception:
            pass
    model = (data.get("model") or {}).get("display_name", "Claude")
    parts = [f"[{model}]"]
    ctx = (data.get("context_window") or {}).get("used_percentage")
    if ctx is not None:
        parts.append(f"ctx {ctx:.0f}%")
    rl = data.get("rate_limits") or {}
    for key, label in (("five_hour", "5h"), ("seven_day", "7g")):
        pct = (rl.get(key) or {}).get("used_percentage")
        if pct is not None:
            parts.append(f"{label} {pct:.0f}%")
    print(" | ".join(parts))
    return 0


def cmd_connect(on):
    from skerry import integrations
    from skerry.settings import Settings
    st = Settings()
    if on:
        integrations.claude_install(st)
        if integrations.codex_status().get("available"):
            integrations.codex_install(st)
    else:
        integrations.claude_uninstall(st)
        integrations.codex_uninstall(st)
    print("Fatto.")
    return 0


def main(argv):
    if len(argv) >= 2 and argv[0] == "hook":
        return cmd_hook(argv[1])
    if argv[:1] == ["statusline"]:
        return cmd_statusline()
    if argv[:1] in (["connect"], ["disconnect"]):
        return cmd_connect(argv[0] == "connect")
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
