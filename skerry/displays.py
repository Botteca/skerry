"""Which screen the island lives on, and what changed between two display layouts. Pure functions (no Win32):
win32.monitors() provides the data, app.py drives them, tests cover the edge cases.

Setting `monitor`: "" = primary screen, "mouse" = the screen with the mouse pointer, otherwise a device name
(\\\\.\\DISPLAY2). `monitor_id` keeps the stable monitor interface id next to it: device names can be reassigned
after docking or reconnecting, the id follows the physical screen.
"""
PRIMARY, MOUSE = "", "mouse"


def label(m):
    return f"{m.get('device')} ({m.get('name') or '?'}, {width(m)}x{height(m)}, {m.get('dpi', 96)} dpi)"


def width(m):
    return m["monitor"][2] - m["monitor"][0]


def height(m):
    return m["monitor"][3] - m["monitor"][1]


def primary(mons):
    return next((m for m in mons if m.get("primary")), mons[0] if mons else None)


def find(mons, device="", monitor_id=""):
    """Monitor matching the stable id first, then the device name."""
    if monitor_id:
        for m in mons:
            if m.get("id") == monitor_id:
                return m
    if device:
        for m in mons:
            if m.get("device") == device:
                return m
    return None


def resolve(mons, setting="", monitor_id="", cursor_device=""):
    """(monitor, reason). reason: primary | mouse | chosen | missing (chosen screen not connected) | none."""
    if not mons:
        return None, "none"
    if setting == MOUSE:
        m = find(mons, cursor_device)
        return (m, "mouse") if m else (primary(mons), "primary")
    if setting:
        m = find(mons, setting, monitor_id)
        return (m, "chosen") if m else (primary(mons), "missing")
    return primary(mons), "primary"


def key(m):
    return m.get("id") or m.get("device")


def changes(old, new):
    """Human-readable differences between two monitor lists (for the log)."""
    out = []
    a, b = {key(m): m for m in old}, {key(m): m for m in new}
    for k in b.keys() - a.keys():
        out.append(f"screen connected: {label(b[k])}")
    for k in a.keys() - b.keys():
        out.append(f"screen disconnected: {label(a[k])}")
    for k in a.keys() & b.keys():
        o, n = a[k], b[k]
        if o.get("device") != n.get("device"):
            out.append(f"screen {o.get('name') or k} renamed {o.get('device')} -> {n.get('device')}")
        if o.get("primary") != n.get("primary") and n.get("primary"):
            out.append(f"primary screen is now {n.get('device')}")
        if o.get("dpi") != n.get("dpi"):
            out.append(f"{n.get('device')}: DPI {o.get('dpi')} -> {n.get('dpi')}")
        if tuple(o["monitor"]) != tuple(n["monitor"]):
            out.append(f"{n.get('device')}: area {tuple(o['monitor'])} -> {tuple(n['monitor'])}")
        elif tuple(o["work"]) != tuple(n["work"]):
            out.append(f"{n.get('device')}: work area {tuple(o['work'])} -> {tuple(n['work'])} (taskbar moved or resized)")
    if old and not new:
        out.append("no active screen (lid closed, all screens off or the session is locked)")
    return out


def geometry(w, h, edge, offset, mon, scale, margin=8):
    """Window rectangle (x, y, W, H) in screen pixels for a w x h pill (CSS px) snapped to `edge` of `mon`."""
    W, H = round(w * scale), round(h * scale)
    if mon:
        L, T, R, B = mon["work"]
        if edge == "top" and mon["work"][1] == mon["monitor"][1]:
            T = mon["monitor"][1]             # top taskbar absent: hug the real top edge
    else:
        L, T, R, B = 0, 0, 1920, 1080
    m = round(margin * scale)
    off = min(0.98, max(0.02, float(offset)))
    if edge in ("top", "bottom"):
        x = round(L + off * (R - L) - W / 2)
        x = max(L + m, min(R - W - m, x))
        y = T + m if edge == "top" else B - H - m
    else:
        y = round(T + off * (B - T) - H / 2)
        y = max(T + m, min(B - H - m, y))
        x = L + m if edge == "left" else R - W - m
    return x, y, W, H


def visible_on_any(rect, mons, min_overlap=16):
    """True if the window rectangle (left, top, right, bottom) overlaps some screen by at least `min_overlap` pixels each way."""
    left, top, right, bottom = rect
    for m in mons:
        ml, mt, mr, mb = m["monitor"]
        if min(right, mr) - max(left, ml) >= min_overlap and min(bottom, mb) - max(top, mt) >= min_overlap:
            return True
    return False
