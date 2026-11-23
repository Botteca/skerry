"""Diagnostics report for bug reports ("Copy diagnostics" in Settings > About and logs).

Collects version, Windows, DPI, monitors, enabled modules, connector/agent/update status and the last log lines,
then hides personal data: user profile paths and the user name, Bluetooth device names and addresses, email
addresses. Nothing is sent anywhere: the text only goes to the clipboard.
"""
import json
import logging
import os
import platform
import re
import sys
from collections import deque

from . import VERSION, i18n, paths

log = logging.getLogger("skerry")
LOG_LINES = 80

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
# C:\Users\<name>\..., C:/Users/<name>/..., C:\\Users\\<name>\\... (JSON-escaped)
USER_PATH_RE = re.compile(r"(?i)([A-Z]:(?:\\\\|\\|/)Users(?:\\\\|\\|/))([^\\/\s\"'<>|:*?]+)")
MAC_RE = re.compile(r"(?<![0-9A-Fa-f])[0-9A-Fa-f]{12}(?![0-9A-Fa-f])")
BT_NAME_RE = re.compile(r"('name':\s*')[^']*(')")
BT_DETAIL_RE = re.compile(r"\(\s*'[^']*',\s*(?:'[0-9A-Fa-f]{12}'|None)")


def redact(text, user_names=(), device_names=()):
    """Hide personal data in `text`. Pure function (no system calls), used on the whole report."""
    out = EMAIL_RE.sub("<email>", str(text))
    for name in sorted({n for n in user_names if n and len(n) >= 3}, key=len, reverse=True):  # known names first:
        out = re.sub(rf"(?i)(?<![\w.-]){re.escape(name)}(?![\w-])", "<user>", out)           # they may contain spaces
    out = USER_PATH_RE.sub(r"\1<user>", out)
    for i, name in enumerate(sorted({n for n in device_names if n and len(n) >= 2}, key=len, reverse=True), 1):
        out = out.replace(name, f"<device {i}>")
    lines = []
    for line in out.splitlines():
        if "Bluetooth" in line:                          # the Bluetooth log line lists raw names and addresses
            line = BT_NAME_RE.sub(r"\1<device>\2", line)
            line = BT_DETAIL_RE.sub("('<device>', '<address>'", line)
            line = MAC_RE.sub("<address>", line)
        lines.append(line)
    return "\n".join(lines)


def tail(path, n=LOG_LINES):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return [line.rstrip("\n") for line in deque(f, maxlen=n)]
    except OSError as e:
        return [f"(log not readable: {e.__class__.__name__})"]


def _windows():
    info = {"platform": platform.platform(), "release": platform.release(), "version": platform.version()}
    try:
        info["edition"] = platform.win32_edition()
    except Exception:
        pass
    try:
        w = sys.getwindowsversion()
        info["build"] = f"{w.major}.{w.minor}.{w.build}"
    except Exception:
        pass
    return info


def _section(title, body):
    if isinstance(body, (dict, list)):
        body = json.dumps(body, indent=2, ensure_ascii=False, default=str)
    return f"## {title}\n{body}\n"


def build(app):
    """Full report text, already redacted."""
    from . import integrations, win32
    s = app.settings
    parts = [f"# Skerry diagnostics\nSkerry {VERSION} ({'installed' if paths.FROZEN else 'from source'}), "
             f"Python {platform.python_version()}, language {i18n.current()}\n"]

    def add(title, fn):
        try:
            parts.append(_section(title, fn()))
        except Exception as e:                           # one broken section never breaks the report
            parts.append(_section(title, f"(not available: {e.__class__.__name__}: {e})"))

    add("Windows", _windows)
    add("Display (DPI)", lambda: win32.dpi_info(app.win.handle()))
    add("Monitors", lambda: [{k: m.get(k) for k in ("device", "name", "primary", "monitor", "work", "dpi", "scale")}
                             for m in win32.monitors()])
    add("Placement", lambda: {k: s.get(k) for k in ("edge", "offset", "monitor", "monitor_id")})
    add("Modules", lambda: {k: v for k, v in (s.get("modules") or {}).items()})
    add("Settings", lambda: {k: s.get(k) for k in ("language", "theme", "updates", "hide_fullscreen",
                                                   "hide_from_capture", "permission_wait", "port", "hooks_version")})
    add("Agents", lambda: {"claude": integrations.claude_status(), "codex": integrations.codex_status()})
    add("Connectors", lambda: app.connectors.states())
    add("Updates", lambda: app.updater.public_state())
    add("System", lambda: {"battery": app.system.state.get("battery"),
                           "bluetooth_devices": len(app.system.state.get("bluetooth") or []),
                           "mic_in_use": len(app.system.state.get("mic") or []),
                           "camera_in_use": len(app.system.state.get("cam") or [])})
    log_file = os.path.join(paths.log_dir(), "skerry.log")
    parts.append(_section(f"Last {LOG_LINES} log lines", "\n".join(tail(log_file))))

    devices = set()
    for d in app.system.state.get("bluetooth") or []:
        devices.add(str(d.get("name") or ""))
    for raw, alias in (s.get("bluetooth_names") or {}).items():
        devices.update({str(raw), str(alias)})
    users = {os.environ.get("USERNAME", ""), os.path.basename(os.path.expanduser("~"))}
    return redact("\n".join(parts), user_names=users, device_names=devices)


def copy_to_clipboard(app):
    """Build the report and put it on the clipboard. Returns (ok, number of lines)."""
    from . import win32
    text = build(app)
    ok = win32.copy_text_to_clipboard(text)
    log.info("Diagnostics %s (%s lines)", "copied to the clipboard" if ok else "could not be copied",
             text.count("\n") + 1)
    return ok, text.count("\n") + 1
