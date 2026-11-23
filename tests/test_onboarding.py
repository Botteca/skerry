"""Guided setup: shown only on the very first run, can be finished/skipped and shown again."""
import pytest

from skerry import api as api_mod
from skerry.settings import Settings


class FakeApp:
    def __init__(self, settings):
        self.settings = settings


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(api_mod.win32, "monitors", lambda: [
        {"device": r"\\.\DISPLAY1", "primary": True, "monitor": (0, 0, 1920, 1080), "work": (0, 0, 1920, 1040)},
        {"device": r"\\.\DISPLAY2", "primary": False, "monitor": (1920, 0, 4480, 1440), "work": (1920, 0, 4480, 1400)}])
    calls = {"claude": 0}

    def claude_status():
        calls["claude"] += 1
        return {"installed": False, "available": True}

    monkeypatch.setattr(api_mod.integrations, "claude_status", claude_status)
    monkeypatch.setattr(api_mod.integrations, "codex_status", lambda: {"installed": False, "available": False})
    settings = Settings(str(tmp_path / "settings.json"))
    return {"settings": settings, "api": api_mod.Api(FakeApp(settings)), "calls": calls}


def test_first_run_shows_the_guided_setup(env):
    assert env["settings"].is_new and env["settings"].get("first_run_done") is False
    o = env["api"]._onboarding()
    assert o["hotkey"] == "win+alt+i"
    assert o["monitors"] == [{"value": "", "index": 1, "primary": True, "width": 1920, "height": 1080},
                             {"value": r"\\.\DISPLAY2", "index": 2, "primary": False, "width": 2560, "height": 1440}]
    assert o["claude"] == {"installed": False, "available": True}
    env["api"]._onboarding()
    assert env["calls"]["claude"] == 1                         # agent status is cached between UI polls


def test_finish_and_show_again(env):
    a, s = env["api"], env["settings"]
    assert a.onboarding_finish() is True
    assert s.get("first_run_done") is True
    assert Settings(s._path).get("first_run_done") is True     # persisted: not shown at the next start
    a.onboarding_restart()
    assert s.get("first_run_done") is False


def test_the_ui_can_choose_edge_and_monitor(env):
    a, s = env["api"], env["settings"]
    assert a.set_setting("edge", "left") and s.get("edge") == "left"
    assert a.set_setting("monitor", r"\\.\DISPLAY2") and s.get("monitor") == r"\\.\DISPLAY2"
    assert a.set_setting("first_run_done", True) is False      # only through onboarding_finish()
