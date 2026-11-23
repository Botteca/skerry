"""SQL Server and Azure SQL widgets: a read-only query per widget, its first value shown green/amber/red.

Read-only is enforced three times: `check_query()` accepts only one SELECT/WITH statement with no writing keyword
(after removing comments and string literals), the connection runs with autocommit off and every query is rolled
back, and the guide asks for a login that can only read (db_datareader).

Sign-in per widget: Windows (integrated), SQL login (password encrypted in `skerry.secrets`, never in
settings.json) or Microsoft Entra ID (Azure CLI token). Polled in a background thread with login and query
timeouts: errors only change the widget status, they never block the island.
"""
import logging
import re
import struct
import threading
import time

from .. import secrets
from ..i18n import Msg, render
from . import azure

log = logging.getLogger("skerry")

MAX_WIDGETS = 8
LOGIN_TIMEOUT = 10          # seconds to connect
QUERY_TIMEOUT = 15          # seconds for the query
MIN_INTERVAL = 30
SQL_RESOURCE = "https://database.windows.net/"
SQL_COPT_SS_ACCESS_TOKEN = 1256
DRIVERS = ("ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server")
AUTHS = ("windows", "sql", "entra")
WRITES = re.compile(r"\b(insert|update|delete|merge|drop|alter|create|truncate|exec|execute|grant|revoke|deny|"
                    r"backup|restore|dbcc|shutdown|kill|reconfigure|bulk|openrowset|opendatasource|openquery|"
                    r"into|use|declare|set|waitfor)\b", re.I)
_STRIP = re.compile(r"--[^\n]*|/\*.*?\*/|'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"|\[(?:[^\]]|\]\])*\]", re.S)


def check_query(query):
    """None if the query is a single read-only SELECT/WITH, else the key of the reason (a translation key)."""
    q = str(query or "").strip()
    if not q:
        return "sql.err_empty"
    code = _STRIP.sub(" ", q).strip().rstrip(";").strip()
    if not re.match(r"(select|with)\b", code, re.I):
        return "sql.err_not_select"
    if ";" in code:
        return "sql.err_multiple"
    if WRITES.search(code):
        return "sql.err_write"
    return None


def level(value, warn, crit):
    """'green' | 'amber' | 'red' | 'none' (None thresholds = always green). crit < warn means lower values are worse."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "green" if warn is None and crit is None else "none"   # text value: thresholds do not apply
    if crit is not None and warn is not None and crit < warn:
        return "red" if v <= crit else "amber" if v <= warn else "green"
    if crit is not None and v >= crit:
        return "red"
    if warn is not None and v >= warn:
        return "amber"
    return "green"


def _num(v):
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def sanitize(widgets):
    """Validated copy of the widgets coming from the UI: (widgets, {id: error key})."""
    out, errors = [], {}
    for w in (widgets or [])[:MAX_WIDGETS]:
        if not isinstance(w, dict):
            continue
        wid = str(w.get("id") or "")
        if not re.fullmatch(r"[a-z0-9]{1,24}", wid):
            continue
        clean = {"id": wid, "name": str(w.get("name") or "").strip()[:60],
                 "server": str(w.get("server") or "").strip()[:200], "database": str(w.get("database") or "").strip()[:128],
                 "auth": w.get("auth") if w.get("auth") in AUTHS else "windows",
                 "user": str(w.get("user") or "").strip()[:128], "trust_cert": bool(w.get("trust_cert")),
                 "query": str(w.get("query") or "").strip()[:4000],
                 "warn": _num(w.get("warn")), "crit": _num(w.get("crit")),
                 "interval": max(MIN_INTERVAL, int(_num(w.get("interval")) or 60))}
        err = check_query(clean["query"])
        if err and clean["query"]:
            errors[wid] = err
        out.append(clean)
    return out, errors


def secret_name(wid):
    return f"sql-{wid}-password"


def _escape(value):
    """ODBC connection-string value: braces when it contains special characters."""
    value = str(value)
    return "{" + value.replace("}", "}}") + "}" if re.search(r"[;{}=\s]", value) else value


def connection_string(w, driver):
    parts = [f"DRIVER={{{driver}}}", f"SERVER={_escape(w['server'])}", "Encrypt=yes",
             "ApplicationIntent=ReadOnly", "APP=Skerry"]
    if w["database"]:
        parts.append(f"DATABASE={_escape(w['database'])}")
    if w["trust_cert"]:
        parts.append("TrustServerCertificate=yes")
    if w["auth"] == "windows":
        parts.append("Trusted_Connection=yes")
    elif w["auth"] == "sql":
        parts += [f"UID={_escape(w['user'])}", f"PWD={_escape(secrets.load(secret_name(w['id'])) or '')}"]
    return ";".join(parts)


def token_struct(token):
    """Access token in the format SQL_COPT_SS_ACCESS_TOKEN expects: length + UTF-16-LE bytes."""
    raw = token.encode("utf-16-le")
    return struct.pack("<I", len(raw)) + raw


def _connect(conn_str, attrs):
    """pyodbc connection (separate function so tests can replace it with a fake server)."""
    import pyodbc
    driver = next((d for d in DRIVERS if d in pyodbc.drivers()), None)
    if not driver:
        raise azure.AzureError(Msg("sql.err_driver"))
    cn = pyodbc.connect(conn_str.replace("DRIVER={?}", f"DRIVER={{{driver}}}"), attrs_before=attrs,
                        timeout=LOGIN_TIMEOUT, autocommit=False)
    cn.timeout = QUERY_TIMEOUT
    return cn


def run_widget(w):
    """First value of the first row. Raises on error (the caller turns it into a status)."""
    err = check_query(w["query"])
    if err:
        raise azure.AzureError(Msg(err))
    if not w["server"]:
        raise azure.AzureError(Msg("sql.err_server"))
    if w["auth"] == "sql" and not (w["user"] and secrets.load(secret_name(w["id"]))):
        raise azure.AzureError(Msg("sql.err_login"))
    attrs = {}
    if w["auth"] == "entra":
        attrs[SQL_COPT_SS_ACCESS_TOKEN] = token_struct(azure.token("az", SQL_RESOURCE))
    cn = _connect(connection_string(w, "?"), attrs)
    try:
        cur = cn.cursor()
        cur.execute(w["query"])
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        try:
            cn.rollback()
        finally:
            cn.close()


def _short_error(e):
    text = str(e)
    m = re.findall(r"\[SQL Server\]([^\[\]()]+)", text) or re.findall(r"\]([^\[\]]+)\s*\(\d+\)", text)
    return " ".join((m[-1] if m else text).split())[:160]


class SQL:
    def __init__(self, settings, store):
        self._settings = settings
        self._store = store
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = False
        self._results = {}     # id -> {"value", "level", "error", "at"}
        self._next = {}

    def cfg(self):
        c = self._settings.get("connectors.sql", {}) or {}
        widgets, _ = sanitize(c.get("widgets"))
        return {"enabled": bool(c.get("enabled")), "widgets": widgets}

    def save(self, widgets):
        """Save the widgets from settings; nothing is saved while a query is not read-only."""
        clean, errors = sanitize(widgets)
        if errors:
            return {"ok": False, "errors": errors}
        before = {w["id"] for w in self.cfg()["widgets"]}
        self._settings.set("connectors.sql.widgets", clean)
        gone = before - {w["id"] for w in clean}
        with self._lock:
            for wid in gone:
                self._results.pop(wid, None)
        for wid in gone:                                  # a removed widget leaves no password behind
            secrets.delete(secret_name(wid))
        self.refresh()
        return {"ok": True, "errors": {}}

    def set_secret(self, value):
        """value = {"id": widget id, "password": "..."} (empty password deletes it)."""
        wid = str((value or {}).get("id") or "")
        if not re.fullmatch(r"[a-z0-9]{1,24}", wid):
            return
        pwd = str((value or {}).get("password") or "")
        if pwd:
            secrets.save(secret_name(wid), pwd)
        else:
            secrets.delete(secret_name(wid))
        self.refresh()

    def status(self):
        c = self.cfg()
        with self._lock:
            res = {wid: {**r, "error": render(r["error"])} for wid, r in self._results.items()}
        errors = [r for r in res.values() if r["error"]]
        status = "off" if not c["enabled"] else "error" if errors else "ok" if res else "checking"
        return {"configured": bool(c["widgets"]), "status": status, "error": errors[0]["error"] if errors else "",
                "updated": max((r["at"] for r in res.values()), default=0), "results": res,
                "has_password": {w["id"]: secrets.load(secret_name(w["id"])) is not None
                                 for w in c["widgets"] if w["auth"] == "sql"}}

    def widgets(self):
        """What the island shows, or None when off."""
        c = self.cfg()
        if not c["enabled"] or not c["widgets"]:
            return None
        with self._lock:
            out = []
            for w in c["widgets"]:
                r = self._results.get(w["id"]) or {}
                v = r.get("value")
                out.append({"id": w["id"], "name": w["name"] or w["database"] or w["server"],
                            "value": v if isinstance(v, (int, float, str)) or v is None else str(v),
                            "level": r.get("level") or "none", "error": render(r.get("error") or ""),
                            "at": r.get("at") or 0})
            return out

    def refresh(self):
        self._next.clear()
        self._wake.set()

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="sql").start()

    def stop(self):
        self._stop = True
        self._wake.set()

    def poll_widget(self, w):
        prev = (self._results.get(w["id"]) or {}).get("level")
        try:
            value = run_widget(w)
            lv, err = level(value, w["warn"], w["crit"]), ""
        except azure.AzureError as e:
            value, lv, err = None, "error", e.msg
        except ImportError:
            value, lv, err = None, "error", Msg("sql.err_pyodbc")
        except Exception as e:
            value, lv, err = None, "error", _short_error(e)
            log.warning("SQL widget %s: %s", w["id"], _short_error(e))
        with self._lock:
            self._results[w["id"]] = {"value": value, "level": lv, "error": err, "at": time.time()}
        if lv == "red" and prev not in ("red", None):
            self._store.alert("danger", "🗄️", Msg("alert.sql_red", name=w["name"] or w["database"], value=value))

    def _loop(self):
        time.sleep(6)
        while not self._stop:
            try:
                c = self.cfg()
                if c["enabled"]:
                    for w in c["widgets"]:
                        if time.time() >= self._next.get(w["id"], 0):
                            self.poll_widget(w)
                            self._next[w["id"]] = time.time() + w["interval"]
            except Exception:
                log.exception("sql loop")
            if self._wake.wait(5):
                self._wake.clear()
