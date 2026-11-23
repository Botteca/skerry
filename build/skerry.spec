# PyInstaller: two executables in the same folder
#   Skerry.exe  (app, no console)   skerry-cli.exe  (hooks and status line, console)
# Usage:  pyinstaller build\skerry.spec --noconfirm
import os
from PyInstaller.utils.hooks import collect_all

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
datas = [(os.path.join(ROOT, "ui"), "ui"), (os.path.join(ROOT, "assets"), "assets")]
binaries, hidden = [], ["msal", "pystray._win32", "comtypes.stream", "winrt.windows.foundation",
                        "winrt.windows.media.control", "winrt.windows.storage.streams"]
for pkg in ("webview", "winrt", "pycaw"):
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
              version=os.path.join(SPECPATH, "version_info.txt"))
exe_cli = EXE(PYZ(c.pure), c.scripts, [], exclude_binaries=True, name="skerry-cli", console=True, icon=icon)
coll = COLLECT(exe_app, a.binaries, a.datas, exe_cli, c.binaries, c.datas, name="Skerry")
