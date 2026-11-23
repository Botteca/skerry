"""Skerry: a dynamic island for Windows.

Normal start: Skerry.exe (or  pythonw app.py)
The main process is a supervisor that restarts the app if it crashes.
  --child         run the app directly (used by the supervisor)
  --no-supervise  run without the supervisor (development)
"""
import logging
import os
import subprocess
import sys
import threading
import time
import urllib.request

from skerry import APP_ID, APP_NAME, VERSION, autostart, log as logsetup, paths, updater, win32

TITLE = "Skerry overlay"   # internal title: deliberately not just "Skerry" (an Explorer folder could match FindWindow)
SETTINGS_TITLE = "Settings · Skerry"


# ======================= supervisor =======================
def supervise():
    log = logsetup.setup()
    args = [sys.executable] if paths.FROZEN else [sys.executable, os.path.abspath(__file__)]
    args.append("--child")
    crashes = []
    while True:
        log.info("Avvio isola (supervisore pid %s)", os.getpid())
        code = subprocess.call(args, creationflags=0x08000000 if sys.platform == "win32" else 0)
        if code in (0, 3):  # 0 = normal exit, 3 = already running
            log.info("Isola terminata (codice %s)", code)
            return
        now = time.time()
        crashes = [t for t in crashes if now - t < 600] + [now]
        log.error("Isola terminata in modo anomalo (codice %s), crash recenti: %s", code, len(crashes))
        if len(crashes) >= 5:
            log.critical("Troppi crash in 10 minuti: mi fermo")
            return
        time.sleep(2)


# ======================= application =======================
class SkerryApp:
    def __init__(self):
        import webview  # noqa: F401  (early import: fail fast if missing)

        from skerry.api import Api
        from skerry.audio import Audio
        from skerry.media import MediaWatcher
        from skerry.settings import Settings
        from skerry.shelf import Shelf
        from skerry.sounds import Sounds
        from skerry.store import Store
        from skerry.system import SystemMonitor
        from skerry.usage import LocalUsage
        from skerry.timer import Timer
        from skerry.tray import Tray

        self.log = logging.getLogger("skerry")
        self.settings = Settings()
        self.sounds = Sounds(self.settings)
        self.store = Store(self.settings, on_event=self.sounds.play)
        self.media = MediaWatcher()
        self.audio = Audio()
        self.system = SystemMonitor(self.settings, self.store)
        self.usage = LocalUsage(self.settings)
        from skerry.connectors import Connectors
        self.connectors = Connectors(self.settings, self.store)
        self.timer = Timer(self.settings, self.store, on_finish=lambda: self.sounds.play("timer"))
        self.shelf = Shelf()
        self.win = win32.SkerryWindow(TITLE, self.settings)
        self.api = Api(self)
        self.tray = Tray(self)
        self.paused = False
        self.update = None
        self.window = None
        self.settings_window = None
        self.hotkey = None
        self._quitting = False
        self.settings.on_change(self._on_setting)

    # ---------- startup ----------
    def run(self):
        import webview
        from skerry.server import start_server

        try:
            start_server(self.store, self.settings, on_show=self.toggle_expand)
        except OSError:
            self.log.error("Porta %s occupata", self.settings.get("port"))
            raise SystemExit(3)

        self.media.start()
        self.audio.start()
        self.system.start()
        self.usage.start()
        self.connectors.start()
        self.timer.start()
        autostart.remove_legacy()
        if paths.FROZEN:
            # autostart is managed only by the installed app (never by `python app.py`)
            if self.settings.is_new:
                # first run after the installer: honour the choice made during setup
                self.settings.set("autostart", autostart.is_enabled())
            elif self.settings.get("autostart", True) != autostart.is_enabled():
                autostart.set_enabled(self.settings.get("autostart", True))
        self._ensure_integrations()

        self.window = webview.create_window(
            TITLE, url=os.path.join(paths.resource_dir(), "ui", "index.html"), js_api=self.api,
            width=180, height=34, frameless=True, on_top=True, resizable=False,
            background_color="#000000", text_select=False, easy_drag=False, min_size=(20, 20), shadow=False)
        self.window.events.shown += self._on_shown
        self.window.events.loaded += self._on_loaded
        self.log.info("%s %s avviata", APP_NAME, VERSION)
        webview.start(self._after_start, debug=bool(os.environ.get("SKERRY_DEBUG")))
        self._shutdown()

    def _ensure_integrations(self):
        """Connect Claude Code (and Codex, if present) on first run and rewrite the hooks after an update."""
        from skerry import integrations
        try:
            st = integrations.claude_status()
            if st.get("available"):
                outdated = st.get("installed") and self.settings.get("hooks_version", 0) != integrations.HOOKS_VERSION
                if outdated or (not st.get("installed") and not self.settings.get("auto_connect_done", False)):
                    integrations.claude_install(self.settings)
                    self.log.info("Claude Code collegato automaticamente (hook v%s)", integrations.HOOKS_VERSION)
            cx = integrations.codex_status()
            if cx.get("available") and not cx.get("installed") and not self.settings.get("auto_connect_done", False):
                integrations.codex_install(self.settings)
            if cx.get("available") and cx.get("installed") and self.settings.get("hooks_version", 0) != integrations.HOOKS_VERSION:
                integrations.codex_install(self.settings)
            self.settings.update({"auto_connect_done": True, "hooks_version": integrations.HOOKS_VERSION})
        except Exception:
            self.log.exception("Collegamento automatico agenti non riuscito")

    def _after_start(self):
        self.tray.start()
        self._start_hotkey()
        threading.Thread(target=self._guard_loop, daemon=True, name="guard").start()
        threading.Thread(target=self._update_loop, daemon=True, name="updates").start()

    def _on_shown(self):
        self._prepare_form(self.window, release_min_size=True)
        self.win.setup()

    def _prepare_form(self, window, release_min_size=False):
        """Set the window icon and, for the pill, clear the WinForms minimum size
        (without that the pill stays 200x100 times the DPI scale)."""
        try:
            import clr  # noqa: F401  (pythonnet, already required by pywebview)
            from System import Action
            from System.Drawing import Icon, Size
            form = window.native
            ico = paths.icon_file()

            def fn():
                if release_min_size:
                    form.MinimumSize = Size(0, 0)
                if os.path.exists(ico):
                    form.Icon = Icon(ico)

            form.Invoke(Action(fn))
        except Exception:
            self.log.exception("Could not prepare the native window")

    def _on_loaded(self):
        if getattr(self, "_drop_ready", False):
            return
        self._drop_ready = True
        try:
            from webview.dom import DOMEventHandler

            def on_drop(e):
                files = ((e or {}).get("dataTransfer") or {}).get("files") or []
                found = [f.get("pywebviewFullPath") for f in files if f.get("pywebviewFullPath")]
                if found and self.settings.get("modules.shelf", True):
                    self.shelf.add(found)
                    self.log.info("Mensola: aggiunti %s file", len(found))

            doc = self.window.dom.document
            doc.events.dragenter += DOMEventHandler(lambda e: None, True, False)
            doc.events.dragover += DOMEventHandler(lambda e: None, True, False)
            doc.events.drop += DOMEventHandler(on_drop, True, False)
        except Exception:
            self.log.exception("Drag & drop dei file non disponibile")

    def _start_hotkey(self):
        if self.hotkey:
            self.hotkey.stop()
        self.hotkey = win32.Hotkey(self.settings.get("hotkey"), self.toggle_expand)
        self.hotkey.start()

    # ---------- service loops ----------
    def _guard_loop(self):
        """Visibility (pause / fullscreen) and always-on-top."""
        tick = 0
        while not self._quitting:
            try:
                exclude = {self.win.handle()}
                if self.settings_window:
                    exclude.add(win32.user32.FindWindowW(None, SETTINGS_TITLE) if win32.IS_WIN else None)
                full = self.settings.get("hide_fullscreen", True) and win32.is_fullscreen(exclude)
                over = self.settings.get("permission_over_fullscreen", True) and self.store.has_pending()
                self.win.set_visible(not self.paused and (not full or over))
                if self.settings_window and win32.IS_WIN:
                    self.win.capture_hidden(win32.user32.FindWindowW(None, SETTINGS_TITLE))
                if tick % 5 == 0:
                    self.win.keep_on_top()
            except Exception:
                self.log.exception("guard")
            tick += 1
            time.sleep(1)

    def _update_loop(self):
        time.sleep(60)
        while not self._quitting:
            if self.settings.get("check_updates", True):
                self.check_updates()
            time.sleep(24 * 3600)

    # ---------- actions ----------
    def toggle_expand(self):
        self.store.ui_toggle()
        if self.paused:
            self.toggle_pause()

    def toggle_pause(self):
        self.paused = not self.paused
        self.tray.refresh()

    def reconnect(self):
        from skerry import integrations
        try:
            integrations.claude_install(self.settings)
            if integrations.codex_status().get("available"):
                integrations.codex_install(self.settings)
            self.store.alert("info", "🔗", "Claude Code collegato: riavvia le sessioni aperte", sound=False)
        except Exception:
            self.log.exception("Ricollegamento agenti")
            self.store.alert("danger", "🔗", "Collegamento non riuscito (vedi log)")

    def toggle_autostart(self):
        self.settings.set("autostart", not autostart.is_enabled())

    def on_snapped(self, edge, offset, monitor):
        self.settings.update({"edge": edge, "offset": offset, "monitor": monitor})
        self.log.info("Isola agganciata al bordo %s (%.2f) %s", edge, offset, monitor or "principale")

    def open_settings(self):
        import webview
        if self.settings_window:
            try:
                self.settings_window.show()
                self.settings_window.restore()
                return
            except Exception:
                self.settings_window = None
        w = webview.create_window(SETTINGS_TITLE, url=os.path.join(paths.resource_dir(), "ui", "settings.html"),
                                  js_api=self.api, width=820, height=640, min_size=(680, 520),
                                  background_color="#111111")

        def closed():
            self.settings_window = None

        w.events.shown += lambda: self._prepare_form(w)
        w.events.closed += closed
        self.settings_window = w

    def check_updates(self):
        info = updater.check(self.settings.get("update_url"))
        self.update = info
        self.tray.refresh()
        if info:
            self.store.alert("info", "⬆️", f"Disponibile Skerry {info['version']}", sound=False)
        return info

    def update_action(self):
        if not self.update:
            threading.Thread(target=self.check_updates, daemon=True).start()
            return
        if not paths.FROZEN:
            self.store.alert("info", "⬆️", "In sviluppo aggiorna con git pull", sound=False)
            return
        try:
            updater.download_and_run(self.update)
            self.quit()
        except Exception:
            self.log.exception("Aggiornamento")
            self.store.alert("danger", "⬆️", "Aggiornamento non riuscito (vedi log)")

    def _on_setting(self, key, value):
        if key == "autostart":
            autostart.set_enabled(bool(value))
            self.tray.refresh()
        elif key == "hotkey":
            self._start_hotkey()
        elif key in ("edge", "offset", "monitor"):
            self.win.replace()

    def quit(self):
        import webview
        self._quitting = True
        for w in list(webview.windows):
            try:
                w.destroy()
            except Exception:
                pass

    def _shutdown(self):
        self._quitting = True
        self.connectors.stop()
        if self.hotkey:
            self.hotkey.stop()
        self.tray.stop()
        self.log.info("Isola chiusa")


def run_child():
    log = logsetup.setup()
    win32.set_app_id(APP_ID)
    first, _mutex = win32.single_instance()
    if not first:
        # already running: ask the live instance to expand
        try:
            from skerry.settings import load_raw
            port = load_raw()["port"]
            urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{port}/ui/show", data=b"{}",
                                                          headers={"Content-Type": "application/json"}), timeout=2)
        except Exception:
            pass
        log.info("Istanza già attiva")
        sys.exit(3)
    try:
        SkerryApp().run()
    except SystemExit:
        raise
    except Exception:
        log.critical("Errore fatale", exc_info=True)
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    argv = sys.argv[1:]
    if "--child" in argv or "--no-supervise" in argv:
        run_child()
    else:
        supervise()
