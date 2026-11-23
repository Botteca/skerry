"""Find the terminal window (Windows Terminal, VS Code, console) hosting an agent
by walking up the parent processes of the hook CLI."""
import sys


def find_terminal_hwnd():
    if sys.platform != "win32":
        return 0
    try:
        import ctypes
        from ctypes import wintypes

        import psutil
    except Exception:
        return 0
    user32 = ctypes.windll.user32

    ancestors = []
    try:
        p = psutil.Process().parent()
        while p is not None and len(ancestors) < 25:
            ancestors.append(p.pid)
            p = p.parent()
    except Exception:
        pass
    if not ancestors:
        return 0

    windows = {}
    EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd) or user32.GetWindow(hwnd, 4):  # GW_OWNER
            return True
        if user32.GetWindowTextLengthW(hwnd) == 0:
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        windows.setdefault(pid.value, hwnd)
        return True

    user32.EnumWindows(EnumProc(cb), 0)
    for pid in ancestors:
        if pid in windows:
            return int(windows[pid])

    return 0
