"""Settings: defaults merged into older/partial files, dotted keys, listeners, atomic save."""
import json

import pytest

from skerry import settings as settings_mod
from skerry.settings import DEFAULTS, Settings, load_raw


def write(path, data):
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def path(tmp_path):
    return tmp_path / "settings.json"


def test_new_file_gets_all_defaults(path):
    s = Settings(str(path))
    assert s.is_new
    expected = {**DEFAULTS, "first_run_done": False}       # brand-new file: the guided setup is shown
    assert read(path) == expected
    assert s.all() == expected


def test_existing_file_skips_the_guided_setup(path):
    write(path, {"theme": "dark"})                          # settings from an older version: no guided setup
    assert Settings(str(path)).get("first_run_done") is True


def test_missing_values_are_added_and_user_values_kept(path):
    # a settings file from an older version: some keys missing, nested dicts incomplete
    write(path, {"theme": "light", "port": 48000,
                 "modules": {"media": False},
                 "alerts": {"limits": [50]},
                 "connectors": {"m365": {"client_id": "00000000-0000-0000-0000-000000000000"}},
                 "something_removed": 1})
    s = Settings(str(path))
    assert not s.is_new
    assert s.get("theme") == "light"
    assert s.get("port") == 48000
    assert s.get("modules.media") is False
    assert s.get("modules.claude") is True                   # added inside an existing dict
    assert s.get("alerts.limits") == [50]                    # lists are values, not merged
    assert s.get("alerts.context") == DEFAULTS["alerts"]["context"]
    assert s.get("connectors.m365.client_id") == "00000000-0000-0000-0000-000000000000"
    assert s.get("connectors.m365.tenant") == "organizations"
    assert s.get("pomodoro") == DEFAULTS["pomodoro"]         # whole missing section
    assert s.get("something_removed") == 1                   # unknown keys are not dropped

    s.set("theme", "dark")                                   # the next save persists the merged file
    on_disk = read(path)
    assert on_disk["modules"]["claude"] is True
    assert on_disk["pomodoro"] == DEFAULTS["pomodoro"]


def test_wrong_type_in_file_is_kept_not_merged(path):
    write(path, {"modules": "oops"})
    assert Settings(str(path)).get("modules") == "oops"


@pytest.mark.parametrize("content", ["{not json", "[1, 2, 3]", "", "null"])
def test_corrupt_file_falls_back_to_defaults(path, content):
    write(path, content)
    assert load_raw(str(path)) == DEFAULTS


def test_defaults_are_never_mutated(path):
    s = Settings(str(path))
    s.get("modules")["claude"] = False                       # get() returns a copy
    s.set("modules.media", False)
    s.set("alerts.limits", [10])
    assert DEFAULTS["modules"]["media"] is True
    assert DEFAULTS["alerts"]["limits"] == [80, 90]
    assert Settings(str(path.with_name("other.json"))).get("modules.media") is True


def test_dotted_get_set_and_defaults(path):
    s = Settings(str(path))
    assert s.get("missing.key", "fallback") == "fallback"
    assert s.get("theme.nested", "x") == "x"
    s.set("connectors.new.value", 3)                         # intermediate dicts are created
    assert s.get("connectors.new") == {"value": 3}
    assert read(path)["connectors"]["new"] == {"value": 3}


def test_listeners_fire_only_on_change(path):
    s = Settings(str(path))
    seen = []
    s.on_change(lambda k, v: seen.append((k, v)))
    s.set("theme", "light")
    s.set("theme", "light")
    s.update({"accent": "#123456", "pomodoro.focus": 50})
    assert seen == [("theme", "light"), ("accent", "#123456"), ("pomodoro.focus", 50)]
    assert read(path)["pomodoro"]["focus"] == 50


def test_failing_listener_does_not_break_set(path):
    s = Settings(str(path))
    s.on_change(lambda k, v: 1 / 0)
    s.set("theme", "light")
    assert s.get("theme") == "light"


def test_save_leaves_no_temp_file(path):
    Settings(str(path)).set("theme", "light")
    assert not list(path.parent.glob("*.tmp"))


def test_default_path_is_under_appdata(isolated_dirs):
    s = Settings()
    assert s.is_new
    assert str(isolated_dirs / "appdata" / "Skerry" / "settings.json") == s._path


def test_no_secrets_in_defaults():
    flat = json.dumps(settings_mod.DEFAULTS).lower()
    for word in ("password", "secret", "token", "refresh"):
        assert word not in flat


@pytest.mark.parametrize("old, expected", [(False, "off"), (True, "auto")])
def test_check_updates_is_migrated_to_updates(path, old, expected):
    write(path, {"check_updates": old})
    s = Settings(str(path))
    assert s.get("updates") == expected
    assert s.get("check_updates") is None
    s.set("theme", "light")
    assert "check_updates" not in read(path)


def test_explicit_updates_mode_wins_over_old_flag(path):
    write(path, {"check_updates": False, "updates": "notify"})
    assert Settings(str(path)).get("updates") == "notify"
