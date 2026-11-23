"""Diagnostics: personal data is hidden; the report survives broken sections; nothing touches the system for real."""
import pytest

from skerry import diagnostics
from skerry.diagnostics import redact


def test_user_paths_are_hidden_in_every_spelling():
    text = ("C:\\Users\\ada.lovelace\\AppData\\Local\\Skerry\\logs\n"
            "C:/Users/ada.lovelace/.claude/settings.json\n"
            '{"path": "C:\\\\Users\\\\ada.lovelace\\\\AppData"}\n'
            "d:\\users\\Bob\\x")
    out = redact(text)
    assert "ada.lovelace" not in out and "Bob" not in out
    assert "C:\\Users\\<user>\\AppData" in out and "C:/Users/<user>/.claude" in out
    assert "C:\\\\Users\\\\<user>\\\\AppData" in out


def test_user_name_outside_paths_and_profile_names_with_spaces():
    out = redact(r"started by adal on HOST; profile C:\Users\Ada Lovelace\Desktop", user_names={"adal", "Ada Lovelace"})
    assert "adal" not in out.replace("<user>", "") and "Lovelace" not in out
    assert redact("radalt adal.", user_names={"adal"}) == "radalt <user>."      # whole words only


def test_emails_are_hidden():
    out = redact("Microsoft 365: signed in (ada@contoso.example) · reply to someone.else@mail.example.invalid")
    assert "@" not in out and out.count("<email>") == 2


def test_bluetooth_names_and_addresses_are_hidden():
    line = ("2026-11-23 INFO [MainThread] Bluetooth: {'scanned': 4, 'devices': [('Ada Headphones', 'a1b2c3d4e5f6', "
            "'BTHENUM\\\\DEV_A1B2C3D4E5F6'), ('Keyboard', None, 'HID\\\\x')]} -> [{'name': 'Ada Headphones', "
            "'battery': 40, 'kind': 'headset'}]")
    out = redact(line, device_names={"Ada Headphones"})
    assert "Ada Headphones" not in out and "a1b2c3d4e5f6" not in out.lower() and "'Keyboard'" not in out
    assert "'battery': 40" in out                               # useful data stays


def test_hashes_and_other_lines_are_kept():
    sha = "e0ddd6dea7cf987aa40bb7d499b73c333d1bc42cca51430d19d42417a0d75ac7"
    text = f"Update 1.2.0 downloaded and verified ({sha})\nPermission requested (claude) Bash: npm test"
    assert redact(text, device_names={"Mouse"}) == text


def test_tail(tmp_path):
    p = tmp_path / "skerry.log"
    p.write_text("\n".join(f"line {i}" for i in range(200)) + "\n", encoding="utf-8")
    lines = diagnostics.tail(str(p))
    assert len(lines) == 80 and lines[0] == "line 120" and lines[-1] == "line 199"
    assert diagnostics.tail(str(tmp_path / "missing.log"))[0].startswith("(log not readable")


class _Settings(dict):
    def get(self, key, default=None):
        return super().get(key, default)


class _App:
    def __init__(self):
        self.settings = _Settings(edge="top", offset=0.5, monitor="", modules={"claude": True, "media": False},
                                  bluetooth_names={"BLE ·9418": "Ada Mouse"}, language="auto")
        self.system = type("S", (), {"state": {"battery": None, "mic": [], "cam": [],
                                               "bluetooth": [{"name": "Ada Mouse", "battery": 80}]}})()
        self.win = type("W", (), {"handle": lambda self: None})()
        self.connectors = type("C", (), {"states": lambda self: {"m365": {"status": "ok", "account": "ada@x.example"}}})()
        self.updater = type("U", (), {"public_state": lambda self: (_ for _ in ()).throw(RuntimeError("boom"))})()


def test_build_report(monkeypatch, tmp_path):
    from skerry import integrations, paths, win32
    monkeypatch.setattr(win32, "monitors", lambda: [{"device": r"\\.\DISPLAY1", "primary": True, "dpi": 144,
                                                     "scale": 1.5, "monitor": (0, 0, 2560, 1440), "work": (0, 0, 2560, 1400)}])
    monkeypatch.setattr(win32, "dpi_info", lambda hwnd: {"awareness": "per-monitor"})
    monkeypatch.setattr(integrations, "claude_status", lambda: {"installed": True})
    monkeypatch.setattr(integrations, "codex_status", lambda: {"installed": False})
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "skerry.log").write_text("x INFO Microsoft 365: signed in (ada@x.example)\n"
                                                  "x INFO C:\\Users\\ada\\file\n", encoding="utf-8")
    monkeypatch.setattr(paths, "log_dir", lambda: str(tmp_path / "logs"))
    report = diagnostics.build(_App())
    for section in ("## Windows", "## Display (DPI)", "## Monitors", "## Modules", "## Agents", "## Connectors",
                    "## Updates", "## Last 80 log lines"):
        assert section in report
    assert '"dpi": 144' in report and '"media": false' in report
    assert "(not available: RuntimeError: boom)" in report       # a broken section does not break the report
    assert "ada@x.example" not in report and "Ada Mouse" not in report and "C:\\Users\\ada" not in report


@pytest.mark.parametrize("ok", [True, False])
def test_copy_to_clipboard(monkeypatch, ok):
    from skerry import win32
    copied = []
    monkeypatch.setattr(diagnostics, "build", lambda app: "a\nb\nc")
    monkeypatch.setattr(win32, "copy_text_to_clipboard", lambda text: copied.append(text) or ok)
    assert diagnostics.copy_to_clipboard(object()) == (ok, 3)
    assert copied == ["a\nb\nc"]
