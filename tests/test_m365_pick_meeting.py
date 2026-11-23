"""pick_meeting(): which calendar event the pill shows. Pure function, no network."""
from datetime import datetime, timedelta, timezone

from skerry.connectors.m365 import _parse, pick_meeting

NOW = datetime(2026, 3, 10, 9, 0, tzinfo=timezone.utc)


def graph_time(dt):
    # Microsoft Graph returns 7 fractional digits and no offset (UTC because of the Prefer header)
    return {"dateTime": dt.strftime("%Y-%m-%dT%H:%M:%S.0000000"), "timeZone": "UTC"}


def event(subject, start_min, end_min, **extra):
    e = {"id": subject.lower().replace(" ", "-"), "subject": subject,
         "start": graph_time(NOW + timedelta(minutes=start_min)),
         "end": graph_time(NOW + timedelta(minutes=end_min))}
    e.update(extra)
    return e


def pick(events):
    return pick_meeting(events, NOW.timestamp())


def test_parse_graph_datetime():
    assert _parse(graph_time(NOW)) == NOW.timestamp()
    assert _parse({"dateTime": "not a date"}) is None
    assert _parse(None) is None


def test_no_events():
    assert pick([]) is None
    assert pick(None) is None


def test_picks_earliest_upcoming():
    m = pick([event("Later", 120, 150), event("Soon", 30, 60), event("Afternoon", 300, 330)])
    assert m["title"] == "Soon"
    assert m["in_progress"] is False
    assert m["start"] == (NOW + timedelta(minutes=30)).timestamp()


def test_in_progress_meeting_wins_over_next():
    m = pick([event("Next", 30, 60), event("Running", -10, 20)])
    assert m["title"] == "Running"
    assert m["in_progress"] is True


def test_skips_finished_cancelled_all_day_and_declined():
    events = [
        event("Finished", -60, -30),
        event("Ends now", -30, 0),
        event("Cancelled", 5, 30, isCancelled=True),
        event("All day", -540, 900, isAllDay=True),
        event("Declined", 10, 40, responseStatus={"response": "declined"}),
        event("Kept", 50, 80, responseStatus={"response": "accepted"}),
    ]
    assert pick(events)["title"] == "Kept"


def test_only_skipped_events_gives_none():
    assert pick([event("Cancelled", 5, 30, isCancelled=True), event("Old", -60, -1)]) is None


def test_teams_join_url_and_provider():
    m = pick([event("Sprint review", 15, 45, onlineMeeting={"joinUrl": "https://teams.example.invalid/meet/1"},
                    onlineMeetingProvider="teamsForBusiness", location={"displayName": "Room 4"})])
    assert m["join_url"] == "https://teams.example.invalid/meet/1"
    assert m["provider"] == "Teams"
    assert m["location"] == ""  # with a join link the location is not shown


def test_https_location_is_used_as_join_url():
    m = pick([event("External call", 15, 45, location={"displayName": " https://meet.example.invalid/abc "})])
    assert m["join_url"] == "https://meet.example.invalid/abc"
    assert m["provider"] == "Online"


def test_non_https_location_is_not_a_link():
    m = pick([event("Room meeting", 15, 45, location={"displayName": "http://intranet.example.invalid"})])
    assert m["join_url"] == ""
    assert m["provider"] == ""
    assert m["location"] == "http://intranet.example.invalid"


def test_missing_subject_and_bad_dates():
    events = [{"id": "x", "start": {"dateTime": "garbage"}, "end": graph_time(NOW + timedelta(hours=1))},
              {"id": "y", "start": graph_time(NOW + timedelta(minutes=5)), "end": graph_time(NOW + timedelta(minutes=35))}]
    m = pick(events)
    assert m["id"] == "y"
    assert m["title"] == "(senza titolo)"
