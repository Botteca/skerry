"""Google Calendar: next event of the primary calendar with its Google Meet link (Calendar API, read-only).

OAuth 2.0 for desktop apps: the system browser, a one-shot loopback redirect on 127.0.0.1 and PKCE.
Scope calendar.events.readonly only. The client ID is in settings; the client secret (Google requires one even
for desktop apps) and the refresh token are encrypted in `skerry.secrets`. Polled every 2 minutes in a background
thread with timeouts: errors only change the status in settings, they never block the island.
"""
import base64
import hashlib
import html
import http.server
import json
import logging
import re
import secrets as pysecrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime, timedelta, timezone

from .. import secrets
from ..i18n import Msg, render, t
from .m365 import alert_before

log = logging.getLogger("skerry")

AUTH = "https://accounts.google.com/o/oauth2/v2/auth"     # these three are replaced by a fake server in tests
TOKEN = "https://oauth2.googleapis.com/token"
API = "https://www.googleapis.com/calendar/v3"
SCOPE = "https://www.googleapis.com/auth/calendar.events.readonly"
SECRET = "google-client-secret"
REFRESH = "google-refresh-token"
POLL = 120
TIMEOUT = 20
LOGIN_WAIT = 240
BROWSER_PAGE = "<!doctype html><meta charset='utf-8'><p style='font:16px system-ui'>%s</p>"


def _ts(value):
    """RFC 3339 ('2026-03-10T09:30:00+01:00' or '...Z') -> timestamp."""
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def meet_link(e):
    """The https link to join: Meet (hangoutLink) or the conference video entry point."""
    urls = [e.get("hangoutLink")] + [p.get("uri") for p in (e.get("conferenceData") or {}).get("entryPoints") or []
                                     if p.get("entryPointType") == "video"]
    return next((u for u in urls if isinstance(u, str) and re.match(r"https://\S+$", u)), "")


def pick_meeting(events, now):
    """Event in progress or next: skip cancelled, all-day, declined and finished ones. Same shape as Microsoft 365."""
    best = None
    for e in events or []:
        if e.get("status") == "cancelled":
            continue
        start, end = (e.get("start") or {}).get("dateTime"), (e.get("end") or {}).get("dateTime")
        if not start or not end:
            continue                                   # all-day event (date only)
        if any(a.get("self") and a.get("responseStatus") == "declined" for a in e.get("attendees") or []):
            continue
        s, en = _ts(start), _ts(end)
        if s is None or en is None or en <= now:
            continue
        if best is None or s < best["start"]:
            url = meet_link(e)
            best = {"id": "g:" + str(e.get("id") or ""), "title": e.get("summary") or "", "start": s, "end": en,
                    "join_url": url, "provider": "Meet" if "meet.google.com" in url else ("Online" if url else ""),
                    "location": "" if url else (e.get("location") or "").strip(),
                    "show_as": "free" if e.get("transparency") == "transparent" else "busy"}
    if best:
        best["in_progress"] = best["start"] <= now < best["end"]
    return best


def _pkce():
    verifier = base64.urlsafe_b64encode(pysecrets.token_bytes(48)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def _post(url, fields):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(fields).encode(),
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.load(r)


def _error(e):
    """(OAuth error code such as 'invalid_grant' or '', short message) from a Google HTTPError."""
    try:
        body = json.load(e)
    except Exception:
        return "", ""
    err = body.get("error")
    text = err.get("message") if isinstance(err, dict) else body.get("error_description") or err or ""
    return (err if isinstance(err, str) else ""), (str(text).splitlines()[0][:160] if text else "")


class Google:
    def __init__(self, settings, store):
        self._settings = settings
        self._store = store
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = False
        self._status, self._error, self._account = "signed_out", "", ""
        self._meeting, self._updated = None, 0
        self._token, self._expires = None, 0
        self._alerted = set()
        self._login_thread = None

    # ---------- configuration ----------
    def cfg(self):
        c = self._settings.get("connectors.google", {}) or {}
        return {"client_id": str(c.get("client_id") or "").strip(), "alert_minutes": int(c.get("alert_minutes", 5) or 0)}

    def status(self):
        with self._lock:
            return {"configured": bool(self.cfg()["client_id"] and secrets.load(SECRET)), "status": self._status,
                    "account": self._account, "error": render(self._error), "updated": self._updated,
                    "has_secret": secrets.load(SECRET) is not None}

    def meeting(self):
        with self._lock:
            m = self._meeting
            now = time.time()
            if not m or m["end"] <= now:
                return None
            return {**m, "in_progress": m["start"] <= now < m["end"]}

    def set_secret(self, value):
        if value:
            secrets.save(SECRET, value)
        else:
            secrets.delete(SECRET)

    def _set(self, status, error=""):
        with self._lock:
            self._status, self._error = status, error

    # ---------- sign-in (browser + loopback + PKCE) ----------
    def login(self):
        c = self.cfg()
        if not c["client_id"] or not secrets.load(SECRET):
            self._set("error", Msg("google.need_client"))
            return False
        if self._login_thread and self._login_thread.is_alive():
            return True
        self._set("signing_in")
        self._login_thread = threading.Thread(target=self._login, args=(c["client_id"],), daemon=True,
                                              name="google-login")
        self._login_thread.start()
        return True

    def _login(self, client_id):
        verifier, challenge = _pkce()
        state = pysecrets.token_urlsafe(24)
        got = {}

        class Redirect(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(self.path).query))
                if q.get("state") == state:
                    got.update(q)
                ok = "code" in got
                page = BROWSER_PAGE % html.escape(t("google.browser_ok" if ok else "google.browser_fail"))
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(page.encode("utf-8"))

            def log_message(self, *args):
                pass

        srv = http.server.HTTPServer(("127.0.0.1", 0), Redirect)
        srv.timeout = 1
        redirect = f"http://127.0.0.1:{srv.server_address[1]}"
        url = AUTH + "?" + urllib.parse.urlencode({
            "client_id": client_id, "redirect_uri": redirect, "response_type": "code", "scope": SCOPE,
            "code_challenge": challenge, "code_challenge_method": "S256", "state": state,
            "access_type": "offline", "prompt": "consent"})
        try:
            webbrowser.open(url)
            deadline = time.time() + LOGIN_WAIT
            while not got and time.time() < deadline and not self._stop:
                srv.handle_request()
        finally:
            srv.server_close()
        if "code" not in got:
            log.warning("Google: sign-in %s", got.get("error") or "not completed")
            self._set("error", Msg("google.cancelled"))
            return
        try:
            d = _post(TOKEN, {"code": got["code"], "client_id": client_id, "client_secret": secrets.load(SECRET) or "",
                              "redirect_uri": redirect, "grant_type": "authorization_code", "code_verifier": verifier})
        except urllib.error.HTTPError as e:
            self._set("error", Msg("google.sign_in_failed", message=_error(e)[1]))
            return
        except Exception as e:
            log.exception("Google sign-in")
            self._set("error", str(e)[:160])
            return
        if d.get("refresh_token"):
            secrets.save(REFRESH, d["refresh_token"])
        with self._lock:
            self._token, self._expires = d.get("access_token"), time.time() + float(d.get("expires_in") or 3600)
        log.info("Google Calendar: signed in")
        self._set("ok")
        self._wake.set()

    def logout(self):
        secrets.delete(REFRESH)
        with self._lock:
            self._token, self._expires = None, 0
            self._status, self._error, self._account, self._meeting = "signed_out", "", "", None
        log.info("Google Calendar: signed out")

    def refresh(self):
        self._wake.set()

    # ---------- polling ----------
    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="google").start()

    def stop(self):
        self._stop = True
        self._wake.set()

    def _access_token(self):
        with self._lock:
            if self._token and self._expires - 120 > time.time():
                return self._token
        refresh = secrets.load(REFRESH)
        if not refresh:
            return None
        d = _post(TOKEN, {"client_id": self.cfg()["client_id"], "client_secret": secrets.load(SECRET) or "",
                          "refresh_token": refresh, "grant_type": "refresh_token"})
        with self._lock:
            self._token, self._expires = d.get("access_token"), time.time() + float(d.get("expires_in") or 3600)
            return self._token

    def fetch(self):
        tok = self._access_token()
        if not tok:
            return None
        now = datetime.now(timezone.utc)
        q = urllib.parse.urlencode({"timeMin": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                    "timeMax": (now + timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                    "singleEvents": "true", "orderBy": "startTime", "maxResults": "15"})
        req = urllib.request.Request(f"{API}/calendars/primary/events?{q}",
                                     headers={"Authorization": "Bearer " + tok, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.load(r)

    def _poll(self):
        try:
            d = self.fetch()
        except urllib.error.HTTPError as e:
            kind, msg = _error(e)
            if kind == "invalid_grant":
                secrets.delete(REFRESH)                   # revoked or expired: sign in again
                self._set("signed_out", Msg("google.expired"))
            else:
                self._set("error", Msg("google.http_error", code=e.code, message=msg))
            log.warning("Google Calendar HTTP %s %s", e.code, msg)
            return
        except (urllib.error.URLError, OSError):
            self._set("error", Msg("m365.network"))
            log.debug("poll google", exc_info=True)
            return
        except Exception as e:
            self._set("error", str(e)[:160])
            log.exception("poll google")
            return
        if d is None:
            if self._status != "signing_in":
                self._set("signed_out")
            return
        m = pick_meeting(d.get("items"), time.time())
        with self._lock:
            self._meeting, self._updated, self._account = m, time.time(), str(d.get("summary") or "")
            if self._status != "signing_in":
                self._status, self._error = "ok", ""

    def _loop(self):
        time.sleep(4)
        nxt = 0
        while not self._stop:
            try:
                if self._status != "signing_in" and time.time() >= nxt and secrets.load(REFRESH):
                    self._poll()
                    nxt = time.time() + POLL
                alert_before(self._store, self.meeting(), self.cfg()["alert_minutes"], self._alerted)
            except Exception:
                log.exception("google loop")
            if self._wake.wait(15):
                self._wake.clear()
                nxt = 0
