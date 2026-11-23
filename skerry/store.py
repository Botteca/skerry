"""Shared agent state (Claude Code, Codex): sessions, permissions, tasks, alerts, limits."""
import itertools
import logging
import os
import re
import threading
import time
import uuid
from collections import OrderedDict

from . import history
from .agents import ACTIVITY_ONLY
from .i18n import Msg, render, t

log = logging.getLogger("skerry")

TOOL_ICONS = {
    "Read": "👁", "Edit": "✏️", "MultiEdit": "✏️", "Write": "📝", "NotebookEdit": "📓",
    "Bash": "⌨️", "PowerShell": "⌨️", "shell": "⌨️", "local_shell": "⌨️", "exec_command": "⌨️",
    "Grep": "🔎", "Glob": "🔎", "LS": "📁", "WebFetch": "🌐", "WebSearch": "🌐", "web_search": "🌐",
    "Task": "🤖", "Agent": "🤖", "TodoWrite": "☑️", "TaskCreate": "☑️", "TaskUpdate": "☑️",
    "update_plan": "☑️", "apply_patch": "✏️",
    # Gemini CLI and Copilot CLI tool names
    "run_shell_command": "⌨️", "bash": "⌨️", "powershell": "⌨️", "read_file": "👁", "read_many_files": "👁",
    "view": "👁", "write_file": "📝", "create": "📝", "replace": "✏️", "edit": "✏️", "glob": "🔎",
    "search_file_content": "🔎", "grep": "🔎", "google_web_search": "🌐", "web_fetch": "🌐",
}
AGENTS = {"claude": "Claude Code", "codex": "Codex", "gemini": "Gemini CLI", "copilot": "Copilot CLI"}
FILE_TOOLS = {"Read": "action.read", "read_file": "action.read", "view": "action.read", "Write": "action.write",
              "write_file": "action.write", "create": "action.write", "Edit": "action.edit",
              "MultiEdit": "action.edit", "NotebookEdit": "action.edit", "replace": "action.edit", "edit": "action.edit"}

# "Allow for N minutes": durations offered in the UI, and what such a rule never covers.
GRANT_MINUTES = (5, 15, 60)
DANGEROUS = re.compile(
    r"\b(rm|rmdir|rd|del|erase|remove-item|format|drop|truncate)\b"
    r"|\bgit\b.*\bpush\b.*(--force|\s-[a-z]*f|\s\+\S)", re.I)
# paths that may leave the project: parent dirs, home, environment variables, POSIX absolute paths
OUTSIDE = re.compile(r"""(^|[\s"'=\\/])\.\.($|[\s"'\\/])|(^|\s)~|\$env:|\$home\b|%\w+%|(^|[\s"'=])/\w+/""", re.I)
WIN_PATH = re.compile(r"""(?:[A-Za-z]:[\\/]|\\\\)[^\s"'|;&<>()]*""")
PATCH_FILE = re.compile(r"^\*\*\* (Add|Update|Delete) File: (.+)$", re.M)


def short(text, n=90):
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[: n - 1] + "…"


def describe(tool, inp):
    """(icon, short text, detail) for an agent action. The text is a `Msg` (translated when shown) or plain text."""
    tool = tool or ""
    inp = inp if isinstance(inp, dict) else {"input": inp}
    icon = TOOL_ICONS.get(tool, "🔌" if tool.startswith("mcp__") else "⚙️")
    fp = inp.get("file_path") or inp.get("notebook_path") or inp.get("absolute_path") or inp.get("path")
    if tool in FILE_TOOLS and fp:
        return icon, Msg(FILE_TOOLS[tool], file=os.path.basename(str(fp))), str(fp)
    if tool == "apply_patch":
        return icon, Msg("action.patch"), short(inp.get("input") or inp.get("patch") or "", 400)
    cmd = inp.get("command") or inp.get("cmd")
    if cmd is not None:
        if isinstance(cmd, list):
            cmd = " ".join(str(c) for c in cmd)
        return TOOL_ICONS.get(tool, "⌨️"), short(cmd, 60), str(cmd)
    if tool in ("Grep", "Glob"):
        return icon, Msg("action.search", pattern=short(inp.get("pattern", ""), 50)), str(inp.get("path") or "")
    if tool == "WebFetch":
        return icon, Msg("action.fetch", url=short(inp.get("url", ""), 50)), str(inp.get("url", ""))
    if tool in ("WebSearch", "web_search"):
        return icon, Msg("action.web_search", query=short(inp.get("query", ""), 40)), str(inp.get("query", ""))
    if tool in ("Task", "Agent"):
        return icon, Msg("action.agent", description=short(inp.get("description", ""), 50)), str(inp.get("prompt", ""))[:400]
    if tool in ("TodoWrite", "TaskCreate", "TaskUpdate", "update_plan"):
        return icon, Msg("action.tasks"), ""
    if tool.startswith("mcp__"):
        parts = tool.split("__")
        return icon, f"{parts[1]} · {parts[-1]}", short(inp, 300)
    return icon, tool or Msg("action.generic"), short(inp, 300)


def _inside(path, cwd):
    root = os.path.normcase(os.path.abspath(cwd))
    p = os.path.normcase(os.path.abspath(os.path.join(cwd, os.path.expanduser(str(path).strip()))))
    return p == root or p.startswith(root.rstrip("\\/") + os.sep)


def risky(tool, inp, cwd):
    """True when a timed rule must not approve this request: destructive command or a path outside the project.

    shortcut: only the usual path keys (file_path, notebook_path, path), commands and apply_patch are inspected;
    extend this if an agent tool takes paths under other keys.
    """
    if not cwd:
        return True
    inp = inp if isinstance(inp, dict) else {"input": inp}
    for key in ("file_path", "notebook_path", "path"):
        if inp.get(key) and not _inside(inp[key], cwd):
            return True
    cmd = inp.get("command") or inp.get("cmd")
    if isinstance(cmd, list):
        cmd = " ".join(str(c) for c in cmd)
    if cmd is not None:
        cmd = str(cmd)
        if DANGEROUS.search(cmd) or OUTSIDE.search(cmd) or any(not _inside(m, cwd) for m in WIN_PATH.findall(cmd)):
            return True
    if tool == "apply_patch":
        for m in PATCH_FILE.finditer(str(inp.get("input") or inp.get("patch") or "")):
            if m.group(1) == "Delete" or not _inside(m.group(2), cwd):
                return True
    return False


class Store:
    def __init__(self, settings, on_event=None):
        self._settings = settings
        self._lock = threading.RLock()
        self._sessions = {}
        self._pending = OrderedDict()
        self._grants = []   # "allow for N minutes" rules: same agent, project folder and tool, until expiry
        self._alerts = []
        self._fired = set()
        self._limits = None
        self._sl = {"seen": False, "at": 0, "limits": False}
        self._selected = None
        self._ui_seq = 0
        self._ids = itertools.count(1)
        self._on_event = on_event or (lambda kind: None)

    # ---------------- sessions ----------------
    def _session(self, payload, agent):
        sid = f"{agent}:{payload.get('session_id') or 'default'}"
        s = self._sessions.get(sid)
        if s is None:
            log.info("New session %s (%s)", sid, payload.get("cwd") or "?")
            s = self._sessions[sid] = {
                "sid": sid, "agent": agent, "project": "", "status": "idle", "icon": "", "action": "",
                "updated": time.time(), "done_msg": "", "done_at": 0, "model": "",
                "context_pct": None, "cost": None, "tasks": None, "hwnd": 0, "_tasks": {},
            }
        cwd = payload.get("cwd") or (payload.get("workspace") or {}).get("project_dir")
        if cwd and not s["project"]:
            s["project"] = os.path.basename(os.path.normpath(str(cwd))) or str(cwd)
        if payload.get("terminal_hwnd"):
            s["hwnd"] = int(payload["terminal_hwnd"])
        s["updated"] = time.time()
        return s

    def _cancel_pending_for(self, sid):
        for p in self._pending.values():
            if p["sid"] == sid and p["result"] is None:
                p["result"] = "cancelled"
                p["event"].set()

    @staticmethod
    def _task_summary(s):
        tasks = s["_tasks"]
        if not tasks:
            return None
        done = sum(1 for t in tasks.values() if t["status"] == "completed")
        current = next((t["title"] for t in tasks.values() if t["status"] == "in_progress"), "")
        if not current:
            current = next((t["title"] for t in tasks.values() if t["status"] != "completed"), "")
        return {"done": done, "total": len(tasks), "current": short(current, 60)}

    def handle(self, event, payload, agent="claude"):
        """Events that need no decision. Always returns the empty response."""
        with self._lock:
            if event == "SessionEnd":
                sid = f"{agent}:{payload.get('session_id') or 'default'}"
                self._cancel_pending_for(sid)
                ended = self._sessions.pop(sid, None)
                if ended:
                    self._record(ended)
                return
            s = self._session(payload, agent)
            tool = payload.get("tool_name", "")
            if event == "SessionStart":
                if payload.get("source") in ("startup", "clear", None):
                    s.update(status="idle", icon="", action="", _tasks={}, tasks=None)
                if payload.get("model"):
                    s["model"] = str(payload["model"])
                self._record(s)
            elif event == "UserPromptSubmit":
                self._cancel_pending_for(s["sid"])
                s.update(status="working", icon="✦", action=Msg("action.thinking"))
                self._record(s)
            elif event == "PreToolUse":
                icon, text, _ = describe(tool, payload.get("tool_input"))
                s.update(status="working", icon=icon, action=text)
                inp = payload.get("tool_input") or {}
                todos = inp.get("todos") if tool == "TodoWrite" else inp.get("plan") if tool == "update_plan" else None
                if isinstance(todos, list):
                    s["_tasks"] = {
                        str(i): {"title": t.get("activeForm") or t.get("content") or t.get("step") or "",
                                 "status": t.get("status", "pending")}
                        for i, t in enumerate(todos) if isinstance(t, dict)}
                    s["tasks"] = self._task_summary(s)
            elif event == "PostToolUse":
                # the tool ran: an open permission for it was answered elsewhere (terminal)
                for p in self._pending.values():
                    if p["sid"] == s["sid"] and p["result"] is None and p["tool"] == tool:
                        p["result"] = "cancelled"
                        p["event"].set()
                if s["status"] in ("permission", "waiting"):
                    s.update(status="working", icon="✦", action=Msg("action.working"))
            elif event == "PostToolUseFailure":
                _, text, _ = describe(tool, payload.get("tool_input"))
                s.update(status="working", icon="⚠️", action=Msg("action.error", action=text))
            elif event in ("TaskCreated", "TaskCompleted"):
                tid = str(payload.get("task_id") or len(s["_tasks"]))
                task = s["_tasks"].setdefault(tid, {"title": payload.get("task_subject", ""), "status": "pending"})
                if event == "TaskCompleted":
                    task["status"] = "completed"
                s["tasks"] = self._task_summary(s)
            elif event == "Notification":
                ntype = payload.get("notification_type", "")
                has_pending = any(p["sid"] == s["sid"] for p in self._pending.values())
                if ntype == "permission_prompt" and has_pending:
                    return
                if ntype == "permission_prompt" and agent in ACTIVITY_ONLY:   # Skerry cannot answer it
                    s.update(status="waiting", icon="⏳", action=Msg("action.terminal_permission"))
                    return
                if ntype in ("idle_prompt", "permission_prompt", "elicitation_dialog", "agent_needs_input"):
                    msg = payload.get("message")
                    s.update(status="waiting", icon="⏳", action=short(msg, 70) if msg else Msg("action.waiting"))
            elif event == "Stop":
                self._cancel_pending_for(s["sid"])
                s.update(status="done", icon="✓", action=Msg("action.done"), done_at=time.time(),
                         done_msg=short(payload.get("last_assistant_message", ""), 180))
                self._record(s)
                self._on_event("done")
            elif event == "StopFailure":
                err = payload.get("error")
                s.update(status="error", icon="✕", done_at=time.time(),
                         action=short(err, 70) if err else Msg("action.failed"))
                self._record(s)

    @staticmethod
    def _record(s):
        """A line in the local session history (Settings > History)."""
        history.record(s["agent"], s["sid"].split(":", 1)[1], s["project"], s["cost"])

    def statusline(self, data):
        with self._lock:
            s = self._session(data, "claude")
            s["model"] = (data.get("model") or {}).get("display_name", "") or s["model"]
            pct = (data.get("context_window") or {}).get("used_percentage")
            s["context_pct"] = pct
            s["cost"] = (data.get("cost") or {}).get("total_cost_usd")
            th = self._settings.get("alerts.context", 80)
            key = ("ctx", s["sid"])
            if pct is not None and th and pct >= th and key not in self._fired:
                self._fired.add(key)
                self._alert("warn", "🧠", Msg("alert.context", project=s["project"] or Msg("alert.session"),
                                             pct=f"{pct:.0f}"))
            elif pct is not None and pct < th * 0.6:
                self._fired.discard(key)
            rl = data.get("rate_limits")
            if not self._sl["seen"]:
                log.info("Status line received from Claude Code (rate_limits %s)",
                         "present" if rl else "missing: needs a Pro/Max plan")
            self._sl.update(seen=True, at=time.time(), limits=bool(rl))
            if rl:
                self._limits = {**rl, "received_at": time.time()}
                self._check_limits(rl)

    def _check_limits(self, rl):
        names = {"five_hour": "limit.five_hour", "seven_day": "limit.seven_day", "spend_limit": "limit.spend"}
        for win, label in names.items():
            w = rl.get(win) or {}
            pct = w.get("used_percentage")
            if pct is None:
                continue
            crossed = [t for t in sorted(self._settings.get("alerts.limits", [80, 90])) if pct >= t]
            if not crossed:
                continue
            key = ("lim", win, crossed[-1], w.get("resets_at"))
            if key in self._fired:
                continue
            for th in crossed:
                self._fired.add(("lim", win, th, w.get("resets_at")))
            level = "danger" if crossed[-1] >= 90 else "warn"
            if w.get("resets_at"):
                left = max(0, w["resets_at"] - time.time())
                text = Msg("alert.limit_reset", label=Msg(label), pct=f"{pct:.0f}",
                           h=int(left // 3600), m=int(left % 3600 // 60))
            else:
                text = Msg("alert.limit", label=Msg(label), pct=f"{pct:.0f}")
            self._alert(level, "⏱", text)

    def _live_limits(self):
        """Known limits without windows that already reset (Claude Code drops them only on the next message)."""
        if not self._limits:
            return None
        now = time.time()
        out = {k: v for k, v in self._limits.items()
               if not (isinstance(v, dict) and v.get("resets_at") and v["resets_at"] < now)}
        return out if any(isinstance(v, dict) for v in out.values()) else None

    # ---------------- alerts ----------------
    def _alert(self, level, icon, text, sound=True):
        self._alerts.append({"id": next(self._ids), "level": level, "icon": icon, "text": text, "at": time.time()})
        self._alerts = self._alerts[-10:]
        if sound:
            self._on_event("alert")

    def alert(self, level, icon, text, sound=True):
        with self._lock:
            self._alert(level, icon, text, sound)

    def dismiss_alert(self, aid):
        with self._lock:
            self._alerts = [a for a in self._alerts if a["id"] != aid]

    # ---------------- permissions ----------------
    def request_permission(self, payload, wait, agent="claude"):
        tool = payload.get("tool_name", "")
        icon, text, detail = describe(tool, payload.get("tool_input"))
        pid = uuid.uuid4().hex[:12]
        suggestions = payload.get("permission_suggestions") or []
        cwd = str(payload.get("cwd") or "")
        safe = not risky(tool, payload.get("tool_input"), cwd)
        with self._lock:
            s = self._session(payload, agent)
            if safe and self._grant_for(agent, cwd, tool):
                log.info("Permission auto-approved by a timed rule (%s) %s: %s", agent, tool, text)
                return {"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": {"behavior": "allow"}}}
            s.update(status="permission", icon=icon, action=text)
            entry = {"id": pid, "sid": s["sid"], "agent": agent, "project": s["project"], "tool": tool,
                     "icon": icon, "text": text, "detail": short(detail, 400), "created": time.time(),
                     "can_always": bool(suggestions), "_suggestions": suggestions,
                     "can_grant": safe, "_cwd": cwd,
                     "event": threading.Event(), "result": None}
            self._pending[pid] = entry
        self._on_event("permission")
        log.info("Permission requested (%s) %s: %s", agent, tool, text)

        entry["event"].wait(wait)

        with self._lock:
            self._pending.pop(pid, None)
            if s["status"] == "permission":
                s["status"] = "working"
        result = entry["result"]
        log.info("Permission %s -> %s", pid, result or "timeout")
        out = {"hookEventName": "PermissionRequest"}
        if result == "allow":
            out["decision"] = {"behavior": "allow"}
        elif result == "always":
            out["decision"] = {"behavior": "allow", "updatedPermissions": suggestions}
        elif result == "deny":
            out["decision"] = {"behavior": "deny", "message": t("perm.denied")}
        else:
            return {}  # terminal, timeout or cancelled: the agent shows its normal prompt
        return {"hookSpecificOutput": out}

    @staticmethod
    def _rule_key(agent, cwd, tool):
        return agent, os.path.normcase(os.path.normpath(cwd)), tool

    def _grant_for(self, agent, cwd, tool):
        now = time.time()
        self._grants = [g for g in self._grants if g["until"] > now]
        key = self._rule_key(agent, cwd, tool)
        return next((g for g in self._grants if g["_key"] == key), None)

    def decide(self, pid, behavior):
        """behavior: allow | always | deny | terminal | grant:<minutes> (allow + a timed rule)."""
        with self._lock:
            p = self._pending.get(pid)
            if p and p["result"] is None:
                if behavior.startswith("grant:"):
                    if not p["can_grant"]:
                        return False
                    minutes = int(behavior.split(":")[1])
                    key = self._rule_key(p["agent"], p["_cwd"], p["tool"])
                    self._grants = [g for g in self._grants if g["_key"] != key]
                    self._grants.append({"id": next(self._ids), "agent": p["agent"], "project": p["project"],
                                         "tool": p["tool"], "until": time.time() + 60 * minutes, "_key": key})
                    log.info("Timed rule: %s %s in %s for %d min", p["agent"], p["tool"], p["project"], minutes)
                    for q in self._pending.values():  # identical requests already waiting
                        same = self._rule_key(q["agent"], q["_cwd"], q["tool"]) == key
                        if q["result"] is None and q["can_grant"] and same:
                            q["result"] = "allow"
                            q["event"].set()
                    behavior = "allow"
                p["result"] = behavior
                p["event"].set()
                return self._sessions.get(p["sid"], {}).get("hwnd", 0) or True
        return False

    def revoke_grant(self, gid):
        with self._lock:
            self._grants = [g for g in self._grants if g["id"] != gid]
            log.info("Timed rule %s revoked", gid)

    # ---------------- selection / UI ----------------
    def _active(self):
        return [s for s in sorted(self._sessions.values(), key=lambda x: x["updated"], reverse=True)
                if s["status"] in ("working", "waiting", "permission")]

    def cycle(self, direction):
        with self._lock:
            act = self._active()
            if len(act) < 2:
                return
            ids = [s["sid"] for s in act]
            i = ids.index(self._selected) if self._selected in ids else 0
            self._selected = ids[(i + (1 if direction > 0 else -1)) % len(ids)]

    def session_hwnd(self, sid):
        with self._lock:
            return self._sessions.get(sid, {}).get("hwnd", 0)

    def ui_toggle(self):
        with self._lock:
            self._ui_seq += 1

    def has_pending(self):
        with self._lock:
            return any(p["result"] is None for p in self._pending.values())

    def snapshot(self, stale_after=600):
        now = time.time()
        with self._lock:
            sessions = []
            for s in self._sessions.values():
                if not self._settings.get(f"modules.{s['agent']}", True):
                    continue
                d = {k: v for k, v in s.items() if not k.startswith("_")}
                if d["status"] in ("working", "waiting") and now - d["updated"] > stale_after:
                    d["status"] = "idle"
                d["has_window"] = bool(d.pop("hwnd"))
                d["action"] = render(d["action"])
                sessions.append(d)
            sessions.sort(key=lambda x: x["updated"], reverse=True)
            pending = [{**{k: v for k, v in p.items() if k not in ("event", "result") and not k.startswith("_")},
                        "text": render(p["text"])}
                       for p in self._pending.values() if p["result"] is None]
            alerts = [{**a, "text": render(a["text"])} for a in self._alerts if now - a["at"] < 7]
            grants = [{k: v for k, v in g.items() if not k.startswith("_")} for g in self._grants if g["until"] > now]
            return {"now": now, "sessions": sessions, "pending": pending, "alerts": alerts, "grants": grants,
                    "limits": self._live_limits(), "statusline": dict(self._sl), "selected": self._selected, "ui_seq": self._ui_seq}
