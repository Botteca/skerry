"""SQL Server / Azure SQL widgets: read-only rules, thresholds, sign-in, errors. A fake pyodbc plays the server."""
import sys
import types

import pytest

from skerry import secrets
from skerry.api import Api
from skerry.connectors import azure, sql
from skerry.settings import Settings


# ---------------------------------------------------------------- read-only rules

@pytest.mark.parametrize("query", [
    "SELECT 1",
    "select count(*) from dbo.Orders where Status = 'Open'",
    "WITH late AS (SELECT * FROM dbo.Orders WHERE DueDate < GETDATE()) SELECT COUNT(*) FROM late",
    "SELECT COUNT(*) FROM dbo.Log WHERE Message = 'DROP TABLE; DELETE'",    # inside a string: data, not a command
    "SELECT [update], [into] FROM dbo.Audit",                                 # bracketed names
    "SELECT 1; -- trailing semicolon and comment",
    "SELECT * FROM dbo.Orders WITH (NOLOCK)",
])
def test_read_only_queries_are_accepted(query):
    assert sql.check_query(query) is None


@pytest.mark.parametrize("query, reason", [
    ("", "sql.err_empty"),
    ("DELETE FROM dbo.Orders", "sql.err_not_select"),
    ("  update dbo.Orders set Status = 'x'", "sql.err_not_select"),
    ("EXEC sp_who2", "sql.err_not_select"),
    ("/* SELECT */ DROP TABLE dbo.Orders", "sql.err_not_select"),
    (";WITH x AS (SELECT 1 a) SELECT a FROM x", "sql.err_not_select"),
    ("SELECT 1; DROP TABLE dbo.Orders", "sql.err_multiple"),
    ("WITH x AS (SELECT 1 a) DELETE FROM dbo.Orders", "sql.err_write"),
    ("SELECT * INTO dbo.Copy FROM dbo.Orders", "sql.err_write"),
    ("SELECT 1 WAITFOR DELAY '00:10:00'", "sql.err_write"),
    ("SELECT * FROM OPENROWSET('SQLNCLI', 'Server=x', 'SELECT 1')", "sql.err_write"),
    ("SELECT 1 /* ; */ ; EXEC xp_cmdshell 'dir'", "sql.err_multiple"),
])
def test_anything_else_is_refused(query, reason):
    assert sql.check_query(query) == reason


def test_thresholds():
    assert [sql.level(v, 10, 20) for v in (5, 10, 25)] == ["green", "amber", "red"]
    assert [sql.level(v, 20, 10) for v in (50, 15, 5)] == ["green", "amber", "red"]    # lower is worse
    assert sql.level(7, None, None) == "green"
    assert sql.level("OK", 1, 2) == "none" and sql.level("OK", None, None) == "green"


# ---------------------------------------------------------------- fake server

class FakeCursor:
    def __init__(self, server):
        self.server = server

    def execute(self, query):
        self.server.queries.append(query)
        if isinstance(self.server.result, Exception):
            raise self.server.result

    def fetchone(self):
        return (self.server.result,)


class FakeConnection:
    def __init__(self, server):
        self.server, self.timeout = server, None

    def cursor(self):
        return FakeCursor(self.server)

    def rollback(self):
        self.server.rolled_back += 1

    def close(self):
        self.server.closed += 1
        self.server.query_timeout = self.timeout


class FakeServer:
    def __init__(self):
        self.result, self.connects, self.queries = 0, [], []
        self.rolled_back = self.closed = 0
        self.login_error = None

    def module(self):
        mod = types.ModuleType("pyodbc")
        mod.drivers = lambda: ["SQL Server", "ODBC Driver 17 for SQL Server", "ODBC Driver 18 for SQL Server"]

        def connect(conn_str, attrs_before=None, timeout=None, autocommit=True):
            self.connects.append({"conn_str": conn_str, "attrs": attrs_before, "timeout": timeout,
                                  "autocommit": autocommit})
            if self.login_error:
                raise self.login_error
            return FakeConnection(self)
        mod.connect = connect
        return mod


class FakeStore:
    def __init__(self):
        self.alerts = []

    def alert(self, level, icon, text, sound=True):
        self.alerts.append(str(text))


class FakeApp:
    def __init__(self, connectors, settings):
        self.connectors, self.settings = connectors, settings


@pytest.fixture
def env(tmp_path, monkeypatch):
    server = FakeServer()
    monkeypatch.setitem(sys.modules, "pyodbc", server.module())
    settings = Settings(str(tmp_path / "settings.json"))
    settings.set("connectors.sql.enabled", True)
    store = FakeStore()
    c = sql.SQL(settings, store)
    connectors = types.SimpleNamespace(sql=c, get=lambda cid: c if cid == "sql" else None)
    return {"server": server, "c": c, "store": store, "settings": settings, "api": Api(FakeApp(connectors, settings)),
            "path": tmp_path / "settings.json"}


def widget(**kw):
    w = {"id": "w1", "name": "Open orders", "server": "SRV-CONTOSO01", "database": "ContosoSales", "auth": "windows",
         "query": "SELECT COUNT(*) FROM dbo.Orders WHERE Status = 'Open'", "warn": 10, "crit": 20, "interval": 60}
    w.update(kw)
    return w


# ---------------------------------------------------------------- saving

def test_unsafe_query_is_never_saved(env):
    r = env["api"].sql_save([widget(), widget(id="w2", query="DELETE FROM dbo.Orders")])
    assert r["ok"] is False and r["errors"]["w2"].startswith("Only queries that start with SELECT or WITH")
    assert env["settings"].get("connectors.sql.widgets") == []                # nothing saved
    assert env["api"].set_setting("connectors.sql.widgets", [widget(query="DROP TABLE x")]) is False   # no bypass
    assert env["api"].sql_save([widget()])["ok"] is True
    assert env["settings"].get("connectors.sql.widgets")[0]["query"].startswith("SELECT")


def test_sql_password_only_in_secrets(env):
    env["api"].sql_save([widget(auth="sql", user="skerry_reader")])
    env["api"].connector_secret("sql", {"id": "w1", "password": "Fake-Passw0rd!"})
    env["c"].poll_widget(env["c"].cfg()["widgets"][0])
    conn = env["server"].connects[-1]["conn_str"]
    assert "UID=skerry_reader" in conn and "PWD=Fake-Passw0rd!" in conn and "Trusted_Connection" not in conn
    assert "Fake-Passw0rd" not in env["path"].read_text(encoding="utf-8")
    assert env["c"].status()["has_password"] == {"w1": True}
    env["api"].sql_save([])                                                    # removing the widget forgets it
    assert secrets.load(sql.secret_name("w1")) is None


# ---------------------------------------------------------------- running

def test_windows_sign_in_read_only_and_timeouts(env):
    env["api"].sql_save([widget()])
    env["server"].result = 12
    env["c"].poll_widget(env["c"].cfg()["widgets"][0])
    call = env["server"].connects[-1]
    assert call["conn_str"].startswith("DRIVER={ODBC Driver 18 for SQL Server};SERVER=SRV-CONTOSO01;")
    assert "Trusted_Connection=yes" in call["conn_str"] and "ApplicationIntent=ReadOnly" in call["conn_str"]
    assert call["autocommit"] is False and call["timeout"] == sql.LOGIN_TIMEOUT
    assert env["server"].query_timeout == sql.QUERY_TIMEOUT
    assert env["server"].rolled_back == 1 and env["server"].closed == 1       # always rolled back and closed
    (w,) = env["c"].widgets()
    assert (w["name"], w["value"], w["level"]) == ("Open orders", 12, "amber")


def test_entra_id_uses_an_access_token(env, monkeypatch):
    monkeypatch.setattr(azure, "token", lambda auth, resource, *a: f"token-for-{resource}")
    env["api"].sql_save([widget(auth="entra", server="sql-contoso.database.windows.net")])
    env["c"].poll_widget(env["c"].cfg()["widgets"][0])
    attrs = env["server"].connects[-1]["attrs"]
    assert attrs == {sql.SQL_COPT_SS_ACCESS_TOKEN: sql.token_struct("token-for-https://database.windows.net/")}
    assert "UID=" not in env["server"].connects[-1]["conn_str"]


def test_red_alerts_once_and_errors_never_raise(env):
    env["api"].sql_save([widget()])
    w = env["c"].cfg()["widgets"][0]
    for value in (5, 50, 60):
        env["server"].result = value
        env["c"].poll_widget(w)
    assert env["store"].alerts == ["Open orders: 50"]                            # on turning red, once
    env["server"].login_error = Exception(
        "('28000', \"[28000] [Microsoft][ODBC Driver 18 for SQL Server][SQL Server]Login failed for user 'skerry_reader'. (18456)\")")
    env["c"].poll_widget(w)
    (shown,) = env["c"].widgets()
    assert shown["level"] == "error" and shown["error"] == "Login failed for user 'skerry_reader'."
    assert env["c"].status()["status"] == "error"


def test_missing_driver_or_library(env, monkeypatch):
    env["api"].sql_save([widget()])
    w = env["c"].cfg()["widgets"][0]
    sys.modules["pyodbc"].drivers = lambda: ["SQL Server"]
    env["c"].poll_widget(w)
    assert "ODBC Driver" in env["c"].widgets()[0]["error"]
    monkeypatch.setitem(sys.modules, "pyodbc", None)                           # import fails
    env["c"].poll_widget(w)
    assert "pyodbc" in env["c"].widgets()[0]["error"]


def test_hand_edited_settings_are_still_checked(env):
    env["settings"].set("connectors.sql.widgets", [widget(query="TRUNCATE TABLE dbo.Orders")])
    env["c"].poll_widget(env["c"].cfg()["widgets"][0])
    assert env["server"].connects == [] and env["c"].widgets()[0]["level"] == "error"
