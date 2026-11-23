"""Timer and Pomodoro."""
import threading
import time

from .i18n import Msg, render


class Timer:
    def __init__(self, settings, store, on_finish=None):
        self._settings = settings
        self._store = store
        self._on_finish = on_finish or (lambda: None)
        self._lock = threading.Lock()
        self._t = None  # {"mode","phase","ends_at","duration","paused_left","cycle","label"}

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="timer").start()

    def _set(self, mode, minutes, phase="focus", cycle=1):
        dur = float(minutes) * 60
        self._t = {"mode": mode, "phase": phase, "duration": dur, "ends_at": time.time() + dur,
                   "paused_left": None, "cycle": cycle,
                   "label": Msg("timer." + phase) if mode == "pomodoro" else Msg("timer.minutes", n=int(minutes))}

    def start_timer(self, minutes):
        with self._lock:
            self._set("timer", minutes)

    def start_pomodoro(self):
        with self._lock:
            self._set("pomodoro", self._settings.get("pomodoro.focus", 25))

    def stop(self):
        with self._lock:
            self._t = None

    def toggle_pause(self):
        with self._lock:
            t = self._t
            if not t:
                return
            if t["paused_left"] is None:
                t["paused_left"] = max(0.0, t["ends_at"] - time.time())
            else:
                t["ends_at"] = time.time() + t["paused_left"]
                t["paused_left"] = None

    def _loop(self):
        while True:
            time.sleep(0.5)
            with self._lock:
                t = self._t
                if not t or t["paused_left"] is not None or time.time() < t["ends_at"]:
                    continue
                if t["mode"] == "timer":
                    self._t = None
                    self._store.alert("info", "⏰", Msg("alert.timer_done", label=t["label"]), sound=False)
                else:
                    p = self._settings.get("pomodoro", {})
                    if t["phase"] == "focus":
                        long_ = t["cycle"] % int(p.get("cycles", 4)) == 0
                        phase = "long_break" if long_ else "short_break"
                        self._set("pomodoro", p.get(phase, 15 if long_ else 5), phase, t["cycle"])
                        self._store.alert("info", "🍅", Msg("alert.pomodoro_break"), sound=False)
                    else:
                        self._set("pomodoro", p.get("focus", 25), "focus", t["cycle"] + 1)
                        self._store.alert("info", "🍅", Msg("alert.pomodoro_back"), sound=False)
            self._on_finish()

    def state(self):
        with self._lock:
            t = self._t
            if not t:
                return None
            left = t["paused_left"] if t["paused_left"] is not None else max(0.0, t["ends_at"] - time.time())
            return {"mode": t["mode"], "phase": t["phase"], "label": render(t["label"]), "left": left,
                    "duration": t["duration"], "paused": t["paused_left"] is not None, "cycle": t["cycle"]}
