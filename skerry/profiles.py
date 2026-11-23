"""Profiles (Work / Presentation / Focus): each one is a set of layout, modules, sounds and position.

Switching saves the current values into the profile being left and applies the one being entered, so every
change the user makes while in a profile is remembered there. A profile never used yet starts from the current
values plus its own defaults (DEFAULTS["profiles"]). Optional automatic rule: while the screen is shared or a
meeting is in progress, switch to a chosen profile and come back afterwards.
"""
import copy
import logging

log = logging.getLogger("skerry")

PROFILES = ("work", "present", "focus")
LABELS = {"work": "profile.work", "present": "profile.present", "focus": "profile.focus"}   # i18n keys
KEYS = ("layout", "modules", "sounds", "edge", "offset", "monitor", "monitor_id")


def current(settings):
    p = settings.get("profile", "work")
    return p if p in PROFILES else "work"


def _merge(base, extra):
    out = copy.deepcopy(base)
    for k, v in extra.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else copy.deepcopy(v)
    return out


def switch(settings, name):
    """Switch profile on the fly. Returns True if something changed."""
    if name not in PROFILES or name == current(settings):
        return False
    leaving = current(settings)
    snapshot = {k: settings.get(k) for k in KEYS}
    target = settings.get(f"profiles.{name}") or {}
    values = {f"profiles.{leaving}": snapshot, "profile": name}
    for k in KEYS:
        if k in target:
            v = target[k]
            values[k] = _merge(snapshot[k], v) if isinstance(v, dict) and isinstance(snapshot[k], dict) else v
    settings.update(values)
    log.info("Profile: %s -> %s", leaving, name)
    return True


def cycle(settings):
    """Next profile (keyboard shortcut)."""
    i = PROFILES.index(current(settings))
    return switch(settings, PROFILES[(i + 1) % len(PROFILES)])


class AutoProfile:
    """Automatic rule. `step(active)` is called every few seconds with "screen shared or meeting in progress"."""

    def __init__(self):
        self.previous = None

    def step(self, settings, active):
        cfg = settings.get("profile_auto") or {}
        target = cfg.get("profile")
        if not cfg.get("enabled") or target not in PROFILES:
            active = False
        if active and self.previous is None and current(settings) != target:
            self.previous = current(settings)
            switch(settings, target)
            return "on"
        if not active and self.previous is not None:
            if current(settings) == target:          # the user did not pick another profile meanwhile
                switch(settings, self.previous)
            self.previous = None
            return "off"
        return None
