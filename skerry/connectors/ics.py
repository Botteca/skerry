"""Calendar link (iCalendar / ICS): the next meeting from a calendar's secret address, with no sign-in.

Outlook on the web ("Publish a calendar" -> ICS link) and Google Calendar ("Secret address in iCal format") give
a private https address. Anyone with it can read the calendar, so it is treated like a password: encrypted with
DPAPI in `skerry.secrets`, never written to settings.json and never shown again. Only https is accepted
(webcal:// is the same address). Read-only, polled every 5 minutes with a timeout and a size limit; recurring
events are expanded with `recurring_ical_events`. Errors only change the status shown in settings.
"""
import logging
import threading
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta

# imported at module load: on Windows python-dateutil (used by both) reads the time-zone key name from the registry
# once when it is first imported
import icalendar
import recurring_ical_events

from .. import secrets
from ..i18n import Msg, render
from .calendar import pick
from .m365 import alert_before

log = logging.getLogger("skerry")

SECRET = "ics-url"
POLL = 300
TIMEOUT = 20
MAX_BYTES = 15 * 1024 * 1024
WINDOW_BEFORE, WINDOW_AFTER = timedelta(hours=12), timedelta(hours=36)


def normalize_url(value):
    """https URL of a calendar link, or None. webcal:// (what calendar apps show) means https://."""
    url = str(value or "").strip()
    if url.lower().startswith("webcal://"):
        url = "https://" + url[len("webcal://"):]
    return url if url.lower().startswith("https://") and len(url) > len("https://x.y") and " " not in url else None


def _ts(value):
    """Timestamp of an ICS date-time; floating (naive) times are local time. None for all-day dates."""
    if isinstance(value, datetime):
        return value.timestamp()          # aware: exact; naive: interpreted as local time
    return None


def parse(data, now):
    """Normalised events (see connectors/calendar.py) around `now` from ICS bytes."""
    cal = icalendar.Calendar.from_ical(data)
    start = datetime.fromtimestamp(now) - WINDOW_BEFORE
    end = datetime.fromtimestamp(now) + WINDOW_AFTER
    out = []
    for ev in recurring_ical_events.of(cal).between(start, end):
        dtstart = ev.get("DTSTART")
        dtend = ev.get("DTEND")
        s = dtstart.dt if dtstart is not None else None
        if s is None:
            continue
        if dtend is not None:
            e = dtend.dt
        elif ev.get("DURATION") is not None:
            e = s + ev.get("DURATION").dt
        else:
            e = s
        all_day = isinstance(s, date) and not isinstance(s, datetime)
        status = str(ev.get("STATUS") or "").upper()
        busy = str(ev.get("X-MICROSOFT-CDO-BUSYSTATUS") or "").upper()
        out.append({
            "id": f"{ev.get('UID') or ''}@{_ts(s) or s}",
            "title": str(ev.get("SUMMARY") or ""),
            "start": _ts(s), "end": _ts(e),
            "location": str(ev.get("LOCATION") or ""),
            "text": "\n".join(str(ev.get(k) or "") for k in ("DESCRIPTION", "X-GOOGLE-CONFERENCE",
                                                               "X-MICROSOFT-SKYPETEAMSMEETINGURL")),
            "url": str(ev.get("URL") or ""),
            "cancelled": status == "CANCELLED",
            "all_day": all_day,
            "declined": False,
            "free": str(ev.get("TRANSP") or "").upper() == "TRANSPARENT" or busy == "FREE",
        })
    return out


class ICS:
    def __init__(self, settings, store):
        self._settings = settings
        self._store = store
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = False
        self._status, self._error = "off", ""
        self._meeting, self._updated = None, 0
        self._alerted = set()

    def cfg(self):
        c = self._settings.get("connectors.ics", {}) or {}
        return {"enabled": bool(c.get("enabled")), "alert_minutes": int(c.get("alert_minutes", 5) or 0)}

    def status(self):
        with self._lock:
            has = secrets.load(SECRET) is not None
            return {"configured": has, "status": self._status, "error": render(self._error),
                    "updated": self._updated, "has_secret": has}

    def meeting(self):
        if not self.cfg()["enabled"]:
            return None
        with self._lock:
            m = self._meeting
            now = time.time()
            if not m or m["end"] <= now:
                return None
            return {**m, "in_progress": m["start"] <= now < m["end"]}

    def set_secret(self, value):
        """Save the calendar link (encrypted). An empty value removes it; an invalid one is refused."""
        if not value:
            secrets.delete(SECRET)
            self._set("off")
            with self._lock:
                self._meeting = None
            return
        url = normalize_url(value)
        if not url:
            self._set("error", Msg("ics.bad_url"))
            return
        secrets.save(SECRET, url)
        self.refresh()

    def login(self):
        return False

    def logout(self):
        self.set_secret("")

    def _set(self, status, error=""):
        with self._lock:
            self._status, self._error = status, error

    def refresh(self):
        self._wake.set()

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="ics").start()

    def stop(self):
        self._stop = True
        self._wake.set()

    def fetch(self, url):
        req = urllib.request.Request(url, headers={"User-Agent": "Skerry", "Accept": "text/calendar"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            if not r.geturl().lower().startswith("https://"):
                raise ValueError("redirected away from https")
            data = r.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError("calendar too large")
        return data

    def _poll(self):
        url = secrets.load(SECRET)
        if not url:
            self._set("off")
            return
        try:
            events = parse(self.fetch(url), time.time())
        except urllib.error.HTTPError as e:
            self._set("error", Msg("ics.http_error", code=e.code))
            log.warning("Calendar link: HTTP %s", e.code)
            return
        except (urllib.error.URLError, OSError):
            self._set("error", Msg("m365.network"))
            log.debug("poll ics", exc_info=True)
            return
        except Exception:
            self._set("error", Msg("ics.bad_data"))
            log.warning("Calendar link: unreadable calendar", exc_info=True)
            return
        m = pick(events, time.time(), "ics")
        with self._lock:
            self._meeting, self._updated, self._status, self._error = m, time.time(), "ok", ""

    def _loop(self):
        time.sleep(5)
        nxt = 0
        while not self._stop:
            try:
                if self.cfg()["enabled"]:
                    if time.time() >= nxt:
                        self._poll()
                        nxt = time.time() + POLL
                    alert_before(self._store, self.meeting(), self.cfg()["alert_minutes"], self._alerted)
                elif self._status != "off":
                    self._set("off")
            except Exception:
                log.exception("ics loop")
            if self._wake.wait(15):
                self._wake.clear()
                nxt = 0
