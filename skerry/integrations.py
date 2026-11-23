"""Connect/disconnect the agents: Claude Code (~/.claude/settings.json), Codex (~/.codex/hooks.json),
Gemini CLI (~/.gemini/settings.json), GitHub Copilot CLI (~/.copilot/hooks/skerry.json) and OpenCode
(~/.config/opencode/plugins/skerry.js)."""
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
GEMINI_SETTINGS = os.path.join(HOME, ".gemini", "settings.json")
COPILOT_DIR = os.environ.get("COPILOT_HOME") or os.path.join(HOME, ".copilot")
COPILOT_HOOKS = os.path.join(COPILOT_DIR, "hooks", "skerry.json")   # our own file: disconnecting deletes it

HOOKS_VERSION = 4  # bump when the hooks change: they are rewritten on the first run after an update
OUR_URL = re.compile(r"^http://127\.0\.0\.1:\d+/hook/")
# Claude Code hooks: all are `skerry-cli hook claude` commands, which exit 0 with no output when Skerry is not
# running, so Claude Code shows nothing (an "http" hook would show "hook failed: ECONNREFUSED" on every event).
# Only PermissionRequest waits for the answer; the others run in the background ("async") and add no latency.
# Up to hooks v3 these were "http" hooks: _is_ours() still recognises them by URL so they get replaced/removed.
CLAUDE_EVENTS = {   # event -> timeout in seconds (None = permission_wait + 30)
    "SessionStart": 10, "UserPromptSubmit": 5, "PreToolUse": 5, "PostToolUse": 5, "PostToolUseFailure": 5,
    "PermissionRequest": None, "Notification": 5, "Stop": 5, "StopFailure": 5, "SessionEnd": 5,
    "TaskCreated": 5, "TaskCompleted": 5,
}
CLAUDE_SYNC = {"PermissionRequest"}
CODEX_EVENTS = {"SessionStart": 10, "UserPromptSubmit": 10, "PreToolUse": 10, "PermissionRequest": None,
                "Stop": 10, "SessionEnd": 10}
# Gemini CLI waits for every hook (timeout in ms): activity only, so they are all short.
GEMINI_EVENTS = ("SessionStart", "SessionEnd", "BeforeAgent", "BeforeTool", "AfterTool", "AfterAgent", "Notification")
GEMINI_MATCHER = {"BeforeTool", "AfterTool"}
COPILOT_EVENTS = {   # event -> timeoutSec (None = permission_wait + 30). On timeout Copilot asks the user as usual.
    "sessionStart": 10, "sessionEnd": 10, "userPromptSubmitted": 10, "preToolUse": 10, "postToolUse": 10,
    "postToolUseFailure": 10, "agentStop": 10, "errorOccurred": 10, "permissionRequest": None,
}
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
    wait = int(settings.get("permission_wait", 300)) + 30
    command = cli_command("hook", "claude")
    for ev, timeout in CLAUDE_EVENTS.items():
        hook = {"type": "command", "command": command, "timeout": timeout or wait}
        if ev not in CLAUDE_SYNC:
            hook["async"] = True
        group = {"hooks": [hook]}
        if ev in WITH_MATCHER:
            group = {"matcher": "*", **group}
        hooks.setdefault(ev, []).append(group)
    current = data.get("statusLine") or {}
    if current.get("command") and not _is_our_cmd(current.get("command"), "statusline"):
        settings.set("chained_statusline", current["command"])
    data["statusLine"] = {"type": "command", "command": cli_command("statusline")}
    _write(CLAUDE_SETTINGS, data)
    settings.set("hooks_version", HOOKS_VERSION)
    log.info("Claude Code connected")


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
    log.info("Claude Code disconnected")


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
    log.info("Codex connected")


def codex_uninstall(settings):
    if not os.path.exists(CODEX_HOOKS):
        return
    data = _read(CODEX_HOOKS)
    _strip(data.get("hooks", {}), "codex")
    _write(CODEX_HOOKS, data)
    log.info("Codex disconnected")


# ---------------- Gemini CLI ----------------
def gemini_status():
    available = bool(shutil.which("gemini")) or os.path.exists(GEMINI_SETTINGS)
    try:
        hooks = _read(GEMINI_SETTINGS).get("hooks", {})
    except Exception as e:
        return {"installed": False, "error": str(e), "available": available}
    installed = any(_is_ours(g, "gemini") for groups in hooks.values() if isinstance(groups, list) for g in groups)
    return {"installed": installed, "available": available}


def gemini_install(settings):
    data = _read(GEMINI_SETTINGS)
    hooks = data.setdefault("hooks", {})
    _strip(hooks, "gemini")
    for ev in GEMINI_EVENTS:
        group = {"hooks": [{"name": "skerry", "type": "command", "command": cli_command("hook", "gemini"),
                            "timeout": 5000}]}
        if ev in GEMINI_MATCHER:
            group = {"matcher": "*", **group}
        hooks.setdefault(ev, []).append(group)
    _write(GEMINI_SETTINGS, data)
    log.info("Gemini CLI connected")


def gemini_uninstall(settings):
    if not os.path.exists(GEMINI_SETTINGS):
        return
    data = _read(GEMINI_SETTINGS)
    hooks = data.get("hooks", {})
    _strip(hooks, "gemini")
    if not hooks:
        data.pop("hooks", None)
    _write(GEMINI_SETTINGS, data)
    log.info("Gemini CLI disconnected")


# ---------------- GitHub Copilot CLI ----------------
def copilot_status():
    return {"installed": os.path.exists(COPILOT_HOOKS),
            "available": bool(shutil.which("copilot")) or os.path.isdir(COPILOT_DIR)}


def copilot_install(settings):
    wait = int(settings.get("permission_wait", 300)) + 30
    hooks = {}
    for ev, timeout in COPILOT_EVENTS.items():
        cmd = cli_command("hook", "copilot", ev)
        hooks[ev] = [{"type": "command", "bash": cmd, "powershell": "& " + cmd, "timeoutSec": timeout or wait}]
    _write(COPILOT_HOOKS, {"version": 1, "hooks": hooks})
    log.info("GitHub Copilot CLI connected")


def copilot_uninstall(settings):
    if os.path.exists(COPILOT_HOOKS):
        os.remove(COPILOT_HOOKS)
    log.info("GitHub Copilot CLI disconnected")


# ---------------- OpenCode ----------------
# OpenCode has no command hooks: it loads JavaScript plugins from ~/.config/opencode/plugins/. Skerry writes its own
# dependency-free plugin there (disconnecting deletes the file). It forwards activity to Skerry's local server in the
# background and, for a permission request, waits for the answer from the island and replies to OpenCode's own server
# (current API /permission/{id}/reply, older /session/{id}/permissions/{id}). If Skerry is off or nobody answers in
# time, nothing is replied and OpenCode keeps asking in the terminal as usual.
OPENCODE_DIR = os.environ.get("OPENCODE_CONFIG_DIR") or os.path.join(HOME, ".config", "opencode")
OPENCODE_PLUGIN = os.path.join(OPENCODE_DIR, "plugins", "skerry.js")
OPENCODE_MARKER = "// Skerry plugin for OpenCode"
OPENCODE_SOURCE = OPENCODE_MARKER + r""" (written by Skerry: disconnect it from Skerry's settings, do not edit).
const HOOK = "http://127.0.0.1:__PORT__/hook/";
const WAIT_MS = (__WAIT__ + 20) * 1000;

async function send(event, body, ms) {
  try {
    const r = await fetch(HOOK + event + "?agent=opencode", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({hook_event_name: event, ...body}), signal: AbortSignal.timeout(ms)});
    return await r.json();
  } catch (e) {
    return {};            // Skerry not running: never get in OpenCode's way
  }
}

export const Skerry = async ({ directory, serverUrl }) => {
  const cwd = directory;
  const busy = {};          // last known state per session: only idle -> busy counts as a new prompt
  const base = String(serverUrl || "").replace(/\/$/, "");
  const post = (path, body) => fetch(base + path, {method: "POST", headers: {"Content-Type": "application/json"},
                                                   body: JSON.stringify(body)}).catch(() => null);

  async function permission(p, legacy) {
    const out = await send("PermissionRequest", {
      session_id: p.sessionID, cwd, permission_id: p.id,
      tool_name: legacy ? p.type : p.permission,
      tool_input: {patterns: p.patterns || p.pattern || [], title: p.title || "", ...(p.metadata || {})},
      can_always: Boolean(legacy || (p.always && p.always.length)),
    }, WAIT_MS);
    const d = out && out.decision;
    if (!d || !base) return;
    if (legacy) await post(`/session/${p.sessionID}/permissions/${p.id}`, {response: d});
    else await post(`/permission/${p.id}/reply`, {reply: d});
  }

  return {
    event: async ({ event }) => {
      const p = event.properties || {};
      switch (event.type) {
        case "session.created": send("SessionStart", {session_id: p.info && p.info.id, cwd}, 3000); break;
        case "session.status": {
          const now = Boolean(p.status && p.status.type === "busy");
          if (now && !busy[p.sessionID]) send("UserPromptSubmit", {session_id: p.sessionID, cwd}, 3000);
          busy[p.sessionID] = now;
          break;
        }
        case "session.idle":
          busy[p.sessionID] = false;
          send("Stop", {session_id: p.sessionID, cwd}, 3000);
          break;
        case "session.error":
          send("StopFailure", {session_id: p.sessionID, cwd, error: (p.error && (p.error.name || p.error.message)) || ""}, 3000);
          break;
        case "session.deleted": send("SessionEnd", {session_id: p.info && p.info.id, cwd}, 3000); break;
        case "permission.asked": permission(p, false); break;          // not awaited: OpenCode keeps running
        case "permission.updated": permission(p, true); break;         // OpenCode before the permission rewrite
        case "permission.replied":
          send("PermissionResolved", {session_id: p.sessionID, cwd}, 3000); break;
      }
    },
    "tool.execute.before": async (input, output) => {
      send("PreToolUse", {session_id: input.sessionID, cwd, tool_name: input.tool, tool_input: output.args}, 3000);
    },
    "tool.execute.after": async (input) => {
      send("PostToolUse", {session_id: input.sessionID, cwd, tool_name: input.tool, tool_input: input.args}, 3000);
    },
  };
};
"""


def opencode_status():
    return {"installed": os.path.exists(OPENCODE_PLUGIN),
            "available": bool(shutil.which("opencode")) or os.path.isdir(OPENCODE_DIR)}


def opencode_install(settings):
    src = (OPENCODE_SOURCE.replace("__PORT__", str(int(settings.get("port", 47800))))
           .replace("__WAIT__", str(int(settings.get("permission_wait", 300)))))
    os.makedirs(os.path.dirname(OPENCODE_PLUGIN), exist_ok=True)
    tmp = OPENCODE_PLUGIN + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(src)
    os.replace(tmp, OPENCODE_PLUGIN)
    log.info("OpenCode connected")


def opencode_uninstall(settings):
    try:
        with open(OPENCODE_PLUGIN, encoding="utf-8") as f:
            ours = f.read().startswith(OPENCODE_MARKER)
    except OSError:
        return
    if ours:                                   # never delete a skerry.js the user wrote
        os.remove(OPENCODE_PLUGIN)
    log.info("OpenCode disconnected")


# ---------------- all agents ----------------
AGENTS = ("claude", "codex", "gemini", "copilot", "opencode")


def functions(agent):
    """(status, install, uninstall) of an agent, looked up at call time."""
    g = globals()
    return g[f"{agent}_status"], g[f"{agent}_install"], g[f"{agent}_uninstall"]


def statuses():
    return {a: functions(a)[0]() for a in AGENTS}


def refresh_connected(settings):
    """Rewrite the hooks of the opt-in agents that are already connected (after an update or a new wait time)."""
    for agent in ("gemini", "copilot", "opencode"):
        status, install, _ = functions(agent)
        if status().get("installed"):
            install(settings)
