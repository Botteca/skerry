"""Windows master volume (pycaw/Core Audio)."""
import logging
import queue
import sys
import threading
import time

log = logging.getLogger("skerry")


class Audio:
    def __init__(self):
        self._q = queue.Queue()
        self.volume = None   # 0..1
        self.muted = None
        self.available = False

    def start(self):
        if sys.platform == "win32":
            threading.Thread(target=self._run, daemon=True, name="audio").start()

    def _endpoint(self):
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        dev = AudioUtilities.GetSpeakers()
        ep = getattr(dev, "EndpointVolume", None)
        if ep is not None:
            return ep
        from ctypes import POINTER, cast

        from comtypes import CLSCTX_ALL
        return cast(dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None), POINTER(IAudioEndpointVolume))

    def _run(self):
        try:
            import comtypes
            comtypes.CoInitialize()
            ep = self._endpoint()
            self.available = True
        except Exception as e:
            log.info("Controllo volume via pycaw non disponibile (%s)", e)
            ep = None
        last_refresh = time.time()
        while True:
            try:
                cmd, val = self._q.get(timeout=0.5)
            except queue.Empty:
                cmd = None
            try:
                if ep is not None and time.time() - last_refresh > 10:
                    ep, last_refresh = self._endpoint(), time.time()  # follow the default device
                if cmd and ep is None:
                    pass
                elif cmd == "set":
                    ep.SetMasterVolumeLevelScalar(max(0.0, min(1.0, val)), None)
                elif cmd == "step":
                    cur = ep.GetMasterVolumeLevelScalar()
                    ep.SetMasterVolumeLevelScalar(max(0.0, min(1.0, cur + val)), None)
                    if cur + val > 0 and ep.GetMute():
                        ep.SetMute(0, None)
                elif cmd == "mute":
                    ep.SetMute(0 if ep.GetMute() else 1, None)
                if ep is not None:
                    self.volume = round(float(ep.GetMasterVolumeLevelScalar()), 3)
                    self.muted = bool(ep.GetMute())
            except Exception as e:
                log.debug("audio: %s", e)
                ep = None
                time.sleep(1)
                try:
                    ep = self._endpoint()
                except Exception:
                    pass

    def set(self, v):
        self._q.put(("set", float(v)))

    def step(self, delta):
        self._q.put(("step", float(delta)))

    def toggle_mute(self):
        self._q.put(("mute", None))

    def state(self):
        return {"volume": self.volume, "muted": self.muted} if self.volume is not None else None
