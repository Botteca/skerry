"""Azure Data Factory connector against a fake Azure (token endpoint + Resource Manager). No real network."""
import json
import time

import pytest

from skerry import secrets
from skerry.connectors import adf, azure
from skerry.settings import Settings

PIPES = "PL_Nightly_Load, PL_Sales_Export"
ARM_PATH = ("/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-contoso-data"
            "/providers/Microsoft.DataFactory/factories/adf-contoso-prod/queryPipelineRuns")


class FakeStore:
    def __init__(self):
        self.alerts = []

    def alert(self, level, icon, text, sound=True):
        self.alerts.append((level, str(text)))


def run(pipeline, status, start, run_id, message=""):
    iso = lambda ts: time.strftime("%Y-%m-%dT%H:%M:%S.1234567Z", time.gmtime(ts))
    return {"runId": run_id, "pipelineName": pipeline, "status": status, "runStart": iso(start),
            "runEnd": iso(start + 60), "message": message}


@pytest.fixture
def env(tmp_path, fake_http, monkeypatch):
    monkeypatch.setattr(azure, "LOGIN", fake_http.url)
    monkeypatch.setattr(adf, "ARM", fake_http.url)
    azure.forget()
    settings = Settings(str(tmp_path / "settings.json"))
    settings.update({"connectors.adf.enabled": True, "connectors.adf.auth": "sp",
                     "connectors.adf.tenant": "contoso.example", "connectors.adf.client_id": "11111111-2222-3333-4444-555555555555",
                     "connectors.adf.subscription": "00000000-0000-0000-0000-000000000000",
                     "connectors.adf.resource_group": "rg-contoso-data", "connectors.adf.factory": "adf-contoso-prod",
                     "connectors.adf.pipelines": PIPES})
    store = FakeStore()
    c = adf.ADF(settings, store)
    c.set_secret("fake-client-secret")
    fake_http.routes[("POST", "/contoso.example/oauth2/v2.0/token")] = lambda req: (
        (200, {"access_token": "tok-1", "expires_in": 3600}) if req["body"].get("client_secret") == "fake-client-secret"
        else (401, {"error_description": "AADSTS7000215: Invalid client secret provided."}))
    return {"c": c, "store": store, "settings": settings, "http": fake_http, "path": tmp_path / "settings.json"}


def test_latest_run_per_pipeline():
    now = time.time()
    runs = [run("PL_Nightly_Load", "Failed", now - 7200, "r1"), run("PL_Nightly_Load", "Succeeded", now - 600, "r2"),
            run("PL_Other", "Failed", now, "r3")]
    out = adf.latest_runs(runs, ["PL_Nightly_Load", "PL_Sales_Export"])
    assert [(r["pipeline"], r["status"], r["run_id"]) for r in out] == [
        ("PL_Nightly_Load", "Succeeded", "r2"), ("PL_Sales_Export", "none", "")]
    assert abs(out[0]["start"] - int(now - 600)) < 1          # 7 fractional digits parsed


def test_runs_alert_once_and_no_secret_in_settings(env):
    now = time.time()
    pages = {None: {"value": [run("PL_Nightly_Load", "Failed", now, "r9", "Copy activity failed")],
                    "continuationToken": "page-2"},
             "page-2": {"value": [run("PL_Sales_Export", "InProgress", now - 30, "r8")]}}

    def query(req):
        assert req["headers"]["Authorization"] == "Bearer tok-1"
        assert req["query"]["api-version"] == "2018-06-01"
        assert req["body"]["filters"] == [{"operand": "PipelineName", "operator": "In",
                                           "values": ["PL_Nightly_Load", "PL_Sales_Export"]}]
        return 200, pages[req["body"].get("continuationToken")]

    env["http"].routes[("POST", ARM_PATH)] = query
    c = env["c"]
    c._poll(c.cfg())
    c._poll(c.cfg())
    runs = c.runs()
    assert [(r["pipeline"], r["status"]) for r in runs] == [("PL_Nightly_Load", "Failed"), ("PL_Sales_Export", "InProgress")]
    assert runs[0]["message"] == "Copy activity failed"
    assert c.status()["status"] == "ok" and c.status()["has_secret"]
    assert env["store"].alerts == [("danger", "Data Factory: PL_Nightly_Load failed")]   # once, not on every poll
    assert "fake-client-secret" not in env["path"].read_text(encoding="utf-8")
    assert secrets.load(adf.SECRET) == "fake-client-secret"


def test_old_failures_are_not_announced(env):
    env["http"].routes[("POST", ARM_PATH)] = lambda req: (200, {"value": [
        run("PL_Nightly_Load", "Failed", time.time() - 86400, "old")]})
    env["c"]._poll(env["c"].cfg())
    assert env["c"].runs()[0]["status"] == "Failed" and env["store"].alerts == []


def test_errors_become_status_never_exceptions(env, monkeypatch):
    c = env["c"]
    env["http"].routes[("POST", ARM_PATH)] = lambda req: (403, {"error": {"code": "AuthorizationFailed",
                                                                          "message": "The client does not have authorization."}})
    c._poll(c.cfg())
    st = c.status()
    assert st["status"] == "error" and "403" in st["error"] and "authorization" in st["error"]

    c.set_secret("wrong")                                     # sign-in refused
    c._poll(c.cfg())
    assert "Invalid client secret" in c.status()["error"]

    c.set_secret("fake-client-secret")
    monkeypatch.setattr(adf, "TIMEOUT", 0.3)
    monkeypatch.setattr(azure, "TIMEOUT", 0.3)
    env["http"].delay = 1                                     # Azure too slow: gives up quickly
    t = time.time()
    c._poll(c.cfg())
    assert time.time() - t < 3 and c.status()["status"] == "error"


def test_azure_cli_missing(env, monkeypatch):
    env["settings"].set("connectors.adf.auth", "az")
    monkeypatch.setattr(azure.shutil, "which", lambda name: None)
    env["c"]._poll(env["c"].cfg())
    assert "Azure CLI" in env["c"].status()["error"]


def test_azure_cli_token(env, monkeypatch):
    env["settings"].set("connectors.adf.auth", "az")
    calls = []

    def fake_run(args, **kw):
        calls.append(args)
        out = json.dumps({"accessToken": "tok-1", "expires_on": int(time.time()) + 3600})
        return type("R", (), {"returncode": 0, "stdout": out, "stderr": ""})()

    monkeypatch.setattr(azure.shutil, "which", lambda name: "C:/Tools/az.cmd")
    monkeypatch.setattr(azure.subprocess, "run", fake_run)
    env["http"].routes[("POST", ARM_PATH)] = lambda req: (200, {"value": []})
    env["c"]._poll(env["c"].cfg())
    env["c"]._poll(env["c"].cfg())
    assert env["c"].status()["status"] == "ok"
    assert len(calls) == 1 and calls[0][1:5] == ["account", "get-access-token", "--resource", adf.RESOURCE]  # cached


def test_incomplete_configuration_shows_nothing(env):
    env["settings"].set("connectors.adf.pipelines", "")
    assert env["c"].runs() is None and env["c"].status()["configured"] is False
