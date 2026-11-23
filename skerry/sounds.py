"""System sounds for Skerry events."""
import sys
import threading


class Sounds:
    def __init__(self, settings):
        self._settings = settings

    def play(self, kind):
        if sys.platform != "win32" or not self._settings.get(f"sounds.{kind}", True):
            return
        import winsound
        flag = {"permission": winsound.MB_ICONEXCLAMATION, "alert": winsound.MB_ICONHAND,
                "timer": winsound.MB_OK}.get(kind, winsound.MB_ICONASTERISK)
        threading.Thread(target=winsound.MessageBeep, args=(flag,), daemon=True).start()
