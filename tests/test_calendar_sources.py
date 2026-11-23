"""Calendar sources without an online API: a calendar link (ICS) and Outlook on this PC (shared picking logic)."""
from datetime import datetime

import pytest

from skerry.connectors import ics
from skerry.connectors.calendar import join_link, pick

ICS = b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Contoso//Example//EN
BEGIN:VTIMEZONE
TZID:W. Europe Standard Time
BEGIN:STANDARD
DTSTART:16010101T030000
TZOFFSETFROM:+0200
TZOFFSETTO:+0100
RRULE:FREQ=YEARLY;INTERVAL=1;BYDAY=-1SU;BYMONTH=10
END:STANDARD
BEGIN:DAYLIGHT
DTSTART:16010101T020000
TZOFFSETFROM:+0100
TZOFFSETTO:+0200
RRULE:FREQ=YEARLY;INTERVAL=1;BYDAY=-1SU;BYMONTH=3
END:DAYLIGHT
END:VTIMEZONE
BEGIN:VEVENT
UID:standup-1
SUMMARY:Daily standup
DTSTART;TZID=W. Europe Standard Time:20261102T093000
DTEND;TZID=W. Europe Standard Time:20261102T094500
RRULE:FREQ=DAILY;BYDAY=MO,TU,WE,TH,FR
LOCATION:Microsoft Teams Meeting
DESCRIPTION:Join: <https://teams.microsoft.com/l/meetup-join/19%3ameeting_abc%40thread.v2/0?context=%7b%7d>
END:VEVENT
BEGIN:VEVENT
UID:holiday
SUMMARY:Holiday
DTSTART;VALUE=DATE:20261124
DTEND;VALUE=DATE:20261125
END:VEVENT
BEGIN:VEVENT
UID:cancelled
SUMMARY:Cancelled sync
STATUS:CANCELLED
DTSTART:20261124T070000Z
DTEND:20261124T073000Z
END:VEVENT
BEGIN:VEVENT
UID:review
SUMMARY:Sprint review
DTSTART:20261124T120000Z
DTEND:20261124T130000Z
X-GOOGLE-CONFERENCE:https://meet.google.com/abc-defg-hij
END:VEVENT
END:VCALENDAR
"""


def _local(*a):
    return datetime(*a).timestamp()


def test_recurring_event_in_its_time_zone_is_found():
    now = datetime(2026, 11, 24, 7, 0).astimezone()            # 07:00 local
    events = ics.parse(ICS, now.timestamp())
    titles = [e["title"] for e in events]
    assert titles.count("Daily standup") >= 1                   # expanded from the RRULE
    m = pick(events, now.timestamp(), "ics")
    assert m["title"] in ("Daily standup", "Sprint review")
    assert m["join_url"].startswith("https://")
    assert not any(e["title"] == "Holiday" and not e["all_day"] for e in events)


def test_pick_skips_cancelled_all_day_declined_and_finished():
    now = 1_000_000.0
    events = [
        {"id": "a", "title": "Old", "start": now - 7200, "end": now - 3600},
        {"id": "b", "title": "Cancelled", "start": now + 60, "end": now + 600, "cancelled": True},
        {"id": "c", "title": "All day", "start": None, "end": None, "all_day": True},
        {"id": "d", "title": "Declined", "start": now + 30, "end": now + 600, "declined": True},
        {"id": "e", "title": "Next", "start": now + 900, "end": now + 1800, "location": "Room 4"},
        {"id": "f", "title": "Later", "start": now + 3600, "end": now + 5400},
    ]
    m = pick(events, now, "x")
    assert (m["title"], m["location"], m["in_progress"], m["id"]) == ("Next", "Room 4", False, "x:e")


def test_join_links():
    assert join_link("Click https://teams.microsoft.com/l/meetup-join/19%3a123/0?context=%7b%7d>") == (
        "Teams", "https://teams.microsoft.com/l/meetup-join/19%3a123/0?context=%7b%7d")
    assert join_link("", "https://meet.google.com/abc-defg-hij") == ("Meet", "https://meet.google.com/abc-defg-hij")
    assert join_link("https://contoso.zoom.us/j/123456?pwd=x")[0] == "Zoom"
    safe = "https://eur01.safelinks.protection.outlook.com/?url=https%3A%2F%2Fteams.microsoft.com%2Fl%2Fmeetup-join%2F19%253a1"
    assert join_link(safe)[0] == "Teams"
    assert join_link("javascript:alert(1) http://teams.microsoft.com/l/meetup-join/x") == ("", "")


@pytest.mark.parametrize("value,expected", [
    ("webcal://calendar.example.invalid/basic.ics", "https://calendar.example.invalid/basic.ics"),
    ("  https://outlook.example.invalid/owa/calendar/abc/reachcalendar.ics ",
     "https://outlook.example.invalid/owa/calendar/abc/reachcalendar.ics"),
    ("http://calendar.example.invalid/basic.ics", None),
    ("file:///C:/x.ics", None),
    ("javascript:alert(1)", None),
    ("", None),
])
def test_calendar_link_must_be_https(value, expected):
    assert ics.normalize_url(value) == expected


def test_link_never_goes_to_settings():
    from skerry.api import SETTABLE
    assert not any(k.startswith("connectors.ics.") and k not in ("connectors.ics.enabled", "connectors.ics.alert_minutes")
                   for k in SETTABLE)
