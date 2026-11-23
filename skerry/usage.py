"""Local Claude Code usage: tokens in the last 5 hours and 7 days, read from the sessions saved in
~/.claude/projects/**/*.jsonl. No credentials, no network: local files only.

This is not the plan-limit percentage (not exposed on Team plans) but the actual consumption rate.
"""
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone

log = logging.getLogger("skerry")

H5, D7 = 5 * 3600, 7 * 86400
REFRESH = 60


def _projects_dir():
    base = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    return os.path.join(base, "projects")


def _ts(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc).timestamp()
    except Exception:
        return None


class LocalUsage:
    def __init__(self, settings=None, root=None):
        self._settings = settings
        self._root = root or _projects_dir()
        self._files = {}   # path -> {"offset", "size", "recs": {key: (ts, in, out, cache_w, cache_r)}}
        self._state = None
        self._lock = threading.Lock()

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="usage").start()

    def state(self):
        with self._lock:
            return self._state

    def _enabled(self):
        return self._settings is None or self._settings.get("modules.usage", True)

    def _loop(self):
        time.sleep(3)
        while True:
            try:
                if self._enabled():
                    self.refresh()
            except Exception:
                log.exception("Could not read local usage")
            time.sleep(REFRESH)

    # ---------------- incremental read ----------------
    def _scan(self, now):
        seen = set()
        for dirpath, _dirs, names in os.walk(self._root):
            for n in names:
                if not n.endswith(".jsonl"):
                    continue
                p = os.path.join(dirpath, n)
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                if now - st.st_mtime > D7 + 3600:
                    continue                      # untouched for more than 7 days: irrelevant
                seen.add(p)
                self._read(p, st.st_size)
        for p in list(self._files):
            if p not in seen:
                del self._files[p]

    def _read(self, path, size):
        f = self._files.setdefault(path, {"offset": 0, "size": 0, "recs": {}})
        if size < f["offset"]:                    # file rewritten: start over
            f.update(offset=0, recs={})
        if size == f["offset"]:
            return
        try:
            with open(path, "rb") as fh:
                fh.seek(f["offset"])
                chunk = fh.read(size - f["offset"])
        except OSError:
            return
        end = chunk.rfind(b"\n")
        if end < 0:
            return                                 # line still incomplete
        f["offset"] += end + 1
        for line in chunk[:end].split(b"\n"):
            if b'"usage"' not in line:
                continue
            try:
                d = json.loads(line)
            except ValueError:
                continue
            msg = d.get("message") if isinstance(d, dict) else None
            u = msg.get("usage") if isinstance(msg, dict) else None
            ts = _ts(d.get("timestamp"))
            if not isinstance(u, dict) or ts is None:
                continue
            key = (msg.get("id"), d.get("requestId")) if msg.get("id") else (path, f["offset"], ts)
            f["recs"][key] = (ts, int(u.get("input_tokens") or 0), int(u.get("output_tokens") or 0),
                              int(u.get("cache_creation_input_tokens") or 0), int(u.get("cache_read_input_tokens") or 0))

    # ---------------- aggregation ----------------
    def refresh(self, now=None):
        now = now or time.time()
        self._scan(now)
        merged = {}
        for f in self._files.values():           # one response can appear in several files (resumed sessions)
            merged.update(f["recs"])
        win = {"h5": [0, 0, 0, 0, 0], "d7": [0, 0, 0, 0, 0]}
        days = [0] * 7
        last = 0
        for ts, i, o, cw, cr in merged.values():
            age = now - ts
            if age < 0 or age > D7:
                continue
            last = max(last, ts)
            work = i + o + cw
            days[min(6, int(age // 86400))] += work
            for k, lim in (("h5", H5), ("d7", D7)):
                if age <= lim:
                    w = win[k]
                    w[0] += 1; w[1] += i; w[2] += o; w[3] += cw; w[4] += cr
        pack = lambda w: {"requests": w[0], "input": w[1], "output": w[2], "cache_write": w[3], "cache_read": w[4],
                          "tokens": w[1] + w[2] + w[3]}
        st = {"h5": pack(win["h5"]), "d7": pack(win["d7"]), "days": days[::-1], "last": last or None, "at": now}
        with self._lock:
            self._state = st
        return st
