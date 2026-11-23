"""System state: microphone/camera in use, battery, Bluetooth batteries."""
import logging
import sys
import threading
import time

from .i18n import Msg, t

log = logging.getLogger("skerry")
CONSENT = r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore"


def _app_name(key, nonpackaged):
    if nonpackaged:
        name = key.split("#")[-1]
        return name[:-4] if name.lower().endswith(".exe") else name
    return key.split("_")[0].split(".")[-1]


def apps_using(capability):
    """Apps using 'microphone' or 'webcam' right now."""
    if sys.platform != "win32":
        return []
    import winreg
    found = []

    def scan(key, nonpackaged):
        i = 0
        while True:
            try:
                name = winreg.EnumKey(key, i)
            except OSError:
                break
            i += 1
            try:
                with winreg.OpenKey(key, name) as sub:
                    if name == "NonPackaged":
                        scan(sub, True)
                        continue
                    start, _ = winreg.QueryValueEx(sub, "LastUsedTimeStart")
                    stop, _ = winreg.QueryValueEx(sub, "LastUsedTimeStop")
                    if stop == 0 and start > 0:
                        found.append(_app_name(name, nonpackaged))
            except OSError:
                continue

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, f"{CONSENT}\\{capability}") as root:
            scan(root, False)
    except OSError:
        pass
    return sorted(set(found))


def battery():
    if sys.platform != "win32":
        return None
    import ctypes

    class SPS(ctypes.Structure):
        _fields_ = [("ACLineStatus", ctypes.c_byte), ("BatteryFlag", ctypes.c_byte),
                    ("BatteryLifePercent", ctypes.c_byte), ("SystemStatusFlag", ctypes.c_byte),
                    ("BatteryLifeTime", ctypes.c_ulong), ("BatteryFullLifeTime", ctypes.c_ulong)]

    s = SPS()
    if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(s)):
        return None
    flag = s.BatteryFlag & 0xFF
    pct = s.BatteryLifePercent & 0xFF
    if flag == 128 or flag == 255 or pct == 255:
        return None  # no battery (desktop PC)
    return {"percent": pct, "plugged": s.ACLineStatus == 1}


_GENERIC = ("bluetooth le device", "hands-free", "handsfree", "vivavoce", "dispositivo", "avrcp", "hid-compliant",
            "bluetooth hid", "unknown", "sconosciuto")
_MAC_RE = None


def _bt_mac(instance_id):
    """Bluetooth address (12 hex digits) taken from the device instance ID."""
    global _MAC_RE
    import re
    _MAC_RE = _MAC_RE or re.compile(r"(?:DEV_|&)([0-9A-Fa-f]{12})(?:_|\\|$)")
    m = _MAC_RE.search(instance_id or "")
    return m.group(1).lower() if m else None


def _bt_registry_name(mac):
    """Name the device announced to the PC (also shown in Settings > Bluetooth)."""
    if not mac or sys.platform != "win32":
        return None
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SYSTEM\CurrentControlSet\Services\BTHPORT\Parameters\Devices" + "\\" + mac) as k:
            raw, _ = winreg.QueryValueEx(k, "Name")
    except OSError:
        return None
    name = raw.split(b"\x00")[0].decode("utf-8", "ignore") if isinstance(raw, (bytes, bytearray)) else str(raw)
    return name.strip() or None


def _bt_kind(name):
    n = name.lower()
    for kind, words in (("mouse", ("mouse", "mx master", "mx anywhere", "m720", "m590", "trackball", "magic mouse")),
                        ("keyboard", ("keyboard", "tastiera", "keys", "mx keys", "k380", "k780", "craft")),
                        ("headset", ("headphone", "headset", "buds", "airpods", "cuffie", "auricolari", "earbuds", "wh-",
                                     "wf-", "jabra", "bose", "pods", "elite", "momentum", "qc ", "arctis", "freebuds")),
                        ("speaker", ("speaker", "soundbar", "boom", "flip", "charge ", "jbl", "echo", "altoparlante")),
                        ("pen", ("pen", "stylus", "penna", "pencil")),
                        ("gamepad", ("controller", "gamepad", "xbox", "dualsense", "dualshock", "joy-con", "pro controller")),
                        ("phone", ("iphone", "galaxy", "pixel", "phone", "telefono", "ipad"))):
        if any(w in n for w in words):
            return kind
    return "device"


def bluetooth_batteries():
    """Bluetooth device batteries via SetupAPI (no external process)."""
    if sys.platform != "win32":
        return []
    import ctypes
    from ctypes import wintypes

    class GUID(ctypes.Structure):
        _fields_ = [("d1", wintypes.DWORD), ("d2", wintypes.WORD), ("d3", wintypes.WORD), ("d4", ctypes.c_ubyte * 8)]

    class DEVPROPKEY(ctypes.Structure):
        _fields_ = [("fmtid", GUID), ("pid", wintypes.ULONG)]

    class SP_DEVINFO_DATA(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("ClassGuid", GUID), ("DevInst", wintypes.DWORD),
                    ("Reserved", ctypes.c_void_p)]

    def key(text, pid):
        import uuid
        b = uuid.UUID(text).bytes_le
        g = GUID.from_buffer_copy(b)
        return DEVPROPKEY(g, pid)

    BATTERY = key("104EA319-6EE2-4701-BD47-8DDBF425BBE5", 2)
    FRIENDLY = key("a45c254e-df1c-4efd-8020-67d146a850e0", 14)
    NAME = key("b725f130-47ef-101a-a5f1-02608c9eebac", 10)
    BUSNAME = key("540b947e-8b40-45bc-a8a2-6a0b894cbda2", 4)  # name reported by the Bluetooth device

    sa = ctypes.WinDLL("setupapi", use_last_error=True)
    sa.SetupDiGetClassDevsW.restype = ctypes.c_void_p
    sa.SetupDiGetClassDevsW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR, wintypes.HWND, wintypes.DWORD]
    sa.SetupDiEnumDeviceInfo.argtypes = [ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(SP_DEVINFO_DATA)]
    sa.SetupDiGetDevicePropertyW.argtypes = [ctypes.c_void_p, ctypes.POINTER(SP_DEVINFO_DATA),
                                             ctypes.POINTER(DEVPROPKEY), ctypes.POINTER(wintypes.ULONG),
                                             ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
                                             wintypes.DWORD]
    sa.SetupDiDestroyDeviceInfoList.argtypes = [ctypes.c_void_p]
    sa.SetupDiGetDeviceInstanceIdW.argtypes = [ctypes.c_void_p, ctypes.POINTER(SP_DEVINFO_DATA), wintypes.LPWSTR,
                                               wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]

    def prop(h, data, k):
        ptype, need = wintypes.ULONG(), wintypes.DWORD()
        buf = ctypes.create_string_buffer(512)
        if not sa.SetupDiGetDevicePropertyW(h, ctypes.byref(data), ctypes.byref(k), ctypes.byref(ptype),
                                            buf, len(buf), ctypes.byref(need), 0):
            return None
        if ptype.value == 0x12:  # DEVPROP_TYPE_STRING
            return ctypes.wstring_at(buf)
        return buf.raw[0]  # DEVPROP_TYPE_BYTE

    # all present devices: the Bluetooth "battery" property lives on the device node
    # (BTHENUM, BTHLE, but also HID\\{00001812...} for BLE mice/keyboards)
    best, scanned, with_batt, details = {}, 0, 0, []
    h = sa.SetupDiGetClassDevsW(None, None, None, 0x2 | 0x4)  # DIGCF_PRESENT | DIGCF_ALLCLASSES
    if not h or h == ctypes.c_void_p(-1).value:
        raise OSError(f"SetupDiGetClassDevs fallita (errore {ctypes.get_last_error()})")
    try:
        i = 0
        while True:
            data = SP_DEVINFO_DATA()
            data.cbSize = ctypes.sizeof(SP_DEVINFO_DATA)
            if not sa.SetupDiEnumDeviceInfo(h, i, ctypes.byref(data)):
                break
            i += 1
            scanned += 1
            batt = prop(h, data, BATTERY)
            if not isinstance(batt, int) or batt > 100:
                continue
            with_batt += 1
            buf = ctypes.create_unicode_buffer(512)
            iid = buf.value if sa.SetupDiGetDeviceInstanceIdW(h, ctypes.byref(data), buf, 512, None) else ""
            iid = buf.value or iid
            mac = _bt_mac(iid)
            raw = prop(h, data, BUSNAME) or prop(h, data, FRIENDLY) or prop(h, data, NAME) or ""
            raw = str(raw).replace("Hands-Free AG", "").replace("Avrcp Transport", "").strip(" -")
            reg = _bt_registry_name(mac)
            name = reg or ("" if raw.lower().startswith(_GENERIC) else raw)
            ident = mac or raw or iid
            cur = best.get(ident)
            if cur is None or (name and not cur["name"]) or batt > cur["battery"]:
                best[ident] = {"name": name or (cur or {}).get("name", ""), "battery": max(batt, (cur or {}).get("battery", 0)),
                               "mac": mac, "raw": raw}
            details.append((name or raw, mac, iid[:60]))
    finally:
        sa.SetupDiDestroyDeviceInfoList(h)
    bluetooth_batteries.last_stats = {"scanned": scanned, "with_battery": with_batt, "devices": details}
    out = []
    for d in best.values():
        short = ("BLE ·" + d["mac"][-4:]) if d["mac"] else (d["raw"] or t("device.bluetooth"))
        name = d["name"] or short
        out.append({"name": name, "battery": d["battery"], "kind": _bt_kind(name)})
    return sorted(out, key=lambda d: d["name"].lower())


bluetooth_batteries.last_stats = {}


class SystemMonitor:
    def __init__(self, settings, store):
        self._settings = settings
        self._store = store
        self.state = {"mic": [], "cam": [], "battery": None, "bluetooth": []}
        self._bt_low = set()
        self._batt_low = False

    def start(self):
        threading.Thread(target=self._fast_loop, daemon=True, name="system").start()
        threading.Thread(target=self._bt_loop, daemon=True, name="bluetooth").start()

    def _fast_loop(self):
        tick = 0
        while True:
            try:
                if self._settings.get("modules.privacy", True):
                    self.state["mic"] = apps_using("microphone")
                    self.state["cam"] = apps_using("webcam")
                else:
                    self.state["mic"], self.state["cam"] = [], []
                if tick % 10 == 0:
                    self._battery()
            except Exception:
                log.exception("system monitor")
            tick += 1
            time.sleep(1.5)

    def _battery(self):
        if not self._settings.get("modules.battery", True):
            self.state["battery"] = None
            return
        prev, cur = self.state["battery"], battery()
        self.state["battery"] = cur
        if not cur:
            return
        if prev and prev["plugged"] != cur["plugged"]:
            self._store.alert("info", "🔌" if cur["plugged"] else "🔋",
                              Msg("alert.charging" if cur["plugged"] else "alert.on_battery", pct=cur["percent"]),
                              sound=False)
        low = self._settings.get("alerts.battery_low", 20)
        if not cur["plugged"] and cur["percent"] <= low and not self._batt_low:
            self._batt_low = True
            self._store.alert("warn", "🪫", Msg("alert.battery_low", pct=cur["percent"]))
        elif cur["plugged"]:
            self._batt_low = False

    def _bt_loop(self):
        time.sleep(5)
        last = None
        while True:
            if self._settings.get("modules.bluetooth", True):
                try:
                    devs = bluetooth_batteries()
                except Exception:
                    log.exception("Could not read Bluetooth batteries")
                    devs = []
                aliases = self._settings.get("bluetooth_names", {}) or {}
                devs = [{**d, "name": aliases.get(d["name"], d["name"]), "kind": _bt_kind(aliases.get(d["name"], d["name"])) if d["name"] in aliases else d["kind"]}
                        for d in devs if aliases.get(d["name"], True) != ""]
                snapshot = (bluetooth_batteries.last_stats.get("scanned") is not None, devs)
                if snapshot != last:  # log only on change: useful to see what Windows reports
                    last = snapshot
                    log.info("Bluetooth: %s -> %s", bluetooth_batteries.last_stats, devs or "no device with a battery")
                self.state["bluetooth"] = devs
                low = self._settings.get("alerts.bluetooth_low", 15)
                for d in devs:
                    if d["battery"] <= low and d["name"] not in self._bt_low:
                        self._bt_low.add(d["name"])
                        self._store.alert("warn", "🎧", Msg("alert.device_battery_low", name=d["name"], pct=d["battery"]))
                    elif d["battery"] > low + 10:
                        self._bt_low.discard(d["name"])
            else:
                self.state["bluetooth"] = []
            time.sleep(120)
