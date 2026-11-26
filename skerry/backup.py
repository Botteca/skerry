"""Export / import of all settings as JSON. settings.json holds no secrets (they live in secrets/, DPAPI), so the
export has none either. Import accepts only known keys of the right type, never keys that would run a command or
change where updates come from, and checks SQL widgets with the same read-only rule as the settings page.
"""
import copy

from . import VERSION
from .settings import DEFAULTS, _migrate

FORMAT = "skerry-settings"
# Not exported nor imported: a command Skerry runs (chained status line), the update source, and per-PC state.
EXCLUDED = {"chained_statusline", "update_url", "port", "hooks_version", "auto_connect_done", "first_run_done"}
MAX_BYTES = 1_000_000


def export_data(settings):
    data = {k: v for k, v in settings.all().items() if k in DEFAULTS and k not in EXCLUDED}
    return {"format": FORMAT, "version": VERSION, "settings": data}


def _same_type(value, default):
    if isinstance(default, bool):
        return isinstance(value, bool)
    if isinstance(default, (int, float)):
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if default is None:
        return value is None or isinstance(value, str)
    return isinstance(value, type(default))


def _merge(base, extra, defaults):
    out = copy.deepcopy(base)
    for k, v in extra.items():
        d = defaults.get(k) if isinstance(defaults, dict) else None
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v, d or {})
        elif d is None or _same_type(v, d):
            out[k] = copy.deepcopy(v)
    return out


def import_data(settings, payload):
    """Apply an exported file. Returns the number of top-level settings applied; raises ValueError if invalid."""
    if not isinstance(payload, dict) or payload.get("format") != FORMAT or not isinstance(payload.get("settings"), dict):
        raise ValueError("not a Skerry settings file")
    data = _migrate(copy.deepcopy(payload["settings"]))
    values = {}
    for k, v in data.items():
        if k not in DEFAULTS or k in EXCLUDED or not _same_type(v, DEFAULTS[k]):
            continue
        values[k] = _merge(settings.get(k), v, DEFAULTS[k]) if isinstance(v, dict) else v
    sql = (values.get("connectors") or {}).get("sql")
    if isinstance(sql, dict):
        from .connectors.sql import sanitize
        clean, errors = sanitize(sql.get("widgets"))
        sql["widgets"] = [w for w in clean if w["id"] not in errors]   # queries that are not read-only are dropped
    if "links" in values:
        from .links import sanitize as clean_links
        values["links"] = clean_links(values["links"])
    settings.update(values)
    return len(values)
