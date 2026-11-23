"""Methods exposed to the UI (window.pywebview.api.*). Only the app's own windows see them:
permission decisions never go through HTTP."""
import logging
import os
import time

from . import VERSION, autostart, i18n, integrations, paths, win32

log = logging.getLogger("skerry")

SETTABLE = {
    "language", "theme", "accent", "hotkey", "autostart", "hide_fullscreen", "hide_from_capture", "permission_over_fullscreen",
    "permission_wait", "focus_terminal_after_decision", "edge", "offset", "monitor", "updates", "update_url",
    "alerts.context", "alerts.limits", "alerts.battery_low", "alerts.bluetooth_low",
    "pomodoro.focus", "pomodoro.short_break", "pomodoro.long_break", "pomodoro.cycles",
    "connectors.m365.client_id", "connectors.m365.tenant", "connectors.m365.alert_minutes",
}


class Api:
    def __init__(self, app):
        self._app = app

    # ---------- state ----------
    def get_state(self):
        a = self._app
        snap = a.store.snapshot()
        mods = a.settings.get("modules", {})
        snap["media"] = a.media.public_state() if mods.get("media", True) else None
        snap["audio"] = a.audio.state()
        snap["system"] = a.system.state
        snap["usage"] = a.usage.state() if mods.get("usage", True) else None
        snap["timer"] = a.timer.state() if mods.get("timer", True) else None
        snap["meeting"] = a.connectors.meeting() if mods.get("calendar", True) else None
        snap["shelf"] = a.shelf.items() if mods.get("shelf", True) else []
        snap["settings"] = {k: a.settings.get(k) for k in ("edge", "monitor", "theme", "accent", "modules")}
        snap["onboarding"] = None if a.settings.get("first_run_done", True) else self._onboarding()
        snap["update"] = a.updater.visible_state()
        snap["version"] = VERSION
        snap["lang"] = i18n.current()
        return snap

    # ---------- guided setup (first run) ----------
    def _onboarding(self):
        """What the guided setup needs. Agent status is read from disk, so it is cached for 2 seconds."""
        cached = getattr(self, "_onb_cache", None)
        if cached and time.time() - cached[0] < 2:
            return cached[1]
        s = self._app.settings
        mons = win32.monitors()
        data = {"hotkey": s.get("hotkey", ""),
                "monitors": [{"value": "" if m["primary"] else m["device"], "index": i + 1, "primary": m["primary"],
                              "width": m["monitor"][2] - m["monitor"][0], "height": m["monitor"][3] - m["monitor"][1]}
                             for i, m in enumerate(mons)],
                "claude": integrations.claude_status(), "codex": integrations.codex_status()}
        self._onb_cache = (time.time(), data)
        return data

    def onboarding_finish(self):
        self._app.settings.set("first_run_done", True)
        log.info("Guided setup finished")
        return True

    def onboarding_restart(self):
        self._onb_cache = None
        self._app.settings.set("first_run_done", False)
        return True

    def get_thumb(self):
        return self._app.media.thumb()

    def log(self, msg):
        log.info("UI: %s", str(msg)[:500])

    # ---------- agents ----------
    def decide(self, pid, behavior):
        if behavior not in ("allow", "always", "deny", "terminal"):
            return False
        res = self._app.store.decide(pid, behavior)
        if isinstance(res, int) and not isinstance(res, bool) and res and \
                self._app.settings.get("focus_terminal_after_decision", True):
            win32.focus_window(res)
        return bool(res)

    def dismiss_alert(self, aid):
        self._app.store.dismiss_alert(aid)

    def cycle_session(self, direction):
        self._app.store.cycle(direction)

    def focus_session(self, sid):
        return win32.focus_window(self._app.store.session_hwnd(sid))

    # ---------- media ----------
    def media(self, cmd):
        return self._app.media.command(cmd)

    def media_seek(self, seconds):
        return self._app.media.seek(seconds)

    def set_volume(self, v):
        self._app.audio.set(v)

    def volume_step(self, delta):
        self._app.audio.step(delta)

    def toggle_mute(self):
        self._app.audio.toggle_mute()

    # ---------- window ----------
    def resize(self, w, h, r):
        self._app.win.animate_to(float(w), float(h), float(r))

    def drag_start(self):
        self._app.win.drag(self._app.on_snapped)

    def open_settings(self):
        self._app.open_settings()

    def quit(self):
        self._app.quit()

    # ---------- timer ----------
    def timer_start(self, minutes):
        self._app.timer.start_timer(minutes)

    def pomodoro_start(self):
        self._app.timer.start_pomodoro()

    def timer_stop(self):
        self._app.timer.stop()

    def timer_toggle_pause(self):
        self._app.timer.toggle_pause()

    # ---------- shelf ----------
    def shelf_copy(self, i):
        p = self._app.shelf.get(int(i))
        return win32.copy_files_to_clipboard([p]) if p and os.path.exists(p) else False

    def shelf_copy_all(self):
        return win32.copy_files_to_clipboard(self._app.shelf.all_paths())

    def shelf_open(self, i):
        self._app.shelf.open(int(i))

    def shelf_reveal(self, i):
        self._app.shelf.reveal(int(i))

    def shelf_remove(self, i):
        self._app.shelf.remove(int(i))

    def shelf_clear(self):
        self._app.shelf.clear()

    # ---------- settings ----------
    def get_settings(self):
        a = self._app
        return {"settings": a.settings.all(), "version": VERSION, "autostart": autostart.is_enabled(),
                "claude": integrations.claude_status(), "codex": integrations.codex_status(),
                "monitors": [m["device"] for m in win32.monitors()], "log_dir": paths.log_dir(),
                "update": a.updater.public_state(), "connectors": a.connectors.states(), "lang": i18n.current()}

    def set_setting(self, key, value):
        if key.startswith("modules.") or key.startswith("sounds.") or key in SETTABLE:
            self._app.settings.set(key, value)
            return True
        return False

    def claude_connect(self, on):
        try:
            (integrations.claude_install if on else integrations.claude_uninstall)(self._app.settings)
            self._onb_cache = None
            return {"ok": True, **integrations.claude_status()}
        except Exception as e:
            log.exception("Connecting Claude Code")
            return {"ok": False, "error": str(e)}

    def codex_connect(self, on):
        try:
            (integrations.codex_install if on else integrations.codex_uninstall)(self._app.settings)
            self._onb_cache = None
            return {"ok": True, **integrations.codex_status()}
        except Exception as e:
            log.exception("Connecting Codex")
            return {"ok": False, "error": str(e)}

    def check_updates(self):
        return self._app.updater.check(manual=True)

    def install_update(self):
        return self._app.updater.install_now()

    def open_release_notes(self):
        """Open the release page of the available update. https only."""
        import webbrowser
        from urllib.parse import urlparse
        url = self._app.updater.public_state().get("notes_url") or ""
        u = urlparse(url)
        if u.scheme != "https" or not u.hostname:
            return False
        webbrowser.open(url)
        return True

    def open_logs(self):
        os.startfile(paths.log_dir())

    # ---------- connectors ----------
    def connector_login(self, cid):
        c = self._app.connectors.get(cid)
        return bool(c and c.login())

    def connector_logout(self, cid):
        c = self._app.connectors.get(cid)
        if c:
            c.logout()
        return bool(c)

    def connector_refresh(self, cid):
        c = self._app.connectors.get(cid)
        if c:
            c.refresh()
        return bool(c)

    def join_meeting(self):
        """Open the current meeting link. https only, never other schemes."""
        import webbrowser
        from urllib.parse import urlparse
        m = self._app.connectors.meeting()
        url = (m or {}).get("join_url", "")
        u = urlparse(url)
        if u.scheme != "https" or not u.hostname:
            return False
        webbrowser.open(url)
        return True
