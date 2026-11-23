"""Automatic updates from GitHub releases.

- Checks the release API at startup and every 6 hours, with an ETag so unchanged answers (HTTP 304) don't use the
  rate limit. Drafts and pre-releases are ignored; versions are compared semantically (1.10.0 > 1.9.0, 1.2.0 > 1.2.0-rc.1).
- Setting `updates`: "auto" (default) downloads the installer, verifies its SHA-256 against SHA256SUMS.txt from the same
  release and installs it at a quiet moment (no pending permission, no fullscreen/presentation) or when the user
  presses "Update now"; "notify" only shows the update; "off" never checks by itself.
- Nothing here ever shows an error window: failures are logged and exposed as a status the UI can show, and the
  running version keeps working.

The installer is started by a hidden PowerShell that first waits for this process (and its supervisor) to exit, so
the installer never finds Skerry running; if the installer fails, the PowerShell starts the current version again.
"""
import base64
import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

from . import VERSION, paths
from .i18n import Msg, render

log = logging.getLogger("skerry")

MODES = ("auto", "notify", "off")
CHECK_EVERY = 6 * 3600
FIRST_CHECK = 30            # seconds after startup
QUIET_POLL = 30             # how often a ready update looks for a quiet moment
TIMEOUT = 20
INSTALLER_RE = re.compile(r"^Skerry-Setup-(.+)\.exe$", re.IGNORECASE)
SUMS_NAME = "SHA256SUMS.txt"
INSTALLER_ARGS = ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"]
VISIBLE = ("available", "downloading", "ready", "installing")   # states the pill shows


# ------------------------------------------------------------------ versions

_SEMVER = re.compile(r"v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?")


def parse_version(text):
    """'v1.2.3-rc.1' -> ((1, 2, 3), ('rc', 1)); None if it is not a semantic version."""
    m = _SEMVER.fullmatch(str(text or "").strip())
    if not m:
        return None
    pre = tuple(int(p) if p.isdigit() else p for p in m.group(4).split(".")) if m.group(4) else ()
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))), pre


def _cmp_pre(a, b):
    if a == b:
        return 0
    if not a:
        return 1              # a release is newer than any of its pre-releases
    if not b:
        return -1
    for x, y in zip(a, b):
        if x == y:
            continue
        if isinstance(x, int) and isinstance(y, int):
            return 1 if x > y else -1
        if isinstance(x, int):
            return -1         # numeric identifiers sort before alphanumeric ones
        if isinstance(y, int):
            return 1
        return 1 if x > y else -1
    return 1 if len(a) > len(b) else -1


def compare_versions(a, b):
    """1 if a > b, -1 if a < b, 0 if equal. Unparseable versions compare as oldest."""
    pa, pb = parse_version(a), parse_version(b)
    if pa is None or pb is None:
        return (pa is not None) - (pb is not None)
    if pa[0] != pb[0]:
        return 1 if pa[0] > pb[0] else -1
    return _cmp_pre(pa[1], pb[1])


def parse_sums(text):
    """SHA256SUMS.txt ('<hex>  <name>' or '<hex> *<name>') -> {name: hex}."""
    out = {}
    for line in str(text).splitlines():
        m = re.match(r"^\s*([0-9a-fA-F]{64})\s+\*?(.+?)\s*$", line)
        if m:
            out[m.group(2)] = m.group(1).lower()
    return out


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ------------------------------------------------------------------ updater

class Updater:
    def __init__(self, settings, store=None, *, current=VERSION, can_install=None, is_quiet=None, on_change=None,
                 quit_app=None, cache_file=None, download_dir=None, spawn=None):
        self._settings = settings
        self._store = store
        self.current = current
        self.can_install = paths.FROZEN if can_install is None else can_install
        self._is_quiet = is_quiet or (lambda: True)
        self._on_change = on_change or (lambda: None)
        self._quit = quit_app or (lambda: None)
        self._cache_file = cache_file or os.path.join(paths.data_dir(), "update-cache.json")
        self._dir = download_dir or os.path.join(tempfile.gettempdir(), "Skerry-update")
        self._spawn = spawn or _spawn_detached
        self._lock = threading.RLock()
        self._busy = threading.Lock()          # one check/download at a time
        self._wake = threading.Event()
        self._stop = False
        self._alerted = set()
        self._release = None                   # {"version", "installer", "sums", "notes_url"}
        self._verified = None                  # (path, sha256) of the downloaded installer
        self._s = {"status": "idle", "version": "", "notes_url": "", "error": "", "last_check": None, "path": ""}

    # ---------- state ----------
    def mode(self):
        m = self._settings.get("updates", "auto")
        return m if m in MODES else "auto"

    def public_state(self):
        with self._lock:
            s = dict(self._s)
        s.pop("path", None)
        s["error"] = render(s["error"])
        s.update(mode=self.mode(), current=self.current, can_install=self.can_install)
        return s

    def visible_state(self):
        """What the pill shows (None when there is nothing to offer)."""
        s = self.public_state()
        return s if s["status"] in VISIBLE else None

    def _set(self, **kw):
        with self._lock:
            self._s.update(kw)
        try:
            self._on_change()
        except Exception:
            log.exception("update state listener")

    def _alert(self, key, version, icon="⬆️"):
        if self._store and (key, version) not in self._alerted:
            self._alerted.add((key, version))
            self._store.alert("info", icon, Msg(key, version=version), sound=False)

    # ---------- network ----------
    def _url(self):
        return self._settings.get("update_url") or ""

    def _open(self, url, headers=None):
        req = urllib.request.Request(url, headers={"User-Agent": f"Skerry/{self.current}", **(headers or {})})
        return urllib.request.urlopen(req, timeout=TIMEOUT)

    def _load_cache(self):
        try:
            with open(self._cache_file, encoding="utf-8") as f:
                c = json.load(f)
            return c if isinstance(c, dict) and c.get("url") == self._url() else {}
        except (OSError, ValueError):
            return {}

    def _save_cache(self, etag, release):
        try:
            tmp = self._cache_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"url": self._url(), "etag": etag, "release": release}, f)
            os.replace(tmp, self._cache_file)
        except OSError:
            log.warning("Could not save the update cache", exc_info=True)

    def _fetch_release(self):
        """Latest release JSON, using the ETag cache (a 304 answer reuses the cached body)."""
        cache = self._load_cache()
        headers = {"Accept": "application/vnd.github+json"}
        if cache.get("etag") and cache.get("release"):
            headers["If-None-Match"] = cache["etag"]
        try:
            with self._open(self._url(), headers) as r:
                release = json.loads(r.read().decode("utf-8"))
                self._save_cache(r.headers.get("ETag"), release)
                return release
        except urllib.error.HTTPError as e:
            if e.code == 304 and cache.get("release"):
                log.debug("Update check: not modified (ETag)")
                return cache["release"]
            raise

    # ---------- check ----------
    def check(self, manual=False):
        """Check for a newer release. In auto mode a download starts in the background. Never raises."""
        if not self._busy.acquire(blocking=False):
            return self.public_state()
        try:
            return self._check(manual)
        finally:
            self._busy.release()

    def _check(self, manual):
        if self._s["status"] in ("ready", "installing"):
            return self.public_state()
        if not self._url():
            self._set(status="idle")
            return self.public_state()
        self._set(status="checking", error="")
        try:
            release = self._fetch_release()
        except urllib.error.HTTPError as e:
            if e.code != 404:
                log.warning("Update check failed: HTTP %s", e.code)
                self._set(status="error", error=Msg("update.err_check"), last_check=time.time())
                return self.public_state()
            log.info("Update check: no published release yet")      # GitHub answers 404 before the first release
            release = None
        except Exception as e:
            log.warning("Update check failed: %s", e)
            self._set(status="error", error=Msg("update.err_check"), last_check=time.time())
            return self.public_state()
        now = time.time()
        info = self._evaluate(release)
        if info is None:
            self._release = None
            self._set(status="up_to_date", version="", notes_url="", last_check=now)
            return self.public_state()
        if isinstance(info, Msg):
            self._set(status="error", error=info, last_check=now)
            return self.public_state()
        self._release = info
        self._set(status="available", version=info["version"], notes_url=info["notes_url"], last_check=now)
        if info["version"] != getattr(self, "_logged", None):                  # once per version, not every 6 h
            self._logged = info["version"]
            log.info("Update available: %s (installed %s, mode %s)", info["version"], self.current, self.mode())
        if self.mode() == "auto" and self.can_install:
            threading.Thread(target=self.download, daemon=True, name="update-download").start()
        else:
            self._alert("alert.update_available", info["version"])
        return self.public_state()

    def _evaluate(self, release):
        """None if nothing newer, a Msg on a broken release, else the update info."""
        if not isinstance(release, dict) or release.get("draft") or release.get("prerelease"):
            return None
        tag = str(release.get("tag_name") or "")
        parsed = parse_version(tag)
        if parsed is None or parsed[1]:                    # pre-release tag on a "latest" release: ignore too
            return None
        if compare_versions(tag, self.current) <= 0:
            return None
        version = tag.lstrip("vV")
        assets = {a.get("name", ""): a.get("browser_download_url", "") for a in release.get("assets") or []
                  if isinstance(a, dict)}
        installer = next((n for n in assets if (m := INSTALLER_RE.match(n)) and m.group(1) == version), None)
        if not installer or not assets.get(SUMS_NAME):
            log.warning("Release %s has no installer or %s", tag, SUMS_NAME)
            return Msg("update.err_assets")
        notes = str(release.get("html_url") or "")
        return {"version": version, "installer": (installer, assets[installer]), "sums": assets[SUMS_NAME],
                "notes_url": notes if notes.startswith("https://") else ""}

    # ---------- download ----------
    def download(self):
        """Download and verify the installer. True when it is ready to install. Never raises."""
        info = self._release
        if not info:
            return False
        name, url = info["installer"]
        final = os.path.join(self._dir, name)
        part = final + ".part"
        self._set(status="downloading")
        try:
            os.makedirs(self._dir, exist_ok=True)
            with self._open(info["sums"]) as r:
                expected = parse_sums(r.read(65536).decode("utf-8", "replace")).get(name)
            if not expected:
                raise ValueError(f"{name} is not listed in {SUMS_NAME}")
            h = hashlib.sha256()
            with self._open(url) as r, open(part, "wb") as f:
                for chunk in iter(lambda: r.read(1 << 16), b""):
                    h.update(chunk)
                    f.write(chunk)
        except Exception as e:
            log.warning("Update download failed: %s", e)
            _remove(part)
            self._set(status="error", error=Msg("update.err_download"))
            return False
        if h.hexdigest() != expected:
            _remove(part)
            log.error("Update %s discarded: SHA-256 mismatch (expected %s, got %s)", info["version"], expected,
                      h.hexdigest())
            self._set(status="error", error=Msg("update.err_hash"))
            return False
        os.replace(part, final)
        self._verified = (final, expected)
        log.info("Update %s downloaded and verified (%s)", info["version"], expected)
        self._set(status="ready", path=final)
        self._alert("alert.update_ready", info["version"])
        return True

    # ---------- install ----------
    def install_now(self):
        """'Update now': install a ready update, downloading it first if needed. Runs in the background."""
        if not self.can_install:
            if self._store:
                self._store.alert("info", "⬆️", Msg("alert.update_dev"), sound=False)
            return False
        st = self._s["status"]
        if st == "ready":
            threading.Thread(target=self._install, daemon=True, name="update-install").start()
            return True
        if st in ("available", "error") and self._release:
            threading.Thread(target=lambda: self.download() and self._install(), daemon=True,
                             name="update-install").start()
            return True
        if st in ("idle", "up_to_date", "error"):
            threading.Thread(target=self.check, args=(True,), daemon=True, name="update-check").start()
        return False

    def maybe_install(self):
        """Auto mode: install a ready update when nothing important is going on."""
        if self.mode() != "auto" or self._s["status"] != "ready" or not self.can_install:
            return False
        try:
            quiet = self._is_quiet()
        except Exception:
            log.exception("quiet-moment check")
            return False
        if not quiet:
            return False
        return self._install()

    def _install(self):
        path = self._s.get("path")
        if not path or not os.path.exists(path):
            self._set(status="error", error=Msg("update.err_install"))
            return False
        try:
            if self._verified != (path, sha256_file(path)):      # the file could have changed on disk since
                raise ValueError("installer changed after verification")
            cmd = installer_command(path, _pids_to_wait(), sys.executable if paths.FROZEN else "",
                                    os.path.join(paths.log_dir(), "update-install.log"))
            self._set(status="installing")
            log.info("Installing update %s: the app restarts after the installer", self._s["version"])
            self._spawn(cmd)
        except Exception:
            log.exception("Could not start the update installer")
            self._set(status="error", error=Msg("update.err_install"))
            return False
        self._quit()
        return True

    # ---------- loop ----------
    def wake(self):
        self._wake.set()

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="updates").start()

    def stop(self):
        self._stop = True
        self._wake.set()

    def _loop(self):
        self.cleanup()
        if self._wake.wait(FIRST_CHECK):
            self._wake.clear()
        next_check = 0
        while not self._stop:
            try:
                if self.mode() != "off" and time.time() >= next_check:
                    self.check()
                    next_check = time.time() + CHECK_EVERY
                self.maybe_install()
            except Exception:
                log.exception("update loop")
            if self._wake.wait(QUIET_POLL):          # woken by a mode change: check again now
                self._wake.clear()
                if self._s["status"] in ("idle", "up_to_date", "error", "available"):
                    next_check = 0

    def cleanup(self):
        """Delete installers left from earlier updates."""
        try:
            for n in os.listdir(self._dir):
                _remove(os.path.join(self._dir, n))
        except OSError:
            pass


# ------------------------------------------------------------------ helpers

def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


def _pids_to_wait():
    """This process, plus the supervisor when it is our own executable (Skerry.exe started us with --child)."""
    pids = [os.getpid()]
    try:
        import psutil
        parent = psutil.Process(os.getppid())
        if os.path.normcase(parent.exe()) == os.path.normcase(sys.executable):
            pids.append(parent.pid)
    except Exception:
        pass
    return pids


def _ps_quote(s):
    return "'" + str(s).replace("'", "''") + "'"


def installer_command(installer, pids, restart_exe, log_file):
    """Hidden PowerShell: wait for Skerry to exit, run the installer silently, start the old version if it failed."""
    args = ", ".join(_ps_quote(a) for a in INSTALLER_ARGS + [f'/LOG="{log_file}"'])
    script = (
        "$ErrorActionPreference = 'SilentlyContinue'; "
        f"Wait-Process -Id {','.join(str(int(p)) for p in pids)} -Timeout 60; "
        f"$p = Start-Process -FilePath {_ps_quote(installer)} -ArgumentList {args} -PassThru -Wait; "
        + (f"if ($p -eq $null -or $p.ExitCode -ne 0) {{ Start-Process -FilePath {_ps_quote(restart_exe)} }}"
           if restart_exe else "")
    )
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    return ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
            "-WindowStyle", "Hidden", "-EncodedCommand", encoded]


def _spawn_detached(cmd):
    flags = 0x08000000 | 0x00000200 if sys.platform == "win32" else 0   # CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(cmd, creationflags=flags, close_fds=True, stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
