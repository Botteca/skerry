# PyInstaller: two executables in the same folder
#   Skerry.exe  (app, no console)   skerry-cli.exe  (hooks and status line, console)
# Usage:  pyinstaller build\skerry.spec --noconfirm --workpath build\work
# The version is read from skerry/__init__.py and written into build/work/version_info.txt (from the template).
import os
import sys

from PyInstaller.utils.hooks import collect_all

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import release  # noqa: E402  (tools/release.py: the version comes only from skerry/__init__.py)

VERSION = release.version(ROOT)
_numbers = tuple(int(x) for x in VERSION.split("-")[0].split(".")) + (0,)
_version_file = os.path.join(ROOT, "build", "work", "version_info.txt")
os.makedirs(os.path.dirname(_version_file), exist_ok=True)
with open(os.path.join(SPECPATH, "version_info.txt"), encoding="utf-8") as _f:
    _tpl = _f.read()
with open(_version_file, "w", encoding="utf-8") as _f:
    _f.write(_tpl.replace("{version}", VERSION).replace("{numbers}", repr(_numbers)))
datas = [(os.path.join(ROOT, "ui"), "ui"), (os.path.join(ROOT, "assets"), "assets")]
binaries, hidden = [], ["msal", "pystray._win32", "comtypes.stream", "comtypes.client", "icalendar",
                        "recurring_ical_events", "x_wr_timezone", "winrt.windows.foundation",
                        "winrt.windows.media.control", "winrt.windows.storage.streams"]
for pkg in ("webview", "winrt", "pycaw", "icalendar", "tzdata"):
    try:
        d, b, h = collect_all(pkg)
        datas += d; binaries += b; hidden += h
    except Exception:
        pass

a = Analysis([os.path.join(ROOT, "app.py")], pathex=[ROOT], datas=datas, binaries=binaries,
             hiddenimports=hidden, excludes=["tkinter", "matplotlib", "numpy"])
c = Analysis([os.path.join(ROOT, "cli.py")], pathex=[ROOT], hiddenimports=["psutil"],
             excludes=["tkinter", "webview", "flask", "PIL", "pystray", "matplotlib", "numpy"])

icon = os.path.join(ROOT, "assets", "brand", "skerry.ico")
exe_app = EXE(PYZ(a.pure), a.scripts, [], exclude_binaries=True, name="Skerry", console=False, icon=icon,
              version=_version_file)
exe_cli = EXE(PYZ(c.pure), c.scripts, [], exclude_binaries=True, name="skerry-cli", console=True, icon=icon,
              version=_version_file)
coll = COLLECT(exe_app, a.binaries, a.datas, exe_cli, c.binaries, c.datas, name="Skerry")
