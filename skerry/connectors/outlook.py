"""Outlook on this PC: the next meeting read from classic Outlook for Windows, with no sign-in or setup.

Uses the Outlook object model over COM (comtypes), read-only, and only while Outlook is already running: Skerry
never starts Outlook. The new Outlook for Windows (olk.exe) has no COM interface, so it is not supported.
The Teams/Meet/Zoom link is taken from the location or the body of the appointment. Polled every 2 minutes in a
background thread; errors only change the status shown in settings.
"""
import logging
import threading
import time
from datetime import datetime, timedelta

from ..i18n import Msg, render
from .calendar import pick
from .m365 import alert_before

log = logging.getLogger("skerry")

POLL = 120
MAX_ITEMS = 60
OL_FOLDER_CALENDAR = 9
OL_FREE = 0
OL_MEETING_CANCELED = (5, 7)          # olMeetingCanceled, olMeetingReceivedAndCanceled
OL_RESPONSE_DECLINED = 4


def outlook_running():
    """True when classic Outlook (OUTLOOK.EXE) is running for this user."""
    try:
        import psutil
        for p in psutil.process_iter(["name"]):
            if (p.info.get("name") or "").upper() == "OUTLOOK.EXE":
                return True
    except Exception:
        log.debug("process list", exc_info=True)
    return False


def _restrict_date(dt):
    """A date in the format Outlook's Restrict expects: the user's short date + time, like VBA Format("ddddd h:nn").

    Outlook compares these strings with the regional settings, so an en-US format fails on other locales."""
    import ctypes
    from ctypes import wintypes

    class SYSTEMTIME(ctypes.Structure):
        _fields_ = [(n, wintypes.WORD) for n in ("wYear", "wMonth", "wDayOfWeek", "wDay", "wHour", "wMinute",
                                                 "wSecond", "wMilliseconds")]

    st = SYSTEMTIME(dt.year, dt.month, 0, dt.day, dt.hour, dt.minute, 0, 0)
    k32 = ctypes.windll.kernel32
    d, t = ctypes.create_unicode_buffer(80), ctypes.create_unicode_buffer(80)
    k32.GetDateFormatW(0x400, 0x1, ctypes.byref(st), None, d, 80)      # LOCALE_USER_DEFAULT, DATE_SHORTDATE
    k32.GetTimeFormatW(0x400, 0x2, ctypes.byref(st), None, t, 80)      # TIME_NOSECONDS
    return f"{d.value} {t.value}"


def _ts(value):
    """Timestamp of a COM date (naive local datetime)."""
    if isinstance(value, datetime):
        return value.timestamp()
    return None


def read_events(now):
    """Normalised events (see connectors/calendar.py) from the default calendar of the running Outlook."""
    import comtypes.client

    # COM is initialised once by the polling thread (Outlook._loop), never uninitialised while objects live
    app = comtypes.client.CreateObject("Outlook.Application", dynamic=True)   # attaches to the running one
    cal = app.GetNamespace("MAPI").GetDefaultFolder(OL_FOLDER_CALENDAR)
    items = cal.Items
    items.IncludeRecurrences = True
    items.Sort("[Start]")
    frm = datetime.fromtimestamp(now) - timedelta(hours=12)
    to = datetime.fromtimestamp(now) + timedelta(hours=36)
    found = items.Restrict(f"[Start] <= '{_restrict_date(to)}' AND [End] >= '{_restrict_date(frm)}'")
    out = []
    it = found.GetFirst()
    while it is not None and len(out) < MAX_ITEMS:
        try:
            body = ""
            try:
                body = str(it.Body or "")[:20000]
            except Exception:
                pass
            out.append({
                "id": str(getattr(it, "GlobalAppointmentID", "") or it.EntryID) + "@" + str(_ts(it.Start)),
                "title": str(it.Subject or ""),
                "start": _ts(it.Start), "end": _ts(it.End),
                "location": str(it.Location or ""),
                "text": body,
                "cancelled": int(it.MeetingStatus or 0) in OL_MEETING_CANCELED,
                "all_day": bool(it.AllDayEvent),
                "declined": int(it.ResponseStatus or 0) == OL_RESPONSE_DECLINED,
                "free": int(it.BusyStatus or 0) == OL_FREE,
            })
        except Exception:
            log.debug("outlook item", exc_info=True)
        it = found.GetNext()
    return out


class Outlook:
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
        c = self._settings.get("connectors.outlook", {}) or {}
        return {"enabled": bool(c.get("enabled")), "alert_minutes": int(c.get("alert_minutes", 5) or 0)}

    def status(self):
        with self._lock:
            return {"configured": True, "status": self._status, "error": render(self._error),
                    "updated": self._updated}

    def meeting(self):
        if not self.cfg()["enabled"]:
            return None
        with self._lock:
            m = self._meeting
            now = time.time()
            if not m or m["end"] <= now:
                return None
            return {**m, "in_progress": m["start"] <= now < m["end"]}

    def login(self):
        return False

    def logout(self):
        pass

    def _set(self, status, error=""):
        with self._lock:
            self._status, self._error = status, error

    def refresh(self):
        self._wake.set()

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="outlook").start()

    def stop(self):
        self._stop = True
        self._wake.set()

    def _poll(self):
        if not outlook_running():
            # keep the last meeting: Outlook may only be closed for a moment
            self._set("waiting", Msg("outlook.not_running"))
            return
        try:
            events = read_events(time.time())
        except ImportError:
            self._set("error", Msg("outlook.no_com"))
            return
        except Exception as e:
            self._set("error", Msg("outlook.failed"))
            log.warning("Outlook: could not read the calendar (%s)", type(e).__name__, exc_info=True)
            return
        m = pick(events, time.time(), "ol")
        with self._lock:
            self._meeting, self._updated, self._status, self._error = m, time.time(), "ok", ""

    def _loop(self):
        time.sleep(6)
        try:
            import comtypes
            comtypes.CoInitialize()          # this thread only; the objects are released with each poll
        except Exception:
            log.debug("COM not available", exc_info=True)
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
                    with self._lock:
                        self._meeting = None
            except Exception:
                log.exception("outlook loop")
            if self._wake.wait(15):
                self._wake.clear()
                nxt = 0
