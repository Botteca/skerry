"""Multi-monitor logic: screen choice, docking/renumbering, layout changes, geometry with different DPI."""
import pytest

from skerry import displays


def mon(device, primary=False, rect=(0, 0, 1920, 1080), work=None, dpi=96, id_=None, name="Generic Monitor"):
    return {"device": device, "primary": primary, "monitor": rect, "work": work or (rect[0], rect[1], rect[2], rect[3] - 40),
            "dpi": dpi, "scale": dpi / 96, "id": id_ if id_ is not None else f"id-{device[-1]}", "name": name}


LAPTOP = mon(r"\\.\DISPLAY1", primary=True, rect=(0, 0, 1920, 1200), dpi=144, id_="laptop")
DESK = mon(r"\\.\DISPLAY2", rect=(1920, 0, 4480, 1440), dpi=96, id_="desk")


# ------------------------------------------------------------------ choice

def test_primary_and_specific():
    assert displays.resolve([LAPTOP, DESK], "") == (LAPTOP, "primary")
    assert displays.resolve([LAPTOP, DESK], r"\\.\DISPLAY2", "desk") == (DESK, "chosen")


def test_follow_the_mouse():
    assert displays.resolve([LAPTOP, DESK], "mouse", cursor_device=r"\\.\DISPLAY2") == (DESK, "mouse")
    assert displays.resolve([LAPTOP, DESK], "mouse", cursor_device="") == (LAPTOP, "primary")   # pointer unknown


def test_chosen_screen_disconnected_falls_back_to_primary():
    assert displays.resolve([LAPTOP], r"\\.\DISPLAY2", "desk") == (LAPTOP, "missing")


def test_docking_renumbers_devices_but_the_id_follows_the_screen():
    # after docking the desk screen came back as DISPLAY3 and another screen took DISPLAY2
    desk3 = {**DESK, "device": r"\\.\DISPLAY3"}
    other = mon(r"\\.\DISPLAY2", rect=(4480, 0, 6400, 1080), id_="other")
    assert displays.resolve([LAPTOP, other, desk3], r"\\.\DISPLAY2", "desk") == (desk3, "chosen")
    # without an id (older settings) the device name still works
    assert displays.resolve([LAPTOP, DESK], r"\\.\DISPLAY2", "") == (DESK, "chosen")


def test_no_screen_at_all():
    assert displays.resolve([], "") == (None, "none")
    assert displays.resolve([], "mouse", cursor_device="x") == (None, "none")


def test_no_flag_for_primary_uses_the_first_screen():
    a, b = {**LAPTOP, "primary": False}, {**DESK, "primary": False}
    assert displays.resolve([a, b], "")[0] is a


# ------------------------------------------------------------------ changes (log lines)

def test_changes_connect_disconnect_and_lid_closed():
    assert displays.changes([LAPTOP], [LAPTOP, DESK]) == [f"screen connected: {displays.label(DESK)}"]
    assert displays.changes([LAPTOP, DESK], [LAPTOP]) == [f"screen disconnected: {displays.label(DESK)}"]
    assert displays.changes([LAPTOP], [])[-1].startswith("no active screen")


def test_changes_dpi_resolution_taskbar_primary_and_renaming():
    new = {**DESK, "dpi": 144, "device": r"\\.\DISPLAY3", "primary": True}
    msgs = displays.changes([LAPTOP, DESK], [{**LAPTOP, "primary": False}, new])
    assert any("renamed" in m and "DISPLAY3" in m for m in msgs)
    assert any(m.startswith("primary screen is now") and "DISPLAY3" in m for m in msgs)
    assert any("DPI 96 -> 144" in m for m in msgs)
    moved = displays.changes([DESK], [{**DESK, "monitor": (1920, 0, 3840, 1080), "work": (1920, 0, 3840, 1040)}])
    assert len(moved) == 1 and "area" in moved[0] and "work area" not in moved[0]
    taskbar = displays.changes([DESK], [{**DESK, "work": (1920, 48, 4480, 1440)}])
    assert taskbar == [rf"\\.\DISPLAY2: work area {DESK['work']} -> (1920, 48, 4480, 1440) (taskbar moved or resized)"]
    assert displays.changes([LAPTOP, DESK], [LAPTOP, DESK]) == []


# ------------------------------------------------------------------ geometry

@pytest.mark.parametrize("edge, expected", [
    ("top", (1920 + 1280 - 90, 8, 180, 34)),
    ("bottom", (1920 + 1280 - 90, 1400 - 34 - 8, 180, 34)),
    ("left", (1920 + 8, 700 - 17, 180, 34)),
    ("right", (4480 - 180 - 8, 700 - 17, 180, 34)),
])
def test_geometry_edges_on_a_secondary_screen(edge, expected):
    assert displays.geometry(180, 34, edge, 0.5, DESK, 1.0) == expected


def test_geometry_scales_with_the_target_screen_dpi():
    x, y, w, h = displays.geometry(180, 34, "top", 0.5, LAPTOP, 1.5)
    assert (w, h) == (270, 51) and y == 12                  # 150 %: size and margin scaled
    assert x == round(0.5 * 1920 - 270 / 2)


def test_geometry_clamps_offset_and_hugs_the_top_without_taskbar():
    x, *_ = displays.geometry(180, 34, "top", 5.0, DESK, 1.0)
    assert x == 4480 - 180 - 8                              # never past the right edge
    top_taskbar = {**DESK, "work": (1920, 48, 4480, 1440)}
    assert displays.geometry(180, 34, "top", 0.5, top_taskbar, 1.0)[1] == 48 + 8   # below a top taskbar
    assert displays.geometry(180, 34, "top", 0.5, DESK, 1.0)[1] == 8               # no top taskbar: real edge


def test_visible_on_any():
    assert displays.visible_on_any((100, 10, 280, 44), [LAPTOP, DESK])
    assert displays.visible_on_any((1900, 10, 2080, 44), [LAPTOP, DESK])            # across the two screens
    assert not displays.visible_on_any((5000, 10, 5180, 44), [LAPTOP, DESK])         # screen that was unplugged
    assert not displays.visible_on_any((100, 10, 280, 44), [])


# ------------------------------------------------------------------ api: screen choice stores the stable id

class _Settings(dict):
    def get(self, key, default=None):
        return super().get(key, default)

    def update(self, values):
        super().update(values)


def test_set_monitor(monkeypatch):
    from skerry import api as api_mod
    monkeypatch.setattr(api_mod.win32, "monitors", lambda: [LAPTOP, DESK])
    app = type("App", (), {"settings": _Settings(monitor="", monitor_id="")})()
    a = api_mod.Api(app)
    assert a.set_monitor(r"\\.\DISPLAY2") and app.settings["monitor_id"] == "desk"
    assert a.set_monitor("mouse") and app.settings == {"monitor": "mouse", "monitor_id": ""}
    assert a.set_monitor(r"\\.\DISPLAY9") is False                                   # unknown screen: refused
    assert a.set_monitor("") and app.settings["monitor"] == ""
    assert [m["device"] for m in a._monitors()] == [LAPTOP["device"], DESK["device"]]
    assert a._monitors()[0]["scale"] == 1.5 and a._monitors()[1]["width"] == 2560
