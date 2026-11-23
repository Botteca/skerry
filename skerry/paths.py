"""Application paths (user data, logs, resources) and the one-time migration from older app names."""
import json
import os
import shutil
import sys

APP_DIR_NAME = "Skerry"
# Names used by earlier versions, newest first: data folders and HKCU Run values to migrate/remove.
LEGACY_NAMES = ("Island",)
FROZEN = getattr(sys, "frozen", False)


def _reset_legacy_settings(path):
    """Drop values that pointed at the old project (the defaults take over on load)."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and data.pop("update_url", None) is not None:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
    except (OSError, ValueError):
        pass


def _migrate(root, path):
    """Copy the newest legacy folder into `path`. Runs only while `path` does not exist, so at most once.
    Copy (not move): an older install still running keeps working until it is uninstalled."""
    for name in LEGACY_NAMES:
        legacy = os.path.join(root, name)
        if not os.path.isdir(legacy):
            continue
        tmp = path + ".migrating"
        try:
            shutil.rmtree(tmp, ignore_errors=True)
            shutil.copytree(legacy, tmp, ignore=shutil.ignore_patterns("*.tmp"))
            _reset_legacy_settings(os.path.join(tmp, "settings.json"))
            os.replace(tmp, path)
        except OSError:
            shutil.rmtree(tmp, ignore_errors=True)  # start clean rather than with a half-copied folder
        return


def _app_dir(root):
    path = os.path.join(root, APP_DIR_NAME)
    if not os.path.exists(path):
        _migrate(root, path)
    os.makedirs(path, exist_ok=True)
    return path


def config_dir():
    return _app_dir(os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config"))


def data_dir():
    return _app_dir(os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".local", "share"))


def log_dir():
    path = os.path.join(data_dir(), "logs")
    os.makedirs(path, exist_ok=True)
    return path


def settings_file():
    return os.path.join(config_dir(), "settings.json")


def shelf_file():
    return os.path.join(config_dir(), "shelf.json")


def resource_dir():
    """Folder holding ui/ and assets/ (in development: the project root)."""
    if FROZEN:
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def icon_file():
    return os.path.join(resource_dir(), "assets", "brand", "skerry.ico")


def install_dir():
    """Folder holding the executables (in development: the project root)."""
    return os.path.dirname(sys.executable) if FROZEN else resource_dir()


def python_console():
    """python.exe next to the current interpreter (a console is needed for stdout)."""
    exe = sys.executable
    base, name = os.path.split(exe)
    if name.lower() == "pythonw.exe":
        return os.path.join(base, "python.exe")
    return exe


def python_windowed():
    exe = sys.executable
    base, name = os.path.split(exe)
    if name.lower() == "python.exe" and os.path.exists(os.path.join(base, "pythonw.exe")):
        return os.path.join(base, "pythonw.exe")
    return exe
