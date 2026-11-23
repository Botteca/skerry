"""Layout of the island: which sections the expanded view shows and in what order, what may occupy the closed pill
and in what priority, minimal mode and per-section options. Pure functions on plain data (settings["layout"]).

Ids are stable: settings keep the user's order, unknown ids are dropped and sections added by a later version are
appended at the end in their default position, so a saved order never breaks.
"""

# Expanded island, default order (the order of versions before the Layout page).
# The tuple order is the default order of the expanded island; ids never change (saved orders and profiles use them).
SECTIONS = ("media", "meeting", "adf", "sql", "agents", "limits", "usage", "system", "timer", "shelf")
# Closed pill: what may occupy it when several things happen. "permission" is always first and cannot be hidden.
PILL = ("permission", "agent", "meeting", "media", "timer", "battery")
FIXED_PILL = "permission"
# Minimal mode: only agents (plus permissions and important alerts, which never depend on the layout).
MINIMAL_SECTIONS = ("agents",)
MINIMAL_PILL = ("permission", "agent")
USAGE_VIEWS = ("all", "today")
# modules.<key> of versions before the Layout page -> section id (agents and system keep their own sub-switches)
LEGACY_MODULES = {"media": "media", "calendar": "meeting", "adf": "adf", "sql": "sql", "usage": "usage",
                  "timer": "timer", "shelf": "shelf"}
DEFAULT = {"order": [], "hidden": [], "pill": [], "pill_hidden": [], "minimal": False, "usage_view": "all",
           "meeting_ahead": 720}


def ordered(saved, known):
    """The saved order restricted to known ids (no duplicates), then the missing known ids in default order."""
    seen, out = set(), []
    for i in saved if isinstance(saved, list) else []:
        if i in known and i not in seen:
            seen.add(i)
            out.append(i)
    return out + [i for i in known if i not in seen]


def _ids(values, known):
    return [i for i in dict.fromkeys(values if isinstance(values, list) else []) if i in known]


def resolve(layout):
    """Clean layout for the UI: full orders, valid hidden lists, and what is actually shown now."""
    lay = layout if isinstance(layout, dict) else {}
    order = ordered(lay.get("order"), SECTIONS)
    hidden = _ids(lay.get("hidden"), SECTIONS)
    pill = [FIXED_PILL] + [p for p in ordered(lay.get("pill"), PILL) if p != FIXED_PILL]
    pill_hidden = [p for p in _ids(lay.get("pill_hidden"), PILL) if p != FIXED_PILL]
    minimal = bool(lay.get("minimal"))
    sections = [s for s in order if s not in hidden and (not minimal or s in MINIMAL_SECTIONS)]
    active_pill = [p for p in pill if p not in pill_hidden and (not minimal or p in MINIMAL_PILL)]
    # "tokens" and "percent" date from when limits and tokens shared a section: both now mean "all"
    view = "today" if lay.get("usage_view") == "today" else "all"
    try:
        ahead = max(0, min(1440, int(lay.get("meeting_ahead", DEFAULT["meeting_ahead"]))))
    except (TypeError, ValueError):
        ahead = DEFAULT["meeting_ahead"]
    return {"order": order, "hidden": hidden, "pill": pill, "pill_hidden": pill_hidden, "minimal": minimal,
            "sections": sections, "active_pill": active_pill, "usage_view": view, "meeting_ahead": ahead}


def visible(settings, section):
    """Is a section shown in the expanded island (also used to skip work for hidden sections)?"""
    return section in resolve(settings.get("layout"))["sections"]


def migrate(data):
    """Turn modules.<x> switches of older versions into layout.hidden (in place, on the raw settings dict)."""
    mods = data.get("modules")
    if not isinstance(mods, dict) or not any(k in mods for k in LEGACY_MODULES):
        return data
    lay = data.setdefault("layout", {})
    if not isinstance(lay, dict):
        lay = data["layout"] = {}
    hidden = list(lay.get("hidden") or [])
    for key, section in LEGACY_MODULES.items():
        if mods.pop(key, True) is False and section not in hidden:
            hidden.append(section)
    lay["hidden"] = hidden
    return data
