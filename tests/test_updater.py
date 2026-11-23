"""Updater against a local fake of the GitHub release API (127.0.0.1 only, no internet).

Covers: newer version (download, SHA-256 check, install at a quiet moment), same/older version, pre-releases,
wrong hash, unreachable server, missing assets, ETag (304), notify mode, failures that must keep the app running.
"""
import base64
import hashlib
import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from skerry import updater
from skerry.updater import Updater, compare_versions, installer_command, parse_sums, parse_version

INSTALLER = b"MZ fake installer for tests " * 200
API_PATH = "/repos/example/skerry/releases/latest"


class FakeGitHub:
    def __init__(self):
        self.tag, self.prerelease, self.draft = "v1.2.0", False, False
        self.installer = INSTALLER
        self.sums = None                      # None = correct SHA256SUMS.txt
        self.assets = ("installer", "sums")
        self.etag = '"etag-1"'
        self.hits = {"200": 0, "304": 0, "downloads": 0}
        self.seen_if_none_match = []
        handler = self._handler()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()

    @property
    def version(self):
        return self.tag.lstrip("v")

    @property
    def name(self):
        return f"Skerry-Setup-{self.version}.exe"

    def release(self):
        assets = []
        if "installer" in self.assets:
            assets.append({"name": self.name, "browser_download_url": f"{self.base}/dl/{self.name}"})
        if "sums" in self.assets:
            assets.append({"name": "SHA256SUMS.txt", "browser_download_url": f"{self.base}/dl/SHA256SUMS.txt"})
        return {"tag_name": self.tag, "prerelease": self.prerelease, "draft": self.draft, "assets": assets,
                "html_url": f"https://github.example.invalid/releases/tag/{self.tag}"}

    def _handler(self):
        gh = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _send(self, code, body=b"", headers=None):
                self.send_response(code)
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if self.path == API_PATH:
                    inm = self.headers.get("If-None-Match")
                    gh.seen_if_none_match.append(inm)
                    if inm == gh.etag:
                        gh.hits["304"] += 1
                        return self._send(304)
                    gh.hits["200"] += 1
                    return self._send(200, json.dumps(gh.release()).encode(),
                                      {"ETag": gh.etag, "Content-Type": "application/json"})
                if self.path == "/dl/SHA256SUMS.txt":
                    text = gh.sums if gh.sums is not None else \
                        f"{hashlib.sha256(gh.installer).hexdigest()}  {gh.name}\n"
                    return self._send(200, text.encode())
                if self.path == f"/dl/{gh.name}":
                    gh.hits["downloads"] += 1
                    return self._send(200, gh.installer, {"Content-Type": "application/octet-stream"})
                return self._send(404)

        return Handler

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


class FakeSettings(dict):
    def get(self, key, default=None):
        return super().get(key, default)


class FakeStore:
    def __init__(self):
        self.alerts = []

    def alert(self, level, icon, text, sound=True):
        self.alerts.append(text.key if hasattr(text, "key") else text)


@pytest.fixture
def gh():
    server = FakeGitHub()
    yield server
    server.close()


@pytest.fixture
def make(gh, tmp_path):
    made = []

    def factory(mode="auto", current="1.1.0", can_install=True, url=None, quiet=True, spawn=None):
        env = {"spawned": [], "quit": [], "quiet": quiet, "store": FakeStore(),
               "settings": FakeSettings(updates=mode, update_url=url or gh.base + API_PATH)}
        env["updater"] = Updater(
            env["settings"], env["store"], current=current, can_install=can_install,
            is_quiet=lambda: env["quiet"], quit_app=lambda: env["quit"].append(True),
            cache_file=str(tmp_path / "update-cache.json"), download_dir=str(tmp_path / "dl"),
            spawn=spawn or env["spawned"].append)
        made.append(env)
        return env

    return factory


def wait_for(fn, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if fn():
            return True
        time.sleep(0.02)
    return False


def status(env):
    return env["updater"].public_state()["status"]


def downloads(tmp_path):
    d = tmp_path / "dl"
    return sorted(p.name for p in d.iterdir()) if d.exists() else []


# ------------------------------------------------------------------ version logic

@pytest.mark.parametrize("a, b, expected", [
    ("1.2.0", "1.1.9", 1), ("v1.10.0", "1.9.0", 1), ("1.2.0", "1.2.0", 0), ("1.2.0", "v1.2.0", 0),
    ("1.2.0", "1.2.0-rc.1", 1), ("1.2.0-rc.2", "1.2.0-rc.1", 1), ("1.2.0-rc.10", "1.2.0-rc.9", 1),
    ("1.2.0-alpha", "1.2.0-1", 1), ("1.2.0-alpha.1", "1.2.0-alpha", 1), ("1.0.0", "garbage", 1),
    ("2.0.0", "10.0.0", -1),
])
def test_compare_versions(a, b, expected):
    assert compare_versions(a, b) == expected
    assert compare_versions(b, a) == -expected


def test_parse_version_and_sums():
    assert parse_version("v1.2.3-rc.1+build.5") == ((1, 2, 3), ("rc", 1))
    assert parse_version("1.2") is None
    h = "a" * 64
    assert parse_sums(f"{h}  Skerry-Setup-1.2.0.exe\n{'B' * 64} *other.txt\nnot a line\n") == \
        {"Skerry-Setup-1.2.0.exe": h, "other.txt": "b" * 64}


# ------------------------------------------------------------------ scenarios

def test_newer_version_downloads_verifies_and_installs_when_quiet(gh, make, tmp_path):
    env = make(quiet=False)
    up = env["updater"]
    st = up.check()
    assert st["version"] == "1.2.0" and st["notes_url"].startswith("https://")
    assert wait_for(lambda: status(env) == "ready")
    assert downloads(tmp_path) == ["Skerry-Setup-1.2.0.exe"]
    assert (tmp_path / "dl" / "Skerry-Setup-1.2.0.exe").read_bytes() == INSTALLER
    assert "alert.update_ready" in env["store"].alerts
    assert up.visible_state()["status"] == "ready"

    assert up.maybe_install() is False                      # a permission is waiting / presentation running
    assert env["spawned"] == [] and env["quit"] == []

    env["quiet"] = True
    assert up.maybe_install() is True
    assert status(env) == "installing" and env["quit"] == [True]
    (cmd,) = env["spawned"]
    script = base64.b64decode(cmd[-1]).decode("utf-16-le")
    assert cmd[0] == "powershell.exe" and "-WindowStyle" in cmd
    assert str(tmp_path / "dl" / "Skerry-Setup-1.2.0.exe") in script
    assert "/VERYSILENT" in script and "/SUPPRESSMSGBOXES" in script and "/NORESTART" in script


def test_update_now_installs_immediately(gh, make):
    env = make(quiet=False)
    env["updater"].check()
    assert wait_for(lambda: status(env) == "ready")
    assert env["updater"].install_now() is True             # the user pressed "Update now": no quiet-moment wait
    assert wait_for(lambda: env["quit"] == [True])
    assert len(env["spawned"]) == 1


@pytest.mark.parametrize("current", ["1.2.0", "1.3.0"])
def test_same_or_older_release_is_ignored(gh, make, tmp_path, current):
    env = make(current=current)
    assert env["updater"].check()["status"] == "up_to_date"
    assert env["updater"].visible_state() is None
    assert gh.hits["downloads"] == 0 and downloads(tmp_path) == []


@pytest.mark.parametrize("tag, prerelease, draft", [("v1.2.0", True, False), ("v1.2.0-rc.1", False, False),
                                                    ("v1.2.0", False, True)])
def test_prereleases_and_drafts_are_ignored(gh, make, tag, prerelease, draft):
    gh.tag, gh.prerelease, gh.draft = tag, prerelease, draft
    env = make()
    assert env["updater"].check()["status"] == "up_to_date"
    assert gh.hits["downloads"] == 0


def test_wrong_hash_discards_the_file_and_never_installs(gh, make, tmp_path, caplog):
    gh.sums = f"{'0' * 64}  {gh.name}\n"
    env = make()
    with caplog.at_level(logging.ERROR, logger="skerry"):
        env["updater"].check()
        assert wait_for(lambda: status(env) == "error")
    assert "SHA-256 mismatch" in caplog.text
    assert downloads(tmp_path) == []                        # neither the .part nor the .exe is kept
    assert env["updater"].public_state()["error"]           # translated message for the settings page
    assert env["updater"].maybe_install() is False
    env["updater"].install_now()                            # retries the download, which fails again
    time.sleep(0.5)
    assert env["spawned"] == [] and env["quit"] == []


def test_installer_not_listed_in_sums(gh, make, tmp_path):
    gh.sums = f"{'1' * 64}  something-else.exe\n"
    env = make()
    env["updater"].check()
    assert wait_for(lambda: status(env) == "error")
    assert downloads(tmp_path) == [] and env["spawned"] == []


def test_unreachable_server(make, caplog):
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()                                               # nothing listens there any more
    env = make(url=f"http://127.0.0.1:{port}{API_PATH}")
    with caplog.at_level(logging.WARNING, logger="skerry"):
        st = env["updater"].check()                         # must not raise
    assert st["status"] == "error" and st["last_check"]
    assert "Update check failed" in caplog.text
    assert env["spawned"] == [] and env["quit"] == []


def test_no_release_yet_is_not_an_error(gh, make):
    env = make(url=gh.base + "/repos/example/skerry/releases/none")   # the fake answers 404, like GitHub does
    assert env["updater"].check()["status"] == "up_to_date"


def test_server_error_is_reported(gh, make):
    env = make(url=gh.base + API_PATH)
    gh.httpd.RequestHandlerClass.do_GET = lambda self: self._send(500)
    st = env["updater"].check()
    assert st["status"] == "error" and st["error"]


def test_release_without_assets(gh, make):
    gh.assets = ("installer",)                              # no SHA256SUMS.txt: never install unverified files
    env = make()
    assert env["updater"].check()["status"] == "error"
    assert gh.hits["downloads"] == 0


def test_etag_avoids_downloading_the_release_again(gh, make):
    env = make(mode="notify")
    assert env["updater"].check()["status"] == "available"
    assert env["updater"].check()["status"] == "available"
    assert gh.seen_if_none_match == [None, '"etag-1"']
    assert gh.hits == {"200": 1, "304": 1, "downloads": 0}


def test_notify_mode_only_announces(gh, make, tmp_path):
    env = make(mode="notify")
    assert env["updater"].check()["status"] == "available"
    time.sleep(0.3)
    assert status(env) == "available" and downloads(tmp_path) == []
    assert env["store"].alerts == ["alert.update_available"]
    assert env["updater"].maybe_install() is False


def test_running_from_source_never_downloads(gh, make):
    env = make(can_install=False)
    assert env["updater"].check()["status"] == "available"
    time.sleep(0.3)
    assert gh.hits["downloads"] == 0
    assert env["updater"].install_now() is False


def test_failure_to_start_the_installer_keeps_the_app(gh, make):
    def broken(cmd):
        raise OSError("powershell missing")

    env = make(spawn=broken)
    env["updater"].check()
    assert wait_for(lambda: status(env) == "ready")
    assert env["updater"].maybe_install() is False
    assert status(env) == "error" and env["quit"] == []


def test_installer_changed_after_verification_is_refused(gh, make, tmp_path):
    env = make(quiet=False)
    env["updater"].check()
    assert wait_for(lambda: status(env) == "ready")
    (tmp_path / "dl" / gh.name).write_bytes(b"tampered")
    env["quiet"] = True
    assert env["updater"].maybe_install() is False
    assert env["spawned"] == [] and env["quit"] == []


def test_mode_values(make):
    env = make(mode="bogus")
    assert env["updater"].mode() == "auto"
    env["settings"]["updates"] = "off"
    assert env["updater"].mode() == "off"


def test_installer_command_restarts_the_old_version_on_failure():
    cmd = installer_command(r"C:\Temp\it's\Skerry-Setup-1.2.0.exe", [10, 20], r"C:\Apps\Skerry\Skerry.exe",
                            r"C:\Logs\update.log")
    script = base64.b64decode(cmd[-1]).decode("utf-16-le")
    assert "Wait-Process -Id 10,20" in script
    assert r"'C:\Temp\it''s\Skerry-Setup-1.2.0.exe'" in script     # quotes are escaped for PowerShell
    assert "ExitCode -ne 0" in script and r"'C:\Apps\Skerry\Skerry.exe'" in script
    assert '/LOG="C:\\Logs\\update.log"' in script
    assert "Start-Process" not in installer_command("x.exe", [1], "", "l.log")[-1]  # base64: nothing in clear


def test_cleanup_removes_old_installers(make, tmp_path):
    env = make()
    (tmp_path / "dl").mkdir()
    (tmp_path / "dl" / "Skerry-Setup-1.0.0.exe").write_bytes(b"old")
    env["updater"].cleanup()
    assert downloads(tmp_path) == []


def test_module_constants():
    assert updater.CHECK_EVERY == 6 * 3600
    assert updater.INSTALLER_ARGS == ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"]
    assert set(updater.MODES) == {"auto", "notify", "off"}
