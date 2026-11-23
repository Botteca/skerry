"""Native Windows integration: edge-snapped pill window, dragging, fullscreen detection,
window focus, clipboard, single instance, global hotkey."""
import logging
import sys
import threading
import time

from . import displays

log = logging.getLogger("skerry")
IS_WIN = sys.platform == "win32"

if IS_WIN:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32")
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    shell32 = ctypes.WinDLL("shell32")

    HWND, RECT, POINT = wintypes.HWND, wintypes.RECT, wintypes.POINT

    def _sig(fn, res, *args):
        fn.restype = res
        fn.argtypes = list(args)

    _sig(user32.FindWindowW, HWND, wintypes.LPCWSTR, wintypes.LPCWSTR)
    _sig(user32.SetWindowDisplayAffinity, wintypes.BOOL, HWND, wintypes.DWORD)
    _sig(user32.GetWindowLongW, ctypes.c_long, HWND, ctypes.c_int)
    _sig(user32.SetWindowLongW, ctypes.c_long, HWND, ctypes.c_int, ctypes.c_long)
    _sig(user32.SetWindowPos, wintypes.BOOL, HWND, HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
         wintypes.UINT)
    _sig(user32.MonitorFromPoint, wintypes.HMONITOR, POINT, wintypes.DWORD)
    _sig(user32.MonitorFromWindow, wintypes.HMONITOR, HWND, wintypes.DWORD)
    _sig(user32.GetDpiForWindow, wintypes.UINT, HWND)
    _sig(user32.SetWindowRgn, ctypes.c_int, HWND, wintypes.HRGN, wintypes.BOOL)
    _sig(gdi32.CreateRoundRectRgn, wintypes.HRGN, *([ctypes.c_int] * 6))
    _sig(user32.GetCursorPos, wintypes.BOOL, ctypes.POINTER(POINT))
    _sig(user32.GetWindowRect, wintypes.BOOL, HWND, ctypes.POINTER(RECT))
    _sig(user32.GetAsyncKeyState, ctypes.c_short, ctypes.c_int)
    _sig(user32.ShowWindow, wintypes.BOOL, HWND, ctypes.c_int)
    _sig(user32.IsWindowVisible, wintypes.BOOL, HWND)
    _sig(user32.IsWindow, wintypes.BOOL, HWND)
    _sig(user32.IsIconic, wintypes.BOOL, HWND)
    _sig(user32.GetForegroundWindow, HWND)
    _sig(user32.GetWindow, HWND, HWND, wintypes.UINT)
    _sig(user32.GetWindowThreadProcessId, wintypes.DWORD, HWND, ctypes.c_void_p)
    _sig(user32.AttachThreadInput, wintypes.BOOL, wintypes.DWORD, wintypes.DWORD, wintypes.BOOL)
    _sig(user32.BringWindowToTop, wintypes.BOOL, HWND)
    _sig(user32.SetForegroundWindow, wintypes.BOOL, HWND)
    _sig(user32.GetClassNameW, ctypes.c_int, HWND, wintypes.LPWSTR, ctypes.c_int)
    _sig(user32.OpenClipboard, wintypes.BOOL, HWND)
    _sig(user32.EmptyClipboard, wintypes.BOOL)
    _sig(user32.SetClipboardData, wintypes.HANDLE, wintypes.UINT, wintypes.HANDLE)
    _sig(user32.CloseClipboard, wintypes.BOOL)
    _sig(user32.RegisterHotKey, wintypes.BOOL, HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT)
    _sig(user32.UnregisterHotKey, wintypes.BOOL, HWND, ctypes.c_int)
    _sig(user32.GetMessageW, wintypes.BOOL, ctypes.POINTER(wintypes.MSG), HWND, wintypes.UINT, wintypes.UINT)
    _sig(user32.PostThreadMessageW, wintypes.BOOL, wintypes.DWORD, wintypes.UINT, wintypes.WPARAM,
         wintypes.LPARAM)
    _sig(kernel32.GlobalAlloc, wintypes.HGLOBAL, wintypes.UINT, ctypes.c_size_t)
    _sig(kernel32.GlobalLock, ctypes.c_void_p, wintypes.HGLOBAL)
    _sig(kernel32.GlobalUnlock, wintypes.BOOL, wintypes.HGLOBAL)
    _sig(kernel32.CreateMutexW, wintypes.HANDLE, ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
    _sig(kernel32.GetCurrentThreadId, wintypes.DWORD)

    class MONITORINFOEXW(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", RECT), ("rcWork", RECT),
                    ("dwFlags", wintypes.DWORD), ("szDevice", wintypes.WCHAR * 32)]

    _sig(user32.GetMonitorInfoW, wintypes.BOOL, wintypes.HMONITOR, ctypes.POINTER(MONITORINFOEXW))
    MonitorEnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC,
                                         ctypes.POINTER(RECT), wintypes.LPARAM)
    _sig(user32.EnumDisplayMonitors, wintypes.BOOL, wintypes.HDC, ctypes.c_void_p, MonitorEnumProc,
         wintypes.LPARAM)

    class DISPLAY_DEVICEW(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("DeviceName", wintypes.WCHAR * 32), ("DeviceString", wintypes.WCHAR * 128),
                    ("StateFlags", wintypes.DWORD), ("DeviceID", wintypes.WCHAR * 128),
                    ("DeviceKey", wintypes.WCHAR * 128)]

    _sig(user32.EnumDisplayDevicesW, wintypes.BOOL, wintypes.LPCWSTR, wintypes.DWORD,
         ctypes.POINTER(DISPLAY_DEVICEW), wintypes.DWORD)

GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW, WS_EX_APPWINDOW = 0x80, 0x40000
HWND_TOPMOST = -1
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE, SWP_FRAMECHANGED = 0x1, 0x2, 0x10, 0x20
SWP_NOCOPYBITS = 0x100
SW_HIDE, SW_SHOWNOACTIVATE, SW_RESTORE = 0, 4, 9


# ---------------- monitor ----------------
def monitor_dpi(hmon):
    """Effective DPI of a monitor (GetDpiForMonitor, Windows 8.1+); 96 if unknown."""
    try:
        x, y = wintypes.UINT(), wintypes.UINT()
        if ctypes.windll.shcore.GetDpiForMonitor(hmon, 0, ctypes.byref(x), ctypes.byref(y)) == 0 and x.value:
            return int(x.value)
    except Exception:
        pass
    return 96


def _display_device(device):
    """(friendly name, stable id) of the screen attached to a display device such as DISPLAY2.
    The id is the monitor interface path: it follows the physical screen when device names are reassigned."""
    try:
        dd = DISPLAY_DEVICEW()
        dd.cb = ctypes.sizeof(DISPLAY_DEVICEW)
        if user32.EnumDisplayDevicesW(device, 0, ctypes.byref(dd), 1):   # EDD_GET_DEVICE_INTERFACE_NAME
            return dd.DeviceString or "", dd.DeviceID or ""
    except Exception:
        log.debug("EnumDisplayDevices %s", device, exc_info=True)
    return "", ""


def _monitor_info(hmon):
    mi = MONITORINFOEXW()
    mi.cbSize = ctypes.sizeof(MONITORINFOEXW)
    user32.GetMonitorInfoW(hmon, ctypes.byref(mi))
    r, w = mi.rcMonitor, mi.rcWork
    dpi = monitor_dpi(hmon)
    name, mid = _display_device(mi.szDevice)
    return {"device": mi.szDevice, "name": name, "id": mid, "primary": bool(mi.dwFlags & 1),
            "monitor": (r.left, r.top, r.right, r.bottom), "work": (w.left, w.top, w.right, w.bottom),
            "dpi": dpi, "scale": round(dpi / 96, 2)}


def monitors():
    if not IS_WIN:
        return []
    out = []

    def cb(hmon, hdc, rect, lp):
        out.append(_monitor_info(hmon))
        return True

    user32.EnumDisplayMonitors(None, None, MonitorEnumProc(cb), 0)
    return out


def window_rect(hwnd):
    """(left, top, right, bottom) of a window, or None."""
    if not IS_WIN or not hwnd:
        return None
    rc = RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rc)):
        return None
    return rc.left, rc.top, rc.right, rc.bottom


def cursor_device():
    """Device name of the screen under the mouse pointer ("" if unknown)."""
    if not IS_WIN:
        return ""
    pt = POINT()
    if not user32.GetCursorPos(ctypes.byref(pt)):
        return ""
    mi = MONITORINFOEXW()
    mi.cbSize = ctypes.sizeof(MONITORINFOEXW)
    if not user32.GetMonitorInfoW(user32.MonitorFromPoint(pt, 2), ctypes.byref(mi)):
        return ""
    return mi.szDevice


def dpi_awareness():
    """'per-monitor', 'system' or 'unaware'. With 'system' Windows virtualises coordinates and DPI on screens whose
    scale differs from the main one (it stretches the window), so every screen reports the system DPI."""
    try:
        ctx = user32.GetThreadDpiAwarenessContext()
        return {0: "unaware", 1: "system", 2: "per-monitor"}.get(user32.GetAwarenessFromDpiAwarenessContext(ctx), "?")
    except Exception:
        return "?"


# ---------------- pill window ----------------
def _timer_resolution(on):
    """1 ms timer resolution during animations (by default Windows sleeps in ~15 ms steps)."""
    try:
        ctypes.windll.winmm.timeBeginPeriod(1) if on else ctypes.windll.winmm.timeEndPeriod(1)
    except Exception:
        pass


def _vsync():
    try:
        if ctypes.windll.dwmapi.DwmFlush() == 0:
            return
    except Exception:
        pass
    time.sleep(0.008)


class SkerryWindow:
    MARGIN = 8

    def __init__(self, title, settings):
        self.title = title
        self.settings = settings
        self.hwnd = None
        self.cur = (180.0, 34.0, 17.0)
        self.dragging = False
        self.visible = True
        self._gen = 0
        self._lock = threading.Lock()
        self.displays = []           # cached monitors() list, refreshed by the app's display loop
        # true per-pixel transparency (DWM "sheet of glass"): the web page draws the rounded shape with smooth
        # edges. Off (setting smooth_edges = false, or if DWM refuses) = the old window region with hard edges.
        self.glass = bool(settings.get("smooth_edges", True))
        self._region_cleared = False
        self.cursor_device = ""      # screen with the mouse (for monitor = "mouse")

    def handle(self):
        if IS_WIN and not self.hwnd:
            self.hwnd = user32.FindWindowW(None, self.title)
        return self.hwnd

    def setup(self):
        h = self.handle()
        if not h:
            log.warning("Island window not found")
            return
        ex = user32.GetWindowLongW(h, GWL_EXSTYLE)
        want = (ex | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW
        if want != ex:
            user32.SetWindowLongW(h, GWL_EXSTYLE, want)
            # the taskbar only notices the new style when the window is shown again
            if user32.IsWindowVisible(h):
                user32.ShowWindow(h, SW_HIDE)
                user32.ShowWindow(h, SW_SHOWNOACTIVATE)
            log.info("Pill removed from the taskbar")
        self.dwm_flat()
        self.capture_hidden()
        log.info("Smooth edges: %s", "on (transparent window)" if self.glass else "off (window region)")
        try:
            ctx = user32.GetThreadDpiAwarenessContext()
            aware = user32.GetAwarenessFromDpiAwarenessContext(ctx)
        except Exception:
            aware = "?"
        log.info("Window hwnd=%s dpi=%s awareness=%s", h, user32.GetDpiForWindow(h), aware)
        self._apply(*self.cur, SWP_FRAMECHANGED)
        self.diag("setup")

    def capture_hidden(self, hwnd=None):
        """Exclude a window from screen sharing and recording (Teams, Zoom, Meet, OBS...).

        The user still sees it; viewers do not. Uses WDA_EXCLUDEFROMCAPTURE (Windows 10 2004+) and falls back
        to WDA_MONITOR (a black box in captures) on older builds. Driven by the `hide_from_capture` setting;
        the last applied state is cached per window so this is cheap to call often.
        """
        h = hwnd or self.handle()
        if not h or not IS_WIN:
            return
        want = bool(self.settings.get("hide_from_capture", True))
        applied = self.__dict__.setdefault("_capture_state", {})
        if applied.get(h) == want:
            return
        ok = user32.SetWindowDisplayAffinity(h, 0x11 if want else 0)  # WDA_EXCLUDEFROMCAPTURE / WDA_NONE
        if not ok and want:
            ok = user32.SetWindowDisplayAffinity(h, 0x01)  # WDA_MONITOR
        applied[h] = want
        log.info("Screen-capture exclusion hwnd=%s: %s (%s)", h, "on" if want else "off", "ok" if ok else "failed")

    def dwm_flat(self):
        """No Mica backdrop (the grey #202020 rectangle pywebview applies in dark theme), no border, no system
        corners. With `glass` the whole client area becomes DWM frame ("sheet of glass"): the form background is
        black, which DWM treats as transparent, and the transparent web view is blended per pixel, so the page
        draws the pill with smooth edges. Without it: no shadow or frame, and the shape comes from the region."""
        h = self.handle()
        if not h or not IS_WIN:
            return
        try:
            dwm = ctypes.WinDLL("dwmapi")
            put = lambda attr, val, t=ctypes.c_int: dwm.DwmSetWindowAttribute(h, attr, ctypes.byref(t(val)), 4)
            put(38, 1)                    # DWMWA_SYSTEMBACKDROP_TYPE = none (pywebview sets Mica = 2)
            put(33, 1)                    # DWMWA_WINDOW_CORNER_PREFERENCE = do not round
            put(34, 0xFFFFFFFE, ctypes.c_uint)  # DWMWA_BORDER_COLOR = none
            if self.glass:
                margins = (ctypes.c_int * 4)(-1, -1, -1, -1)
                hr = dwm.DwmExtendFrameIntoClientArea(h, margins)
                if hr != 0:
                    log.warning("Transparent window refused by DWM (0x%08x): back to the window region",
                                hr & 0xFFFFFFFF)
                    self.glass = False
            if not self.glass:
                put(2, 1)                 # DWMWA_NCRENDERING_POLICY = disabled (no shadow/frame)
                margins = (ctypes.c_int * 4)(0, 0, 0, 0)
                dwm.DwmExtendFrameIntoClientArea(h, margins)
        except Exception:
            log.debug("DWM not available", exc_info=True)

    def diag(self, why=""):
        """Log the real window and WebView sizes (diagnostics)."""
        hwnd = self.handle()
        if not hwnd:
            return
        rc, cc = RECT(), RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rc))
        child = user32.GetWindow(hwnd, 5)  # GW_CHILD
        if child:
            user32.GetWindowRect(child, ctypes.byref(cc))
        log.info("diag %s: requested=%s window=%sx%s@%s,%s webview=%sx%s", why,
                 tuple(round(v) for v in self.cur), rc.right - rc.left, rc.bottom - rc.top, rc.left, rc.top,
                 cc.right - cc.left, cc.bottom - cc.top)

    def target(self):
        """(monitor, reason) the island belongs to right now (see displays.resolve)."""
        mons = self.displays or monitors()
        return displays.resolve(mons, self.settings.get("monitor", ""), self.settings.get("monitor_id", ""),
                                self.cursor_device)

    def _rect(self, w, h):
        mon, _ = self.target()
        if mon is None:
            return None
        # size from the target screen's DPI, not the window's: when the island moves to a screen with another
        # scale it gets the right size at once (with system DPI awareness every screen reports the same DPI)
        scale = (mon.get("dpi") or user32.GetDpiForWindow(self.handle()) or 96) / 96
        x, y, W, H = displays.geometry(w, h, self.settings.get("edge", "top"), self.settings.get("offset", 0.5),
                                       mon, scale, self.MARGIN)
        return x, y, W, H, scale

    def _apply(self, w, h, r, flags=0):
        hwnd = self.handle()
        if not hwnd or self.dragging:
            return
        rect = self._rect(w, h)
        if rect is None:                 # no active screen: keep the window where it is
            return
        x, y, W, H, scale = rect
        d = max(2, round(2 * r * scale))
        if self.glass:
            # transparent window: the page draws the rounded shape, no region (removed once)
            if not self._region_cleared:
                user32.SetWindowRgn(hwnd, None, False)
                self._region_cleared = True
        else:
            # region first, then the window: no "square" corner ever shows during the animation
            user32.SetWindowRgn(hwnd, gdi32.CreateRoundRectRgn(0, 0, W + 1, H + 1, d, d), False)
            self._region_cleared = False
        user32.SetWindowPos(hwnd, HWND_TOPMOST, x, y, W, H, SWP_NOACTIVATE | SWP_NOCOPYBITS | flags)

    def animate_to(self, w, h, r, duration=0.30):
        if not IS_WIN:
            self.cur = (w, h, r)
            return
        with self._lock:
            self._gen += 1
            gen = self._gen
            start = self.cur
        if start == (w, h, r):
            return

        def run():
            # wall-clock time (not a step count) + DwmFlush: one frame per screen refresh
            t0 = time.perf_counter()
            _timer_resolution(True)
            try:
                while gen == self._gen:
                    p = (time.perf_counter() - t0) / duration
                    if p >= 1:
                        break
                    e = 1 - (1 - p) ** 4          # ease-out: fast start, soft landing
                    self.cur = tuple(a + (b - a) * e for a, b in zip(start, (w, h, r)))
                    self._apply(*self.cur)
                    _vsync()
                else:
                    return
                self.cur = (w, h, r)
                self._apply(*self.cur)
            finally:
                _timer_resolution(False)
            self.diag("resize")

        threading.Thread(target=run, daemon=True, name="anim").start()

    def replace(self):
        if IS_WIN:
            self._apply(*self.cur)

    def set_visible(self, visible):
        hwnd = self.handle()
        if not hwnd or visible == self.visible:
            return
        self.visible = visible
        user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE if visible else SW_HIDE)
        if visible:
            self._apply(*self.cur)

    def keep_on_top(self):
        hwnd = self.handle()
        self._tick = getattr(self, "_tick", 0) + 1
        if self._tick % 5 == 0:
            self.dwm_flat()
        self.capture_hidden()
        if hwnd and self.visible and not self.dragging:
            user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)

    def drag(self, on_done):
        """Follow the mouse while the left button is down, then snap to the nearest edge."""
        hwnd = self.handle()
        if not hwnd or self.dragging:
            return
        self._gen += 1
        self.dragging = True

        def run():
            try:
                pt, rc = POINT(), RECT()
                user32.GetCursorPos(ctypes.byref(pt))
                user32.GetWindowRect(hwnd, ctypes.byref(rc))
                dx, dy = pt.x - rc.left, pt.y - rc.top
                W, H = rc.right - rc.left, rc.bottom - rc.top
                while user32.GetAsyncKeyState(0x01) & 0x8000:
                    user32.GetCursorPos(ctypes.byref(pt))
                    user32.SetWindowPos(hwnd, HWND_TOPMOST, pt.x - dx, pt.y - dy, 0, 0, SWP_NOSIZE | SWP_NOACTIVATE)
                    time.sleep(0.008)
                user32.GetCursorPos(ctypes.byref(pt))
                cx, cy = pt.x - dx + W // 2, pt.y - dy + H // 2
                mon = _monitor_info(user32.MonitorFromPoint(POINT(cx, cy), 2))
                L, T, R, B = mon["work"]
                dist = {"top": cy - T, "bottom": B - cy, "left": cx - L, "right": R - cx}
                edge = min(dist, key=dist.get)
                offset = (cx - L) / max(1, R - L) if edge in ("top", "bottom") else (cy - T) / max(1, B - T)
                offset = round(min(0.98, max(0.02, offset)), 4)
            finally:
                self.dragging = False
            on_done(edge, offset, "" if mon["primary"] else mon["device"], mon.get("id", ""))
            self._apply(*self.cur)

        threading.Thread(target=run, daemon=True, name="drag").start()


# ---------------- utilities ----------------
def is_fullscreen(exclude=()):
    """True if an app is fullscreen or in presentation mode."""
    if not IS_WIN:
        return False
    state = ctypes.c_int(0)
    try:
        if shell32.SHQueryUserNotificationState(ctypes.byref(state)) == 0 and state.value in (2, 3, 4):
            return True
    except Exception:
        pass
    fg = user32.GetForegroundWindow()
    if not fg or fg in exclude:
        return False
    buf = ctypes.create_unicode_buffer(64)
    user32.GetClassNameW(fg, buf, 64)
    if buf.value in ("Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd", "Windows.UI.Core.CoreWindow"):
        return False
    if user32.GetWindowLongW(fg, -16) & 0xC00000 == 0xC00000:  # WS_CAPTION: normal/maximised window
        return False
    rc = RECT()
    user32.GetWindowRect(fg, ctypes.byref(rc))
    m = _monitor_info(user32.MonitorFromWindow(fg, 2))["monitor"]
    return rc.left <= m[0] and rc.top <= m[1] and rc.right >= m[2] and rc.bottom >= m[3]


# shortcut: screen sharing has no Windows API, so this looks for the "you are sharing" bars of the browsers and
# meeting apps by window title; add titles here when an app is not recognised.
SHARE_TITLES = ("is sharing your screen", "is sharing a window", "is sharing this tab", "sta condividendo lo schermo",
                "sta condividendo una finestra", "sta condividendo questa scheda", "sharing control bar",
                "zoom share toolbar", "you are screen sharing", "stai condividendo lo schermo")


def screen_sharing():
    """True if a known "screen is being shared" bar is on screen (heuristic, see SHARE_TITLES)."""
    if not IS_WIN:
        return False
    found = []

    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
            if 0 < n < 300:
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, buf, n + 1)
                title = buf.value.lower()
                if any(s in title for s in SHARE_TITLES):
                    found.append(hwnd)
                    return False
        return True

    proc = ctypes.WINFUNCTYPE(wintypes.BOOL, HWND, wintypes.LPARAM)(cb)
    user32.EnumWindows(proc, 0)
    return bool(found)


def focus_window(hwnd):
    if not IS_WIN or not hwnd or not user32.IsWindow(hwnd):
        return False
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    # temporarily attach input to the foreground thread: no simulated keystrokes
    fg = user32.GetForegroundWindow()
    me = kernel32.GetCurrentThreadId()
    other = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    attached = bool(other and other != me and user32.AttachThreadInput(me, other, True))
    try:
        user32.BringWindowToTop(hwnd)
        ok = user32.SetForegroundWindow(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(me, other, False)
    return bool(ok)


def dpi_info(hwnd=None):
    """Process DPI awareness, system DPI and the DPI of a window (diagnostics)."""
    if not IS_WIN:
        return {}
    out = {}
    try:
        ctx = user32.GetThreadDpiAwarenessContext()
        out["awareness"] = {0: "unaware", 1: "system", 2: "per-monitor"}.get(
            user32.GetAwarenessFromDpiAwarenessContext(ctx), "?")
    except Exception:
        out["awareness"] = "?"
    try:
        out["system_dpi"] = user32.GetDpiForSystem()
    except Exception:
        pass
    if hwnd:
        out["window_dpi"] = user32.GetDpiForWindow(hwnd)
    return out


def copy_text_to_clipboard(text):
    """Put Unicode text on the clipboard (CF_UNICODETEXT)."""
    if not IS_WIN:
        return False
    data = (str(text) + "\0").encode("utf-16-le")
    h = kernel32.GlobalAlloc(0x42, len(data))          # GMEM_MOVEABLE | GMEM_ZEROINIT
    if not h:
        return False
    p = kernel32.GlobalLock(h)
    ctypes.memmove(p, data, len(data))
    kernel32.GlobalUnlock(h)
    for _ in range(10):
        if user32.OpenClipboard(None):
            break
        time.sleep(0.05)
    else:
        return False
    try:
        user32.EmptyClipboard()
        return bool(user32.SetClipboardData(13, h))
    finally:
        user32.CloseClipboard()


def copy_files_to_clipboard(file_paths):
    """Put files on the clipboard (CF_HDROP): Ctrl+V in Explorer pastes them."""
    if not IS_WIN or not file_paths:
        return False

    class DROPFILES(ctypes.Structure):
        _fields_ = [("pFiles", wintypes.DWORD), ("pt", POINT), ("fNC", wintypes.BOOL), ("fWide", wintypes.BOOL)]

    data = ("\0".join(file_paths) + "\0\0").encode("utf-16-le")
    df = DROPFILES(ctypes.sizeof(DROPFILES), POINT(0, 0), 0, 1)
    size = ctypes.sizeof(df) + len(data)
    h = kernel32.GlobalAlloc(0x42, size)
    p = kernel32.GlobalLock(h)
    ctypes.memmove(p, ctypes.byref(df), ctypes.sizeof(df))
    ctypes.memmove(p + ctypes.sizeof(df), data, len(data))
    kernel32.GlobalUnlock(h)
    for _ in range(5):
        if user32.OpenClipboard(None):
            break
        time.sleep(0.05)
    else:
        return False
    try:
        user32.EmptyClipboard()
        user32.SetClipboardData(15, h)
    finally:
        user32.CloseClipboard()
    return True


def set_app_id(app_id):
    """Explicit AppUserModelID: taskbar grouping and notifications show Skerry, not python.exe."""
    if IS_WIN:
        try:
            shell32.SetCurrentProcessExplicitAppUserModelID(ctypes.c_wchar_p(app_id))
        except Exception:
            log.debug("AppUserModelID not set", exc_info=True)


def single_instance(name="Local\\SkerrySingleInstance"):
    """(is_first_instance, handle). Keep the handle alive for the whole process lifetime."""
    if not IS_WIN:
        return True, None
    h = kernel32.CreateMutexW(None, False, name)
    return ctypes.get_last_error() != 183, h


class Hotkey:
    MODS = {"alt": 1, "ctrl": 2, "control": 2, "shift": 4, "win": 8}

    def __init__(self, spec, callback):
        self.spec = spec
        self.callback = callback
        self._tid = None

    @classmethod
    def parse(cls, spec):
        mods, vk = 0x4000, None  # MOD_NOREPEAT
        for part in str(spec).lower().replace(" ", "").split("+"):
            if part in cls.MODS:
                mods |= cls.MODS[part]
            elif len(part) == 1 and part.isalnum():
                vk = ord(part.upper())
            elif part.startswith("f") and part[1:].isdigit():
                vk = 0x6F + int(part[1:])
            elif part == "space":
                vk = 0x20
        return mods, vk

    def start(self):
        if IS_WIN and self.spec:
            threading.Thread(target=self._run, daemon=True, name="hotkey").start()

    def _run(self):
        mods, vk = self.parse(self.spec)
        if vk is None:
            log.warning("Invalid hotkey: %s", self.spec)
            return
        self._tid = kernel32.GetCurrentThreadId()
        if not user32.RegisterHotKey(None, 1, mods, vk):
            log.warning("Hotkey %s is already used by another app", self.spec)
            return
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == 0x0312:
                try:
                    self.callback()
                except Exception:
                    log.exception("hotkey")
        user32.UnregisterHotKey(None, 1)

    def stop(self):
        if IS_WIN and self._tid:
            user32.PostThreadMessageW(self._tid, 0x12, 0, 0)
            self._tid = None
