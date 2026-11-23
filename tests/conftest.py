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

    for name in ("OpenKey", "OpenKeyEx", "CreateKey", "CreateKeyEx", "ConnectRegistry",
                 "SetValue", "SetValueEx", "DeleteKey", "DeleteKeyEx", "DeleteValue"):
        if hasattr(winreg, name):
            monkeypatch.setattr(winreg, name, blocked)
