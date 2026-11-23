"""Google Calendar connector against a fake Google (OAuth token endpoint + Calendar API) and a fake browser."""
import base64
import hashlib
import threading
import time
import types
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import pytest

from skerry import secrets
from skerry.connectors import Connectors, google
from skerry.settings import Settings

NOW = datetime.now(timezone.utc).replace(microsecond=0)


def rfc(dt):
    return dt.astimezone(timezone(timedelta(hours=1))).isoformat()        # Google returns local offsets


def event(summary, start_min, end_min, **extra):
    e = {"id": summary.lower().replace(" ", "-"), "summary": summary, "status": "confirmed",
         "start": {"dateTime": rfc(NOW + timedelta(minutes=start_min))},
         "end": {"dateTime": rfc(NOW + timedelta(minutes=end_min))}}
    e.update(extra)
    return e


# ---------------------------------------------------------------- choosing the event

def test_pick_meeting_and_meet_link():
    events = [
        event("Finished", -60, -30),
        event("All day", 0, 0, start={"date": "2026-03-10"}, end={"date": "2026-03-11"}),
        event("Cancelled", 5, 30, status="cancelled"),
        event("Declined", 10, 40, attendees=[{"email": "ada@example.invalid", "self": True, "responseStatus": "declined"}]),
        event("Design review", 20, 50, hangoutLink="https://meet.google.com/abc-defg-hij"),
        event("Later", 90, 120, location="Room 4"),
    ]
    m = google.pick_meeting(events, NOW.timestamp())
    assert (m["title"], m["provider"], m["join_url"]) == ("Design review", "Meet", "https://meet.google.com/abc-defg-hij")
    assert m["start"] == (NOW + timedelta(minutes=20)).timestamp() and m["in_progress"] is False
    later = google.pick_meeting(events[-1:], NOW.timestamp())
    assert (later["join_url"], later["location"]) == ("", "Room 4")


def test_only_https_links_are_used():
    e = event("x", 5, 10, hangoutLink="javascript:alert(1)",
              conferenceData={"entryPoints": [{"entryPointType": "phone", "uri": "tel:+1-555-0100"},
                                              {"entryPointType": "video", "uri": "https://video.example.invalid/j/1"}]})
    assert google.meet_link(e) == "https://video.example.invalid/j/1"
    assert google.meet_link(event("y", 5, 10, hangoutLink="http://meet.example.invalid")) == ""


# ---------------------------------------------------------------- fake Google

class FakeStore:
    def __init__(self):
        self.alerts = []

    def alert(self, level, icon, text, sound=True):
        self.alerts.append(str(text))


@pytest.fixture
def env(tmp_path, fake_http, monkeypatch):
    monkeypatch.setattr(google, "AUTH", fake_http.url + "/auth")
    monkeypatch.setattr(google, "TOKEN", fake_http.url + "/token")
    monkeypatch.setattr(google, "API", fake_http.url + "/calendar/v3")
    monkeypatch.setattr(google, "LOGIN_WAIT", 10)
    settings = Settings(str(tmp_path / "settings.json"))
    settings.set("connectors.google.client_id", "1234567890-fake.apps.googleusercontent.com")
    store = FakeStore()
    c = google.Google(settings, store)
    c.set_secret("fake-client-secret")
    state = {"challenge": None, "events": [event("Design review", 20, 50, hangoutLink="https://meet.google.com/abc-defg-hij")]}

    def token(req):
        b = req["body"]
        assert b["client_secret"] == "fake-client-secret"
        if b["grant_type"] == "authorization_code":
            digest = hashlib.sha256(b["code_verifier"].encode()).digest()
            assert base64.urlsafe_b64encode(digest).rstrip(b"=").decode() == state["challenge"]   # PKCE
            assert b["code"] == "fake-code"
            return 200, {"access_token": "access-1", "refresh_token": "refresh-1", "expires_in": 3600}
        if b["refresh_token"] == "refresh-1":
            return 200, {"access_token": "access-2", "expires_in": 3600}
        return 400, {"error": "invalid_grant", "error_description": "Token has been expired or revoked."}

    def events(req):
        if req["headers"].get("Authorization") not in ("Bearer access-1", "Bearer access-2"):
            return 401, {"error": {"message": "Invalid Credentials"}}
        assert req["query"]["singleEvents"] == "true" and req["query"]["orderBy"] == "startTime"
        return 200, {"summary": "ada@example.invalid", "items": state["events"]}

    fake_http.routes[("POST", "/token")] = token
    fake_http.routes[("GET", "/calendar/v3/calendars/primary/events")] = events
    return {"c": c, "store": store, "settings": settings, "http": fake_http, "state": state,
            "path": tmp_path / "settings.json"}


def fake_browser(env, monkeypatch, deny=False):
    """Stands in for the user's browser: reads the sign-in URL and follows the redirect back to Skerry."""
    seen = {}

    def open_url(url):
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))
        seen.update(q)
        env["state"]["challenge"] = q["code_challenge"]
        back = {"error": "access_denied", "state": q["state"]} if deny else {"code": "fake-code", "state": q["state"]}

        def follow():
            time.sleep(0.2)
            urllib.request.urlopen(q["redirect_uri"] + "?" + urllib.parse.urlencode(back), timeout=5).read()
        threading.Thread(target=follow, daemon=True).start()
        return True

    monkeypatch.setattr(google.webbrowser, "open", open_url)
    return seen


def test_sign_in_poll_and_secrets(env, monkeypatch):
    seen = fake_browser(env, monkeypatch)
    c = env["c"]
    c._login(c.cfg()["client_id"])
    assert seen["scope"] == google.SCOPE and seen["code_challenge_method"] == "S256"
    assert seen["redirect_uri"].startswith("http://127.0.0.1:") and seen["access_type"] == "offline"
    assert c.status()["status"] == "ok"
    c._poll()
    st = c.status()
    assert (st["status"], st["account"]) == ("ok", "ada@example.invalid")
    assert c.meeting()["join_url"] == "https://meet.google.com/abc-defg-hij"
    text = env["path"].read_text(encoding="utf-8")
    assert "fake-client-secret" not in text and "refresh-1" not in text
    assert secrets.load(google.REFRESH) == "refresh-1"

    c._token = None                                                    # access token expired: uses the refresh token
    c._poll()
    assert c.status()["status"] == "ok" and env["http"].requests[-1]["headers"]["Authorization"] == "Bearer access-2"


def test_denied_sign_in(env, monkeypatch):
    fake_browser(env, monkeypatch, deny=True)
    env["c"]._login(env["c"].cfg()["client_id"])
    assert env["c"].status()["status"] == "error" and secrets.load(google.REFRESH) is None


def test_revoked_access_asks_to_sign_in_again(env):
    secrets.save(google.REFRESH, "revoked")
    env["c"]._poll()
    st = env["c"].status()
    assert st["status"] == "signed_out" and "sign in again" in st["error"]
    assert secrets.load(google.REFRESH) is None


def test_slow_google_never_blocks(env, monkeypatch):
    secrets.save(google.REFRESH, "refresh-1")
    monkeypatch.setattr(google, "TIMEOUT", 0.3)
    env["http"].delay = 1
    t = time.time()
    env["c"]._poll()
    assert time.time() - t < 3 and env["c"].status()["status"] == "error"


def test_login_needs_client_id_and_secret(env):
    env["c"].set_secret("")
    assert env["c"].login() is False and env["c"].status()["status"] == "error"


def test_island_shows_the_earliest_meeting_of_both_calendars(tmp_path):
    settings = Settings(str(tmp_path / "settings.json"))
    cs = Connectors(settings, FakeStore())
    soon = {"id": "a", "title": "Standup", "start": time.time() + 600, "end": time.time() + 1500, "in_progress": False}
    later = {**soon, "id": "b", "title": "Planning", "start": time.time() + 3600, "end": time.time() + 7200}
    cs.m365 = types.SimpleNamespace(meeting=lambda: later)
    cs.google = types.SimpleNamespace(meeting=lambda: soon)
    assert cs.meeting()["title"] == "Standup"
    cs.google = types.SimpleNamespace(meeting=lambda: None)
    assert cs.meeting()["title"] == "Planning"
