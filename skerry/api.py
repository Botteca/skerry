"""Methods exposed to the UI (window.pywebview.api.*). Only the app's own windows see them:
permission decisions never go through HTTP."""
import logging
import os

from . import VERSION, autostart, integrations, paths, win32

log = logging.getLogger("skerry")

SETTABLE = {
    "theme", "accent", "hotkey", "autostart", "hide_fullscreen", "hide_from_capture", "permission_over_fullscreen",
    "permission_wait", "focus_terminal_after_decision", "edge", "offset", "check_updates", "update_url",
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
        snap["settings"] = {k: a.settings.get(k) for k in ("edge", "theme", "accent", "modules")}
        snap["update"] = a.update
        snap["version"] = VERSION
        return snap

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
                "update": a.update, "connectors": a.connectors.states()}

    def set_setting(self, key, value):
        if key.startswith("modules.") or key.startswith("sounds.") or key in SETTABLE:
            self._app.settings.set(key, value)
            return True
        return False

    def claude_connect(self, on):
        try:
            (integrations.claude_install if on else integrations.claude_uninstall)(self._app.settings)
            return {"ok": True, **integrations.claude_status()}
        except Exception as e:
            log.exception("Collegamento Claude Code")
            return {"ok": False, "error": str(e)}

    def codex_connect(self, on):
        try:
            (integrations.codex_install if on else integrations.codex_uninstall)(self._app.settings)
            return {"ok": True, **integrations.codex_status()}
        except Exception as e:
            log.exception("Collegamento Codex")
            return {"ok": False, "error": str(e)}

    def check_updates(self):
        return self._app.check_updates()

    def install_update(self):
        self._app.update_action()

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
