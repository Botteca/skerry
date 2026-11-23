"""Shared fixtures. Every test runs with:

- user data folders (APPDATA, LOCALAPPDATA, CLAUDE_CONFIG_DIR) redirected to a temporary directory;
- outbound network blocked (only loopback is allowed);
- the Windows registry blocked (any winreg open/create/write raises).
"""
import ipaddress
import socket
import sys

import pytest


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path, monkeypatch):
    for var in ("APPDATA", "LOCALAPPDATA"):
        d = tmp_path / var.lower()
        d.mkdir()
        monkeypatch.setenv(var, str(d))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    return tmp_path


def _is_loopback(address):
    host = address[0] if isinstance(address, tuple) else address
    if host in ("localhost",):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    real_connect = socket.socket.connect

    def guarded_connect(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6) and not _is_loopback(address):
            raise RuntimeError(f"Network access is not allowed in tests: {address!r}")
        return real_connect(self, address)

    def guarded_getaddrinfo(host, *args, **kwargs):
        if host is not None and not _is_loopback(host):
            raise RuntimeError(f"DNS lookups are not allowed in tests: {host!r}")
        return real_getaddrinfo(host, *args, **kwargs)

    real_getaddrinfo = socket.getaddrinfo
    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)


@pytest.fixture(autouse=True)
def no_registry(monkeypatch):
    if sys.platform != "win32":
        return
    import winreg

    def blocked(*args, **kwargs):
        raise RuntimeError("Registry access is not allowed in tests")

    # urllib reads the system proxy from the registry: tests never use a proxy (they only talk to 127.0.0.1)
    import urllib.request
    monkeypatch.setattr(urllib.request, "getproxies", lambda: {})
    monkeypatch.setattr(urllib.request, "_opener", None)

    for name in ("OpenKey", "OpenKeyEx", "CreateKey", "CreateKeyEx", "ConnectRegistry",
                 "SetValue", "SetValueEx", "DeleteKey", "DeleteKeyEx", "DeleteValue"):
        if hasattr(winreg, name):
            monkeypatch.setattr(winreg, name, blocked)


class FakeHTTP:
    """A local HTTP server standing in for a cloud API. `routes` maps (method, path) to a handler
    `fn(request) -> (status, json_body)`; `requests` records what the client sent."""

    def __init__(self):
        import http.server
        import json
        import threading

        fake = self
        self.routes, self.requests, self.delay = {}, [], 0

        class Handler(http.server.BaseHTTPRequestHandler):
            def _do(self, method):
                import time
                from urllib.parse import parse_qs, urlparse
                url = urlparse(self.path)
                raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                try:
                    body = json.loads(raw) if self.headers.get("Content-Type", "").startswith("application/json") \
                        else {k: v[0] for k, v in parse_qs(raw.decode()).items()}
                except ValueError:
                    body = raw
                req = {"method": method, "path": url.path, "query": {k: v[0] for k, v in parse_qs(url.query).items()},
                       "headers": dict(self.headers), "body": body}
                fake.requests.append(req)
                time.sleep(fake.delay)
                fn = fake.routes.get((method, url.path))
                status, out = fn(req) if fn else (404, {"error": {"message": "no route"}})
                data = json.dumps(out).encode()
                try:
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                except OSError:
                    pass   # the client gave up (timeout tests)

            def do_GET(self):
                self._do("GET")

            def do_POST(self):
                self._do("POST")

            def log_message(self, *args):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()


@pytest.fixture
def fake_http():
    srv = FakeHTTP()
    yield srv
    srv.server.shutdown()
