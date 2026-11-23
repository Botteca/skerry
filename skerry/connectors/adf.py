"""Azure Data Factory: the latest run of the chosen pipelines, and an alert when one fails.

Read-only: Azure Resource Manager `queryPipelineRuns` (api-version 2018-06-01). Sign-in with the Azure CLI
(`az login`) or a service principal (see connectors/azure.py). Polled every 5 minutes in a background thread:
errors only change the status shown in settings, they never block the island.
"""
import json
import logging
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from .. import secrets
from ..i18n import Msg, render
from . import azure

log = logging.getLogger("skerry")

ARM = "https://management.azure.com"   # replaced by a fake server in tests
RESOURCE = "https://management.azure.com/"
API = "2018-06-01"
SECRET = "adf-client-secret"
POLL = 300
TIMEOUT = 20                           # seconds for every Azure call
LOOKBACK_DAYS = 7


def _iso(value):
    """ADF times ('2026-03-10T02:00:03.1234567Z') -> timestamp. Fractions beyond microseconds are dropped."""
    s = str(value or "")
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    head, _, tz = s.partition("+")
    if "." in head:
        main, frac = head.split(".", 1)
        head = f"{main}.{frac[:6]}"
    try:
        d = datetime.fromisoformat(head + ("+" + tz if tz else ""))
    except ValueError:
        return None
    return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).timestamp()


def latest_runs(runs, pipelines):
    """One entry per chosen pipeline, in the chosen order: its most recent run, or status "none"."""
    best = {}
    for r in runs or []:
        name = r.get("pipelineName")
        start = _iso(r.get("runStart")) or 0
        if name in pipelines and (name not in best or start > best[name]["start"]):
            best[name] = {"pipeline": name, "status": r.get("status") or "", "run_id": r.get("runId") or "",
                          "start": start, "end": _iso(r.get("runEnd")),
                          "message": " ".join(str(r.get("message") or "").split())[:200]}
    return [best.get(p) or {"pipeline": p, "status": "none", "run_id": "", "start": None, "end": None, "message": ""}
            for p in pipelines]


class ADF:
    def __init__(self, settings, store):
        self._settings = settings
        self._store = store
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = False
        self._status, self._error, self._updated = "off", "", 0
        self._runs = None
        self._alerted = set()
        self._since = time.time()   # failures that ended before Skerry started are not announced

    # ---------- configuration ----------
    def cfg(self):
        c = self._settings.get("connectors.adf", {}) or {}
        pipes = [p.strip() for p in str(c.get("pipelines") or "").split(",") if p.strip()]
        return {"enabled": bool(c.get("enabled")), "auth": "sp" if c.get("auth") == "sp" else "az",
                "tenant": str(c.get("tenant") or "").strip(), "client_id": str(c.get("client_id") or "").strip(),
                "subscription": str(c.get("subscription") or "").strip(),
                "resource_group": str(c.get("resource_group") or "").strip(),
                "factory": str(c.get("factory") or "").strip(), "pipelines": pipes[:20]}

    def _ready(self, c):
        return c["enabled"] and c["subscription"] and c["resource_group"] and c["factory"] and c["pipelines"]

    def status(self):
        with self._lock:
            return {"configured": bool(self._ready(self.cfg())), "status": self._status, "error": render(self._error),
                    "updated": self._updated, "has_secret": secrets.load(SECRET) is not None}

    def runs(self):
        """What the island shows: latest run per pipeline, or None when off or not loaded yet."""
        with self._lock:
            return [dict(r) for r in self._runs] if self._runs and self._ready(self.cfg()) else None

    def set_secret(self, value):
        if value:
            secrets.save(SECRET, value)
        else:
            secrets.delete(SECRET)
        azure.forget()
        self.refresh()

    def _set(self, status, error=""):
        with self._lock:
            self._status, self._error = status, error

    def refresh(self):
        self._wake.set()

    # ---------- polling ----------
    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="adf").start()

    def stop(self):
        self._stop = True
        self._wake.set()

    def fetch(self, c):
        tok = azure.token(c["auth"], RESOURCE, c["tenant"], c["client_id"], SECRET)
        q = lambda s: urllib.parse.quote(s, safe="")
        url = (f"{ARM}/subscriptions/{q(c['subscription'])}/resourceGroups/{q(c['resource_group'])}"
               f"/providers/Microsoft.DataFactory/factories/{q(c['factory'])}/queryPipelineRuns?api-version={API}")
        now = datetime.now(timezone.utc)
        body = {"lastUpdatedAfter": (now - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "lastUpdatedBefore": (now + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "filters": [{"operand": "PipelineName", "operator": "In", "values": c["pipelines"]}],
                "orderBy": [{"orderBy": "RunStart", "order": "DESC"}]}
        runs = []
        for _page in range(5):
            req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                         headers={"Authorization": "Bearer " + tok, "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                d = json.load(r)
            runs += d.get("value") or []
            if not d.get("continuationToken"):
                break
            body["continuationToken"] = d["continuationToken"]
        return latest_runs(runs, c["pipelines"])

    def _poll(self, c):
        try:
            latest = self.fetch(c)
        except azure.AzureError as e:
            self._set("error", e.msg)
            log.warning("Data Factory: %s", e)
            return
        except urllib.error.HTTPError as e:
            self._set("error", Msg("azure.http_error", code=e.code, message=azure.http_error(e)))
            log.warning("Data Factory HTTP %s", e.code)
            return
        except (urllib.error.URLError, OSError):
            self._set("error", Msg("azure.network"))
            log.debug("poll adf", exc_info=True)
            return
        except Exception as e:
            self._set("error", str(e)[:160])
            log.exception("poll adf")
            return
        with self._lock:
            self._runs, self._updated = latest, time.time()
            self._status, self._error = "ok", ""
        for r in latest:
            if r["status"] == "Failed" and r["run_id"] not in self._alerted and (r["end"] or r["start"]) >= self._since:
                self._alerted.add(r["run_id"])
                self._store.alert("danger", "🏭", Msg("alert.adf_failed", pipeline=r["pipeline"]))
                log.info("Data Factory: pipeline %s failed", r["pipeline"])

    def _loop(self):
        time.sleep(5)
        nxt = 0
        while not self._stop:
            try:
                c = self.cfg()
                if not self._ready(c):
                    with self._lock:
                        self._runs = None
                    self._set("off")
                elif time.time() >= nxt:
                    self._poll(c)
                    nxt = time.time() + POLL
            except Exception:
                log.exception("adf loop")
            if self._wake.wait(15):
                self._wake.clear()
                nxt = 0
