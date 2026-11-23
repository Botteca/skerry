"""The local server only talks to agents: no browsers (CSRF), no DNS rebinding, no huge bodies."""
import pytest

from skerry import api
from skerry.server import MAX_BODY, create_app
from skerry.settings import Settings
from skerry.store import Store


@pytest.fixture
def client(tmp_path):
    settings = Settings(str(tmp_path / "settings.json"))
    store = Store(settings, on_event=lambda *_: None)
    shown = []
    app = create_app(store, settings, on_show=lambda: shown.append(1))
    c = app.test_client()
    c.shown, c.store = shown, store
    return c


EVENT = {"hook_event_name": "UserPromptSubmit", "session_id": "s-1", "cwd": "C:/rep/ExampleApp", "prompt": "hi"}


def test_agent_request_is_accepted(client):
    assert client.post("/hook/UserPromptSubmit?agent=claude", json=EVENT).status_code == 200
    assert client.get("/health").status_code == 200


@pytest.mark.parametrize("headers", [
    {"Origin": "https://example.invalid"},
    {"Origin": "null"},
    {"Sec-Fetch-Site": "cross-site"},
])
def test_browser_requests_are_refused(client, headers):
    assert client.post("/hook/UserPromptSubmit?agent=claude", json=EVENT, headers=headers).status_code == 403
    assert client.post("/ui/show", json={}, headers=headers).status_code == 403
    assert client.shown == []


def test_dns_rebinding_host_is_refused(client):
    r = client.post("/hook/UserPromptSubmit?agent=claude", json=EVENT, headers={"Host": "evil.example.invalid:47800"})
    assert r.status_code == 403
    assert client.get("/health", headers={"Host": "evil.example.invalid"}).status_code == 403


def test_localhost_names_are_accepted(client):
    for host in ("127.0.0.1:47800", "localhost:47800", "localhost"):
        assert client.get("/health", headers={"Host": host}).status_code == 200


def test_non_json_post_is_refused(client):
    # text/plain is what a browser can send cross-site without a preflight
    r = client.post("/hook/UserPromptSubmit?agent=claude", data="{}", content_type="text/plain")
    assert r.status_code == 403


def test_oversized_body_is_refused(client):
    r = client.post("/statusline", data=b'{"x":"' + b"a" * (MAX_BODY + 10) + b'"}', content_type="application/json")
    assert r.status_code == 413


def test_update_source_is_not_settable_from_the_ui():
    # the update URL decides what gets installed: never writable through js_api
    assert "update_url" not in api.SETTABLE
    assert "chained_statusline" not in api.SETTABLE
