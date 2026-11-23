"""Microsoft 365: next Outlook/Teams calendar meeting (Microsoft Graph, read-only).

Delegated sign-in with MSAL (system browser, no stored password, tokens encrypted with DPAPI).
Needs an app registration in Microsoft Entra ID granted only the delegated permissions
User.Read and Calendars.Read. Instructions are in the settings page and the README.
"""
import json
import logging
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from .. import secrets
from ..i18n import Msg, render

log = logging.getLogger("skerry")

SCOPES = ["User.Read", "Calendars.Read"]
GRAPH = "https://graph.microsoft.com/v1.0"
CACHE_NAME = "m365-token-cache"
POLL = 120                      # seconds between two calendar reads
SELECT = "id,subject,start,end,isAllDay,isCancelled,showAs,isOnlineMeeting,onlineMeeting,onlineMeetingProvider,location,responseStatus"


def _parse(dt):
    """'2026-11-22T19:00:00.0000000' (UTC, because of the Prefer header) -> timestamp."""
    s = (dt or {}).get("dateTime") or ""
    s = re.sub(r"(\.\d{6})\d+", r"\1", s)
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        return None
    return (d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d).timestamp()


def pick_meeting(events, now):
    """Pick the meeting in progress or the next one: skip cancelled, all-day, declined and finished events."""
    best = None
    for e in events or []:
        if e.get("isCancelled") or e.get("isAllDay"):
            continue
        if ((e.get("responseStatus") or {}).get("response") or "") == "declined":
            continue
        start, end = _parse(e.get("start")), _parse(e.get("end"))
        if start is None or end is None or end <= now:
            continue
        if best is None or start < best["start"]:
            om = e.get("onlineMeeting") or {}
            loc = ((e.get("location") or {}).get("displayName") or "").strip()
            url = om.get("joinUrl") or (loc if re.match(r"https://\S+$", loc) else "")
            prov = {"teamsForBusiness": "Teams", "skypeForBusiness": "Skype", "skypeForConsumer": "Skype"}.get(
                e.get("onlineMeetingProvider") or "", "")
            best = {"id": e.get("id") or "", "title": e.get("subject") or "", "start": start, "end": end,
                    "join_url": url, "provider": prov or ("Online" if url else ""),
                    "location": "" if url else loc, "show_as": e.get("showAs") or ""}
    if best:
        best["in_progress"] = best["start"] <= now < best["end"]
    return best


class M365:
    def __init__(self, settings, store):
        self._settings = settings
        self._store = store
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = False
        self._status = "signed_out"
        self._error = ""
        self._account = ""
        self._meeting = None
        self._updated = 0
        self._alerted = set()
        self._app = None
        self._cache = None
        self._cfg_key = None
        self._thread = None
        self._login_thread = None

    # ---------- configuration ----------
    def cfg(self):
        c = self._settings.get("connectors.m365", {}) or {}
        return {"client_id": (c.get("client_id") or "").strip(), "tenant": (c.get("tenant") or "organizations").strip(),
                "alert_minutes": int(c.get("alert_minutes", 5) or 0)}

    def _msal(self):
        """MSAL app (recreated when client id or tenant change)."""
        import msal
        c = self.cfg()
        key = (c["client_id"], c["tenant"])
        if self._app is None or key != self._cfg_key:
            self._cache = msal.SerializableTokenCache()
            blob = secrets.load(CACHE_NAME)
            if blob:
                try:
                    self._cache.deserialize(blob)
                except Exception:
                    log.warning("Invalid Microsoft 365 token cache: ignored")
            self._app = msal.PublicClientApplication(
                c["client_id"], authority=f"https://login.microsoftonline.com/{c['tenant']}", token_cache=self._cache)
            self._cfg_key = key
        return self._app

    def _persist(self):
        if self._cache is not None and self._cache.has_state_changed:
            secrets.save(CACHE_NAME, self._cache.serialize())

    def _token(self):
        app = self._msal()
        accounts = app.get_accounts()
        if not accounts:
            return None
        res = app.acquire_token_silent(SCOPES, account=accounts[0])
        self._persist()
        if not res or "access_token" not in res:
            return None
        self._account = accounts[0].get("username", "")
        return res["access_token"]

    # ---------- state ----------
    def status(self):
        with self._lock:
            c = self.cfg()
            return {"configured": bool(c["client_id"]), "status": self._status, "account": self._account,
                    "error": render(self._error), "updated": self._updated, "has_meeting": bool(self._meeting)}

    def meeting(self):
        with self._lock:
            m = self._meeting
            if not m:
                return None
            now = time.time()
            if m["end"] <= now:
                return None
            return {**m, "in_progress": m["start"] <= now < m["end"]}

    def _set(self, status, error=""):
        with self._lock:
            self._status, self._error = status, error

    # ---------- sign-in ----------
    def login(self):
        c = self.cfg()
        if not c["client_id"]:
            self._set("error", Msg("m365.need_client_id"))
            return False
        if self._login_thread and self._login_thread.is_alive():
            return True
        self._set("signing_in")
        self._login_thread = threading.Thread(target=self._login, daemon=True, name="m365-login")
        self._login_thread.start()
        return True

    def _login(self):
        try:
            res = self._msal().acquire_token_interactive(SCOPES, prompt="select_account", timeout=240)
        except ImportError:
            self._set("error", Msg("m365.need_msal"))
            return
        except Exception as e:
            log.exception("Microsoft 365 sign-in")
            self._set("error", str(e)[:200])
            return
        self._persist()
        if res and "access_token" in res:
            with self._lock:
                self._account = (res.get("id_token_claims") or {}).get("preferred_username", "")
            log.info("Microsoft 365: signed in (%s)", self._account or "account")
            self._set("ok")
            self._wake.set()
        else:
            err = (res or {}).get("error_description") or (res or {}).get("error")
            log.warning("Microsoft 365: sign-in failed: %s", str(err or "cancelled").splitlines()[0][:200])
            self._set("error", str(err).splitlines()[0][:200] if err else Msg("m365.cancelled"))

    def logout(self):
        try:
            app = self._msal() if self.cfg()["client_id"] else None
            for a in (app.get_accounts() if app else []):
                app.remove_account(a)
        except Exception:
            log.debug("logout m365", exc_info=True)
        secrets.delete(CACHE_NAME)
        self._app = self._cache = self._cfg_key = None
        with self._lock:
            self._status, self._error, self._account, self._meeting = "signed_out", "", "", None
        log.info("Microsoft 365: signed out")

    def refresh(self):
        self._wake.set()

    # ---------- polling ----------
    def start(self):
        self._thread = threading.Thread(target=self._loop, daemon=True, name="m365")
        self._thread.start()

    def stop(self):
        self._stop = True
        self._wake.set()

    def _get(self, token, url):
        req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token, "Accept": "application/json",
                                                   "Prefer": 'outlook.timezone="UTC"'})
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r)

    def fetch(self):
        token = self._token()
        if not token:
            self._set("signed_out" if self._status != "signing_in" else "signing_in")
            return None
        now = datetime.now(timezone.utc)
        q = urllib.parse.urlencode({"startDateTime": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                    "endDateTime": (now + timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                    "$orderby": "start/dateTime", "$top": "15", "$select": SELECT})
        return self._get(token, f"{GRAPH}/me/calendarView?{q}").get("value", [])

    def _poll(self):
        try:
            events = self.fetch()
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = json.load(e).get("error", {}).get("message", "")
            except Exception:
                pass
            self._set("error", Msg("m365.graph_error", code=e.code, message=body[:140]))
            log.warning("Microsoft Graph HTTP %s %s", e.code, body[:200])
            return
        except ImportError:
            self._set("error", Msg("m365.need_msal"))
            return
        except Exception as e:
            self._set("error", Msg("m365.network") if isinstance(e, (urllib.error.URLError, OSError)) else str(e)[:160])
            log.debug("poll m365", exc_info=True)
            return
        if events is None:
            return
        m = pick_meeting(events, time.time())
        with self._lock:
            self._meeting, self._updated = m, time.time()
            if self._status != "signing_in":
                self._status, self._error = "ok", ""

    def _check_alert(self):
        m = self.meeting()
        n = self.cfg()["alert_minutes"]
        if not m or not n or m["in_progress"]:
            return
        left = m["start"] - time.time()
        key = (m["id"], m["start"])
        if 0 < left <= n * 60 and key not in self._alerted:
            self._alerted.add(key)
            self._alerted = set(list(self._alerted)[-20:])
            mins = max(1, round(left / 60))
            self._store.alert("info", "📅", Msg("alert.meeting_soon", title=m["title"] or Msg("meeting.untitled"), n=mins),
                              sound=True)

    def _loop(self):
        time.sleep(4)
        nxt = 0
        while not self._stop:
            try:
                c = self.cfg()
                if c["client_id"] and (self._status != "signing_in") and time.time() >= nxt:
                    self._poll()
                    nxt = time.time() + POLL
                self._check_alert()
            except Exception:
                log.exception("m365 loop")
            if self._wake.wait(15):
                self._wake.clear()
                nxt = 0
