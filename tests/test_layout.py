"""Island layout (order, visibility, closed-pill priority, minimal mode), migration of modules.*, profiles that
switch on the fly, and settings export/import."""
import json

import pytest

from skerry import backup, layout, profiles, secrets
from skerry.settings import Settings


@pytest.fixture
def settings(tmp_path):
    return Settings(str(tmp_path / "settings.json"))


# ---------------------------------------------------------------- order and visibility

def test_saved_order_with_unknown_missing_and_duplicate_ids():
    saved = ["shelf", "removed-in-v2", "agents", "shelf", 42, "media"]
    out = layout.ordered(saved, layout.SECTIONS)
    assert out[:3] == ["shelf", "agents", "media"]                     # the user's order, cleaned
    assert out[3:] == [s for s in layout.SECTIONS if s not in ("shelf", "agents", "media")]   # the rest, default order
    assert sorted(out) == sorted(layout.SECTIONS)


def test_sections_added_by_a_later_version_appear_at_the_end(monkeypatch):
    saved = ["timer", "agents", "media"]
    monkeypatch.setattr(layout, "SECTIONS", layout.SECTIONS + ("weather",))
    out = layout.resolve({"order": saved})["order"]
    assert out[:3] == saved and out[-1] == "weather"


def test_empty_or_broken_layout_falls_back_to_defaults():
    for bad in (None, "oops", {"order": "x", "hidden": 5, "pill": None, "usage_view": "pie", "meeting_ahead": "soon"}):
        r = layout.resolve(bad)
        assert r["order"] == list(layout.SECTIONS) and r["hidden"] == [] and r["sections"] == list(layout.SECTIONS)
        assert r["pill"] == list(layout.PILL) and r["usage_view"] == "all" and r["meeting_ahead"] == 720


def test_hidden_sections_and_pill_priority():
    r = layout.resolve({"order": ["agents", "media"], "hidden": ["media", "nope"],
                        "pill": ["media", "permission", "agent"], "pill_hidden": ["permission", "battery"]})
    assert r["sections"][0] == "agents" and "media" not in r["sections"]
    assert r["hidden"] == ["media"]
    assert r["pill"][:3] == ["permission", "media", "agent"]          # permissions always first
    assert r["pill_hidden"] == ["battery"]                              # ... and cannot be hidden
    assert r["active_pill"][0] == "permission" and "battery" not in r["active_pill"]


def test_minimal_mode_keeps_agents_and_permissions():
    r = layout.resolve({"minimal": True, "order": ["media", "agents"]})
    assert r["sections"] == ["agents"] and r["active_pill"] == ["permission", "agent"]
    assert layout.resolve({"minimal": True, "hidden": ["agents"]})["sections"] == []


def test_visible_follows_the_settings(settings):
    assert layout.visible(settings, "usage")
    settings.set("layout.hidden", ["usage"])
    assert not layout.visible(settings, "usage")


# ---------------------------------------------------------------- migration from modules.*

def test_old_module_switches_become_hidden_sections(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"modules": {"media": False, "calendar": False, "timer": True, "claude": False,
                                            "bluetooth": False}}), encoding="utf-8")
    s = Settings(str(path))
    assert s.get("layout.hidden") == ["media", "meeting"]
    assert s.get("modules") == {"claude": False, "bluetooth": False, "codex": True, "gemini": True, "copilot": True,
                                "privacy": True, "battery": True}          # agent/system switches stay
    s.set("theme", "light")                                              # saved once: migration does not repeat
    again = Settings(str(path))
    assert again.get("layout.hidden") == ["media", "meeting"]


def test_migration_merges_with_an_existing_layout():
    data = layout.migrate({"modules": {"shelf": False, "usage": False}, "layout": {"hidden": ["usage"]}})
    assert data["layout"]["hidden"] == ["usage", "shelf"] and data["modules"] == {}


# ---------------------------------------------------------------- profiles

def test_profile_switches_on_the_fly_and_remembers_changes(settings):
    seen = []
    settings.on_change(lambda k, v: seen.append(k))
    settings.update({"edge": "bottom", "sounds.done": True})
    assert profiles.switch(settings, "present") is True
    assert settings.get("profile") == "present"
    assert settings.get("layout.minimal") is True and settings.get("sounds.done") is False   # profile defaults
    assert settings.get("edge") == "bottom"                             # not in the profile: unchanged
    assert "layout" in seen and "sounds" in seen                        # listeners fire: the island updates live

    settings.set("edge", "left")                                        # a change made while presenting...
    profiles.switch(settings, "work")
    assert settings.get("layout.minimal") is False and settings.get("sounds.done") is True and settings.get("edge") == "bottom"
    profiles.switch(settings, "present")
    assert settings.get("edge") == "left"                               # ... is remembered by that profile
    assert profiles.switch(settings, "present") is False and profiles.switch(settings, "nope") is False


def test_cycle_goes_through_all_profiles(settings):
    names = []
    for _ in profiles.PROFILES:
        profiles.cycle(settings)
        names.append(profiles.current(settings))
    assert names == ["present", "focus", "work"]


def test_automatic_profile_on_and_back(settings):
    auto = profiles.AutoProfile()
    assert auto.step(settings, True) is None                           # rule off: nothing happens
    settings.update({"profile_auto.enabled": True, "profile_auto.profile": "present"})
    assert auto.step(settings, True) == "on" and profiles.current(settings) == "present"
    assert auto.step(settings, True) is None
    assert auto.step(settings, False) == "off" and profiles.current(settings) == "work"

    auto.step(settings, True)
    profiles.switch(settings, "focus")                                  # the user picks a profile meanwhile
    auto.step(settings, False)
    assert profiles.current(settings) == "focus"                        # ... and it is kept


# ---------------------------------------------------------------- export / import

def test_export_has_no_secrets_and_no_commands(settings):
    secrets.save("adf-client-secret", "fake-client-secret")
    settings.update({"chained_statusline": "custom-status.exe", "layout.order": ["agents"]})
    out = backup.export_data(settings)
    text = json.dumps(out)
    assert out["format"] == backup.FORMAT and out["settings"]["layout"]["order"] == ["agents"]
    assert "fake-client-secret" not in text and "chained_statusline" not in text and "update_url" not in text


def test_import_applies_known_values_only(settings, tmp_path):
    payload = {"format": backup.FORMAT, "settings": {
        "theme": "light", "edge": 3,                                      # wrong type: ignored
        "chained_statusline": "evil.exe", "update_url": "https://example.invalid/x",   # never imported
        "modules": {"media": False},                                      # an old export: migrated
        "layout": {"order": ["timer", "agents"]},
        "connectors": {"sql": {"widgets": [
            {"id": "w1", "name": "Open orders", "server": "SRV-CONTOSO01", "query": "SELECT COUNT(*) FROM dbo.Orders"},
            {"id": "w2", "name": "Bad", "server": "SRV-CONTOSO01", "query": "DELETE FROM dbo.Orders"}]}},
        "unknown": 1}}
    backup.import_data(settings, payload)
    assert settings.get("theme") == "light" and settings.get("edge") == "top"
    assert settings.get("chained_statusline") is None and "example.invalid" not in settings.get("update_url")
    assert settings.get("layout.hidden") == ["media"] and settings.get("layout.order") == ["timer", "agents"]
    assert [w["id"] for w in settings.get("connectors.sql.widgets")] == ["w1"]   # not read-only: dropped
    assert settings.get("connectors.m365.tenant") == "organizations"     # nested values not in the file are kept
    assert settings.get("unknown") is None
    with pytest.raises(ValueError):
        backup.import_data(settings, {"settings": {}})
