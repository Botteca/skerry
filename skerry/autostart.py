"""Start with Windows (HKCU\\...\\Run, no admin rights needed)."""
import logging
import os
import sys

from . import APP_NAME, paths

log = logging.getLogger("skerry")
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def command():
    if paths.FROZEN:
        return f'"{sys.executable}"'
    return f'"{paths.python_windowed()}" "{os.path.join(paths.resource_dir(), "app.py")}"'


def remove_legacy():
    """Remove the Run values written by earlier app names (installed builds and dev runs)."""
    if sys.platform != "win32":
        return
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            for name in paths.LEGACY_NAMES:
                try:
                    winreg.DeleteValue(k, name)
                    log.info("Removed legacy autostart entry '%s'", name)
                except OSError:
                    pass
    except OSError:
        pass


def is_enabled():
    if sys.platform != "win32":
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, APP_NAME)
            return True
    except OSError:
        return False


def set_enabled(on):
    if sys.platform != "win32":
        return
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, command())
        else:
            try:
                winreg.DeleteValue(k, APP_NAME)
            except OSError:
                pass
    log.info("Autostart %s", "enabled" if on else "disabled")
