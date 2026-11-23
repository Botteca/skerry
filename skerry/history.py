"""Session history for Settings > History: the last 30 days, from local files only. Nothing leaves the PC.

Sources:
- history.jsonl in Skerry's data folder: a line per session event (start, prompt, end) written by the Store for
  every agent. It gives project and duration for all agents, and the cost Claude Code reports in its status line.
- Claude Code session files (~/.claude/projects/**/*.jsonl): tokens and model per session.
Codex, Gemini CLI and Copilot CLI keep their own logs in undocumented formats, so their tokens stay unknown.
"""
import csv
import io
import json
import logging
import os
import threading
import time

from . import paths
from .usage import _projects_dir, _ts

log = logging.getLogger("skerry")

DAYS = 30
TOKENS = ("input", "output", "cache_write", "cache_read")
_lock = threading.Lock()


def _file():
    return os.path.join(paths.data_dir(), "history.jsonl")


def record(agent, sid, project, cost=None):
    line = json.dumps({"t": round(time.time(), 1), "agent": agent, "sid": sid, "project": project, "cost": cost},
                      ensure_ascii=False)
    try:
        with _lock, open(_file(), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        log.exception("Could not write the session history")


def _new(agent, sid):
    return {"agent": agent, "sid": sid, "project": "", "start": None, "end": None, "model": "",
            **{k: None for k in TOKENS}, "cost": None}


def _touch(s, ts):
    s["start"] = ts if s["start"] is None else min(s["start"], ts)
    s["end"] = ts if s["end"] is None else max(s["end"], ts)


def _own(since, out):
    """Skerry's own records; lines older than 30 days are dropped from the file."""
    with _lock:
        try:
            with open(_file(), encoding="utf-8") as f:
                lines = f.read().splitlines()
        except FileNotFoundError:
            return
        keep = []
        for line in lines:
            try:
                r = json.loads(line)
                if r["t"] < since:
                    continue
                s = out.setdefault((r["agent"], r["sid"]), _new(r["agent"], r["sid"]))
            except (ValueError, KeyError, TypeError):
                continue
            keep.append(line)
            _touch(s, r["t"])
            s["project"] = r.get("project") or s["project"]
            if r.get("cost") is not None:
                s["cost"] = r["cost"]
        if len(keep) < len(lines):
            with open(_file(), "w", encoding="utf-8") as f:
                f.write("".join(line + "\n" for line in keep))


def _claude(since, out, root=None):
    seen = set()
    for dirpath, _dirs, names in os.walk(root or _projects_dir()):
        for n in names:
            p = os.path.join(dirpath, n)
            try:
                if not n.endswith(".jsonl") or os.stat(p).st_mtime < since:
                    continue
                fh = open(p, "rb")
            except OSError:
                continue
            with fh:
                for line in fh:
                    if b'"usage"' not in line:
                        continue
                    try:
                        d = json.loads(line)
                        msg = d["message"]
                        u = msg["usage"]
                        sid = d["sessionId"]
                    except (ValueError, KeyError, TypeError):
                        continue
                    ts = _ts(d.get("timestamp"))
                    if ts is None or ts < since or not isinstance(u, dict):
                        continue
                    key = (msg.get("id"), d.get("requestId"))
                    if msg.get("id"):                    # one response can appear in several files (resumed sessions)
                        if key in seen:
                            continue
                        seen.add(key)
                    s = out.setdefault(("claude", sid), _new("claude", sid))
                    _touch(s, ts)
                    if d.get("cwd") and not s["project"]:
                        s["project"] = os.path.basename(os.path.normpath(str(d["cwd"])))
                    if msg.get("model") and not str(msg["model"]).startswith("<"):
                        s["model"] = msg["model"]
                    for k, field in zip(TOKENS, ("input_tokens", "output_tokens", "cache_creation_input_tokens",
                                                 "cache_read_input_tokens")):
                        s[k] = (s[k] or 0) + int(u.get(field) or 0)


def sessions(now=None, claude_root=None):
    """Sessions of the last 30 days, newest first. Duration = first to last recorded activity."""
    since = (now or time.time()) - DAYS * 86400
    out = {}
    _own(since, out)
    _claude(since, out, claude_root)
    rows = [{**s, "duration": s["end"] - s["start"]} for s in out.values() if s["start"] is not None]
    return sorted(rows, key=lambda s: s["end"], reverse=True)


CSV_FIELDS = ("agent", "project", "session", "start", "end", "duration_min", "model", "input_tokens",
              "output_tokens", "cache_write_tokens", "cache_read_tokens", "cost_usd")


def _cell(v):
    if v is None:
        return ""
    v = str(v)
    return "'" + v if v[:1] in ("=", "+", "-", "@") else v   # a spreadsheet must not run it as a formula


def to_csv(rows):
    when = lambda ts: time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(CSV_FIELDS)
    for s in rows:
        w.writerow([_cell(v) for v in (s["agent"], s["project"], s["sid"], when(s["start"]), when(s["end"]),
                                       round(s["duration"] / 60, 1), s["model"], *(s[k] for k in TOKENS),
                                       None if s["cost"] is None else round(s["cost"], 4))])
    return buf.getvalue()
