"""Connect/disconnect Claude Code (~/.claude/settings.json) and Codex (~/.codex/hooks.json)."""
import json
import logging
import os
import re
import shutil
import time

from . import paths

log = logging.getLogger("skerry")

HOME = os.path.expanduser("~")
CLAUDE_SETTINGS = os.path.join(HOME, ".claude", "settings.json")
CODEX_DIR = os.path.join(HOME, ".codex")
CODEX_HOOKS = os.path.join(CODEX_DIR, "hooks.json")

HOOKS_VERSION = 3  # bump when the hooks change: they are rewritten on the first run after an update
OUR_URL = re.compile(r"^http://127\.0\.0\.1:\d+/hook/")
CLAUDE_HTTP_EVENTS = {
    "UserPromptSubmit": 5, "PreToolUse": 5, "PostToolUse": 5, "PostToolUseFailure": 5, "PermissionRequest": None,
    "Notification": 5, "Stop": 5, "StopFailure": 5, "SessionEnd": 2, "TaskCreated": 5, "TaskCompleted": 5,
}
CODEX_EVENTS = {"SessionStart": 10, "UserPromptSubmit": 10, "PreToolUse": 10, "PermissionRequest": None,
                "Stop": 10, "SessionEnd": 10}
# Hook commands we own. "island-cli" was written by versions before the rename: still ours, so it gets stripped.
CLI_MARKERS = ("skerry-cli", "island-cli", "cli.py")
WITH_MATCHER = {"PreToolUse", "PostToolUse", "PostToolUseFailure", "PermissionRequest"}


def _slash(p):
    return p.replace("\\", "/")


def cli_command(*args):
    """Command that runs the hook CLI (exe when packaged, python in development)."""
    if paths.FROZEN:
        exe = os.path.join(paths.install_dir(), "skerry-cli.exe")
        return f'"{_slash(exe)}" ' + " ".join(args)
    py = paths.python_console()
    cli = os.path.join(paths.resource_dir(), "cli.py")
    return f'"{_slash(py)}" "{_slash(cli)}" ' + " ".join(args)


def _is_our_cmd(cmd, kind):
    cmd = str(cmd or "")
    return any(m in cmd for m in CLI_MARKERS) and f" {kind}" in cmd


def _is_ours(group, agent):
    for h in group.get("hooks", []):
        if OUR_URL.match(str(h.get("url", ""))):
            return True
        if h.get("type") == "command" and _is_our_cmd(h.get("command"), f"hook {agent}"):
            return True
    return False


def _read(path):
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        text = f.read().strip()
    return json.loads(text) if text else {}


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        backup_dir = os.path.join(paths.data_dir(), "backup")
        os.makedirs(backup_dir, exist_ok=True)
        shutil.copy2(path, os.path.join(backup_dir, f"{os.path.basename(path)}.{time.strftime('%Y%m%d-%H%M%S')}"))
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def _strip(hooks, agent):
    for ev in list(hooks):
        hooks[ev] = [g for g in hooks[ev] if not _is_ours(g, agent)]
        if not hooks[ev]:
            del hooks[ev]


# ---------------- Claude Code ----------------
def claude_status():
    try:
        data = _read(CLAUDE_SETTINGS)
    except Exception as e:
        return {"installed": False, "error": str(e)}
    hooks = data.get("hooks", {})
    installed = any(_is_ours(g, "claude") for groups in hooks.values() for g in groups)
    sl = (data.get("statusLine") or {}).get("command", "")
    return {"installed": installed, "statusline": _is_our_cmd(sl, "statusline"),
            "available": os.path.isdir(os.path.dirname(CLAUDE_SETTINGS))}


def claude_install(settings):
    data = _read(CLAUDE_SETTINGS)
    hooks = data.setdefault("hooks", {})
    _strip(hooks, "claude")
    port = settings.get("port", 47800)
    wait = int(settings.get("permission_wait", 300)) + 30
    hooks.setdefault("SessionStart", []).append(
        {"hooks": [{"type": "command", "command": cli_command("hook", "claude"), "timeout": 10}]})
    for ev, timeout in CLAUDE_HTTP_EVENTS.items():
        group = {"hooks": [{"type": "http", "url": f"http://127.0.0.1:{port}/hook/{ev}?agent=claude",
                            "timeout": timeout or wait}]}
        if ev in WITH_MATCHER:
            group = {"matcher": "*", **group}
        hooks.setdefault(ev, []).append(group)
    current = data.get("statusLine") or {}
    if current.get("command") and not _is_our_cmd(current.get("command"), "statusline"):
        settings.set("chained_statusline", current["command"])
    data["statusLine"] = {"type": "command", "command": cli_command("statusline")}
    _write(CLAUDE_SETTINGS, data)
    settings.set("hooks_version", HOOKS_VERSION)
    log.info("Claude Code collegato")


def claude_uninstall(settings):
    if not os.path.exists(CLAUDE_SETTINGS):
        return
    data = _read(CLAUDE_SETTINGS)
    hooks = data.get("hooks", {})
    _strip(hooks, "claude")
    if not hooks:
        data.pop("hooks", None)
    if _is_our_cmd((data.get("statusLine") or {}).get("command"), "statusline"):
        chained = settings.get("chained_statusline")
        if chained:
            data["statusLine"] = {"type": "command", "command": chained}
            settings.set("chained_statusline", None)
        else:
            data.pop("statusLine", None)
    _write(CLAUDE_SETTINGS, data)
    log.info("Claude Code scollegato")


# ---------------- Codex ----------------
def codex_status():
    try:
        data = _read(CODEX_HOOKS)
    except Exception as e:
        return {"installed": False, "error": str(e), "available": os.path.isdir(CODEX_DIR)}
    hooks = data.get("hooks", {})
    installed = any(_is_ours(g, "codex") for groups in hooks.values() for g in groups)
    return {"installed": installed, "available": os.path.isdir(CODEX_DIR)}


def codex_install(settings):
    data = _read(CODEX_HOOKS)
    hooks = data.setdefault("hooks", {})
    _strip(hooks, "codex")
    wait = int(settings.get("permission_wait", 300)) + 30
    for ev, timeout in CODEX_EVENTS.items():
        group = {"hooks": [{"type": "command", "command": cli_command("hook", "codex"), "timeout": timeout or wait}]}
        if ev in WITH_MATCHER:
            group = {"matcher": ".*", **group}
        hooks.setdefault(ev, []).append(group)
    _write(CODEX_HOOKS, data)
    log.info("Codex collegato")


def codex_uninstall(settings):
    if not os.path.exists(CODEX_HOOKS):
        return
    data = _read(CODEX_HOOKS)
    _strip(data.get("hooks", {}), "codex")
    _write(CODEX_HOOKS, data)
    log.info("Codex scollegato")
