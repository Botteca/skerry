"""Notification-area (tray) icon and menu."""
import logging
import os

from . import APP_NAME, VERSION, autostart, paths, profiles
from .i18n import t

log = logging.getLogger("skerry")


def tray_image():
    from PIL import Image, ImageDraw
    ico = paths.icon_file()
    if os.path.exists(ico):
        img = Image.open(ico)
        img.size = max(img.ico.sizes())  # largest frame; pystray scales it down
        return img.convert("RGBA")
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((4, 20, 60, 44), radius=12, fill=(0, 0, 0, 255), outline=(80, 80, 80, 255))
    d.ellipse((42, 27, 52, 37), fill=(217, 119, 87, 255))
    return img


class Tray:
    def __init__(self, app):
        self.app = app
        self.icon = None

    def start(self):
        try:
            import pystray
        except Exception:
            log.warning("pystray not available: no tray icon")
            return
        app = self.app
        item, menu = pystray.MenuItem, pystray.Menu

        def profile_item(name):     # a factory, so each item keeps its own profile name
            return item(lambda i: t(profiles.LABELS[name]), lambda: app.set_profile(name),
                        checked=lambda i: profiles.current(app.settings) == name, radio=True)
        self.icon = pystray.Icon(
            "skerry", tray_image(), APP_NAME,
            menu(
                item(f"{APP_NAME} {VERSION}", None, enabled=False),
                # texts are callables: refresh() re-reads them after a language change
                item(lambda i: t("tray.expand"), lambda: app.toggle_expand(), default=True),
                item(lambda i: t("tray.settings"), lambda: app.open_settings()),
                item(lambda i: t("tray.profile"), menu(*[profile_item(p) for p in profiles.PROFILES])),
                item(lambda i: t("tray.pause"), lambda: app.toggle_pause(), checked=lambda i: app.paused),
                item(lambda i: t("tray.reconnect"), lambda: app.reconnect()),
                item(lambda i: t("tray.autostart"), lambda: app.toggle_autostart(), checked=lambda i: autostart.is_enabled()),
                menu.SEPARATOR,
                item(lambda i: t("tray.install_update", version=app.updater.visible_state()["version"])
                     if app.updater.visible_state() else t("tray.check_updates"), lambda: app.updater.install_now()),
                item(lambda i: t("tray.logs"), lambda: os.startfile(paths.log_dir())),
                menu.SEPARATOR,
                item(lambda i: t("tray.quit"), lambda: app.quit()),
            ))
        self.icon.run_detached()

    def refresh(self):
        if self.icon:
            try:
                self.icon.update_menu()
            except Exception:
                pass

    def notify(self, text):
        if self.icon:
            try:
                self.icon.notify(text, APP_NAME)
            except Exception:
                pass

    def stop(self):
        if self.icon:
            try:
                self.icon.stop()
            except Exception:
                pass
