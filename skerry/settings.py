"""Persistent settings in %APPDATA%\\Skerry\\settings.json."""
import copy
import json
import os
import threading

from . import paths

DEFAULTS = {
    "edge": "top",            # top | bottom | left | right
    "offset": 0.5,            # position along the edge (0..1)
    "monitor": "",            # "" = primary screen, "mouse" = screen with the pointer, else a device name
    "monitor_id": "",         # stable id of the chosen screen (survives docking / device renumbering)
    "language": "auto",       # auto (Windows display language) | en | it
    "theme": "dark",          # dark | light
    "accent": "#d97757",
    "hotkey": "win+alt+i",
    "autostart": True,
    "hide_fullscreen": True,
    "hide_from_capture": True,
    "permission_over_fullscreen": True,
    "port": 47800,
    "permission_wait": 300,
    "focus_terminal_after_decision": True,
    "modules": {
        "claude": True, "codex": True, "gemini": True, "copilot": True, "media": True, "privacy": True,
        "battery": True, "bluetooth": True, "timer": True, "shelf": True, "usage": True, "calendar": True, "adf": True,
    },
    "sounds": {"permission": True, "done": True, "alert": True, "timer": True},
    "alerts": {"context": 80, "limits": [80, 90], "battery_low": 20, "bluetooth_low": 15},
    "pomodoro": {"focus": 25, "short_break": 5, "long_break": 15, "cycles": 4},
    "updates": "auto",        # auto (download, verify, install at a quiet moment) | notify | off
    "update_url": "https://api.github.com/repos/fabrisimo/skerry/releases/latest",
    "chained_statusline": None,
    "auto_connect_done": False,
    "first_run_done": True,   # False only for a brand-new settings file: the island shows the guided setup
    "bluetooth_names": {},   # e.g. {"BLE ·9418": "Mouse", "BLE ·a5f0": ""}  ("" = hide)
    "hooks_version": 0,
    "connectors": {
        "m365": {"client_id": "", "tenant": "organizations", "alert_minutes": 5},
        # Azure Data Factory: no secret here (the service principal secret is in secrets/adf-client-secret.bin)
        "adf": {"enabled": False, "auth": "az", "tenant": "", "client_id": "", "subscription": "",
                "resource_group": "", "factory": "", "pipelines": ""},
    },
}


def _merge(data, defaults):
    for k, v in defaults.items():
        if k not in data:
            data[k] = copy.deepcopy(v)
        elif isinstance(v, dict) and isinstance(data[k], dict):
            _merge(data[k], v)
    return data


def _migrate(data):
    """Rename settings from older versions before the defaults are merged in."""
    if "check_updates" in data:                     # bool before 1.1: off -> "off", on -> the new default
        if "updates" not in data and data["check_updates"] is False:
            data["updates"] = "off"
        del data["check_updates"]
    return data


def load_raw(path=None):
    """Plain read (used by the hook CLI)."""
    path = path or paths.settings_file()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}
    return _merge(_migrate(data) if isinstance(data, dict) else {}, DEFAULTS)


class Settings:
    def __init__(self, path=None):
        self._path = path or paths.settings_file()
        self._lock = threading.RLock()
        self._data = load_raw(self._path)
        self._listeners = []
        self.is_new = not os.path.exists(self._path)
        if self.is_new:
            self._data["first_run_done"] = False      # first launch ever: show the guided setup
            self.save()

    def get(self, key, default=None):
        with self._lock:
            cur = self._data
            for part in key.split("."):
                if not isinstance(cur, dict) or part not in cur:
                    return default
                cur = cur[part]
            return copy.deepcopy(cur)

    def set(self, key, value, save=True):
        with self._lock:
            parts = key.split(".")
            cur = self._data
            for part in parts[:-1]:
                cur = cur.setdefault(part, {})
            if cur.get(parts[-1]) == value:
                return
            cur[parts[-1]] = value
            if save:
                self.save()
        for fn in list(self._listeners):
            try:
                fn(key, value)
            except Exception:
                import logging
                logging.getLogger("skerry").exception("settings listener")

    def update(self, values):
        for k, v in values.items():
            self.set(k, v, save=False)
        self.save()

    def all(self):
        with self._lock:
            return copy.deepcopy(self._data)

    def save(self):
        with self._lock:
            tmp = self._path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
            os.replace(tmp, self._path)

    def on_change(self, fn):
        self._listeners.append(fn)
