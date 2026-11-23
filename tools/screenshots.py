"""Regenerate the README screenshots in docs/img/ from invented demo data.

    python tools/screenshots.py              # English -> docs/img/, Italian -> docs/img/it/
    python tools/screenshots.py --lang en    # one language only

The pill state comes from the real code (Store fed with fake hook events, Timer, pick_meeting, i18n), so actions,
labels and alerts are translated exactly as in the app. The UI files are copied to a temporary folder with a fake
`window.pywebview.api` and rendered by headless Microsoft Edge (or Chrome). Nothing touches the network, the real
settings or the real agents' configuration.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from skerry import VERSION, i18n  # noqa: E402
from skerry.connectors.m365 import pick_meeting  # noqa: E402
from skerry.settings import DEFAULTS  # noqa: E402
from skerry.store import Store  # noqa: E402
from skerry.timer import Timer  # noqa: E402

BROWSERS = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe"]
BACKGROUNDS = {
    "a": "linear-gradient(90deg,#c25aa3 0%,#7b67bd 38%,#3a73c9 70%,#2b6fcd 100%)",
    "b": "radial-gradient(120% 90% at 0% 0%,#5b3cc4 0%,transparent 55%),"
         "radial-gradient(120% 90% at 100% 0%,#d9644f 0%,transparent 55%),"
         "radial-gradient(120% 100% at 0% 100%,#c85aa0 0%,transparent 60%),#2b6fcd",
}


class FakeSettings(dict):
    def __init__(self, lang):
        super().__init__(json.loads(json.dumps(DEFAULTS)))
        self["language"] = lang

    def get(self, key, default=None):
        cur = self
        for part in key.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return default
            cur = cur[part]
        return cur


# ------------------------------------------------------------------ demo data (all invented)

def agent_store(settings):
    """Two Claude Code sessions: one running tests with a task list, one waiting for input."""
    st = Store(settings)
    a = {"session_id": "demo-a", "cwd": "C:/rep/web-shop"}
    st.handle("SessionStart", {**a, "source": "startup", "model": "Opus"})
    titles = {"en": ("Add cart API", "Write tests", "Fix checkout", "Run tests", "Update docs"),
              "it": ("API del carrello", "Scrivere i test", "Correggere il checkout", "Eseguire i test",
                     "Aggiornare la documentazione")}[settings["language"]]
    todos = [{"content": c, "activeForm": c, "status": s} for c, s in
             zip(titles, ("completed", "completed", "completed", "in_progress", "pending"))]
    st.handle("PreToolUse", {**a, "tool_name": "TodoWrite", "tool_input": {"todos": todos}})
    st.handle("PreToolUse", {**a, "tool_name": "Bash", "tool_input": {"command": "pytest -q"}})
    st.statusline({"session_id": "demo-a", "cwd": "C:/rep/web-shop", "model": {"display_name": "Opus"},
                   "context_window": {"used_percentage": 62}, "cost": {"total_cost_usd": 1.8},
                   "rate_limits": {"five_hour": {"used_percentage": 38, "resets_at": time.time() + 2 * 3600 + 900},
                                   "seven_day": {"used_percentage": 21, "resets_at": time.time() + 3 * 86400}}})
    b = {"session_id": "demo-b", "cwd": "C:/rep/data-pipeline"}
    st.handle("UserPromptSubmit", b)
    st.handle("Notification", {**b, "notification_type": "idle_prompt"})
    st.statusline({"session_id": "demo-b", "cwd": "C:/rep/data-pipeline", "context_window": {"used_percentage": 35}})
    st._alerts.clear()                       # no context/limit alert popping over the screenshots
    return st


def done_store(settings):
    st = Store(settings)
    s = {"session_id": "demo-c", "cwd": "C:/rep/data-pipeline"}
    st.handle("UserPromptSubmit", s)
    st.handle("Stop", {**s, "last_assistant_message": {
        "en": "Added retry with backoff and the tests: 14 passed.",
        "it": "Ho aggiunto il retry con backoff e i test: 14 passati."}[settings["language"]]})
    return st


def permission_snapshot(settings):
    st = Store(settings)
    payload = {"session_id": "demo-d", "cwd": "C:/rep/api-gateway", "tool_name": "Bash",
               "tool_input": {"command": "npm run build && npm test -- --coverage"},
               "permission_suggestions": [{"type": "addRules", "behavior": "allow"}]}
    th = threading.Thread(target=st.request_permission, args=(payload, 10), daemon=True)
    th.start()
    for _ in range(200):
        snap = st.snapshot()
        if snap["pending"]:
            break
        time.sleep(0.01)
    st.decide(snap["pending"][0]["id"], "terminal")
    th.join(2)
    return snap


def pomodoro_state(settings):
    timer = Timer(settings, Store(settings))
    timer.start_pomodoro()
    timer._t["paused_left"] = 17 * 60        # frozen at 17:00 for the picture
    state = timer.state()
    state["paused"] = False
    return state


def meeting(now):
    def graph(dt):
        return {"dateTime": dt.strftime("%Y-%m-%dT%H:%M:%S.0000000"), "timeZone": "UTC"}
    start = datetime.fromtimestamp(now, timezone.utc) + timedelta(minutes=13)
    return pick_meeting([{"id": "m1", "subject": "Sprint review", "start": graph(start),
                          "end": graph(start + timedelta(minutes=47)), "isOnlineMeeting": True,
                          "onlineMeetingProvider": "teamsForBusiness",
                          "onlineMeeting": {"joinUrl": "https://teams.example.invalid/meet/1"}}], now)


MEDIA = {"title": "Blue Hour", "artist": "Lumen", "app": "Music", "playing": True, "position": 74, "duration": 231,
         "thumb_id": 0}
BLUETOOTH = [{"name": "Contoso Mouse", "battery": 82, "kind": "mouse"},
             {"name": "Fabrikam Keys", "battery": 64, "kind": "keyboard"},
             {"name": "Northwind Buds", "battery": 27, "kind": "headset"}]
USAGE = {"h5": {"requests": 63, "input": 210_000, "output": 380_000, "cache_write": 810_000, "cache_read": 9_400_000,
                "tokens": 1_400_000},
         "d7": {"requests": 910, "input": 2_100_000, "output": 3_900_000, "cache_write": 7_000_000,
                "cache_read": 120_000_000, "tokens": 13_000_000},
         "days": [1_200_000, 2_600_000, 700_000, 3_100_000, 2_400_000, 150_000, 1_400_000]}


def pill_state(settings, store=None, **extra):
    now = time.time()
    snap = dict(store) if isinstance(store, dict) else (store or Store(settings)).snapshot()
    snap.update({"media": None, "audio": {"volume": 0.55, "muted": False},
                 "system": {"mic": [], "cam": [], "battery": None, "bluetooth": []}, "usage": None, "timer": None,
                 "meeting": None, "shelf": [], "update": None, "version": VERSION, "lang": settings["language"],
                 "settings": {k: settings[k] for k in ("edge", "theme", "accent", "modules")}, "now": now})
    snap.update(extra)
    if snap["media"]:
        snap["media"] = {**snap["media"], "updated": now}
    return snap


def scenes(settings):
    lang = settings["language"]
    agents = agent_store(settings)
    working = pill_state(settings, agents)
    working["selected"] = working["sessions"][0]["sid"] if working["sessions"][0]["project"] == "web-shop" \
        else working["sessions"][1]["sid"]
    music = pill_state(settings, media=MEDIA)
    pomo = pill_state(settings, timer=pomodoro_state(settings))
    done = pill_state(settings, done_store(settings))
    perm = pill_state(settings, permission_snapshot(settings))
    perm["sessions"] = []
    expanded = pill_state(settings, agents, media=MEDIA, meeting=meeting(time.time()), usage=USAGE,
                          system={"mic": [], "cam": [], "battery": {"percent": 74, "plugged": False},
                                  "bluetooth": BLUETOOTH})
    expanded["_expand"] = True
    settings_data = {"settings": dict(settings), "version": VERSION, "autostart": True,
                     "claude": {"installed": True, "available": True},
                     "codex": {"installed": True, "available": True},
                     "gemini": {"installed": False, "available": False},
                     "copilot": {"installed": False, "available": True},
                     "monitors": [], "log_dir": r"C:\Users\you\AppData\Local\Skerry\logs", "update": None,
                     "connectors": {"m365": {"status": "ok", "account": "ada@example.invalid", "error": ""},
                                    "adf": {"configured": False, "status": "off", "error": "", "updated": 0,
                                            "has_secret": False}},
                     "lang": lang}
    return {
        "00-compact-states": {"bg": "a", "size": (750, 720), "pills": [working, music, pomo, done, perm]},
        "01-agent": {"bg": "a", "size": (600, 160), "pills": [working]},
        "02-music": {"bg": "a", "size": (600, 160), "pills": [music]},
        "03-timer": {"bg": "a", "size": (600, 160), "pills": [pomo]},
        "04-permission": {"bg": "a", "size": (640, 300), "pills": [perm]},
        "05-done": {"bg": "a", "size": (640, 220), "pills": [done]},
        "06-expanded": {"bg": "b", "size": (1080, 1000), "pills": [expanded]},
        "07-settings-appearance": {"bg": "b", "size": (950, 740), "settings": (settings_data, "look")},
        "07-settings-modules": {"bg": "b", "size": (950, 740), "settings": (settings_data, "mods")},
        "07-settings-connections": {"bg": "b", "size": (950, 740), "settings": (settings_data, "conn")},
    }


# ------------------------------------------------------------------ HTML harness

# No motion, except the equalizer bars, which get fixed heights so they show up in a still picture.
NO_MOTION = ("<style>*,*::before,*::after{animation:none!important;transition:none!important}"
             ".eq i:nth-child(1){height:9px}.eq i:nth-child(2){height:14px}.eq i:nth-child(3){height:6px}"
             ".eq i:nth-child(4){height:11px}</style>")

PILL_MOCK = """<script>
(() => {
  const P = new URLSearchParams(location.search), id = P.get('id');
  const state = %s[id];
  let calls = 0;
  window.pywebview = {api: {
    get_state: async () => { calls++; return {...state, ui_seq: state._expand && calls > 1 ? 1 : 0}; },
    get_thumb: async () => null,
    resize: (w, h, r) => parent.postMessage({id, w, h, r}, '*'),
  }};
  for (const name of ['decide','dismiss_alert','focus_session','media','toggle_mute','media_seek','timer_start',
    'pomodoro_start','timer_stop','timer_toggle_pause','set_volume','volume_step','cycle_session','drag_start',
    'open_settings','join_meeting','install_update','log']) window.pywebview.api[name] = async () => null;
  addEventListener('load', () => dispatchEvent(new Event('pywebviewready')));
})();
</script>"""

SETTINGS_MOCK = """<script>
(() => {
  const data = %s, page = %s;
  window.pywebview = {api: new Proxy({get_settings: async () => data}, {get: (o, k) => o[k] || (async () => true)})};
  addEventListener('load', () => {
    dispatchEvent(new Event('pywebviewready'));
    setTimeout(() => show(page), 50);
  });
})();
</script>"""

PAGE = """<!DOCTYPE html><html><head><meta charset="utf-8"><style>
html,body{margin:0;height:100%%;overflow:hidden}
body{background:%s;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:%dpx}
.pill{border:0;display:block;background:#000;box-shadow:0 18px 40px rgba(0,0,0,.35),0 2px 8px rgba(0,0,0,.25)}
.win{border:0;display:block;width:820px;height:640px;border-radius:18px;box-shadow:0 24px 60px rgba(0,0,0,.4)}
</style></head><body>%s
<script>
addEventListener('message', e => {
  const f = document.getElementById('f' + e.data.id);
  if (!f) return;
  f.style.width = e.data.w + 'px'; f.style.height = e.data.h + 'px'; f.style.borderRadius = e.data.r + 'px';
});
</script></body></html>"""


def build(tmp, scene, name):
    ui = os.path.join(ROOT, "ui")
    for f in ("skerry.css", "i18n.js", "skerry.js"):
        shutil.copy(os.path.join(ui, f), tmp)
    if "settings" in scene:
        data, page = scene["settings"]
        src = open(os.path.join(ui, "settings.html"), encoding="utf-8").read()
        src = src.replace("</head>", NO_MOTION + "</head>").replace(
            '<script src="i18n.js"></script>', SETTINGS_MOCK % (json.dumps(data), json.dumps(page))
            + '<script src="i18n.js"></script>')
        frame = f"settings-{name}.html"
        with open(os.path.join(tmp, frame), "w", encoding="utf-8") as fh:
            fh.write(src)
        body = f'<iframe class="win" src="{frame}"></iframe>'
        gap = 0
    else:
        states = {str(i): s for i, s in enumerate(scene["pills"])}
        src = open(os.path.join(ui, "index.html"), encoding="utf-8").read()
        src = src.replace("</head>", NO_MOTION + "</head>").replace(
            '<script src="i18n.js"></script>', PILL_MOCK % json.dumps(states) + '<script src="i18n.js"></script>')
        frame = f"pill-{name}.html"
        with open(os.path.join(tmp, frame), "w", encoding="utf-8") as fh:
            fh.write(src)
        body = "".join(f'<iframe class="pill" id="f{i}" src="{frame}?id={i}" style="width:600px;height:40px">'
                       f"</iframe>" for i in states)
        gap = 70 if len(states) > 1 else 0
    page = os.path.join(tmp, f"{name}.html")
    with open(page, "w", encoding="utf-8") as fh:
        fh.write(PAGE % (BACKGROUNDS[scene["bg"]], gap, body))
    return page


def shoot(browser, page, out, size, profile):
    w, h = size
    cmd = [browser, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
           "--disable-extensions", f"--user-data-dir={profile}", "--force-device-scale-factor=2",
           f"--window-size={w},{h}", "--virtual-time-budget=4000", f"--screenshot={out}",
           "file:///" + page.replace("\\", "/")]
    subprocess.run(cmd, check=True, capture_output=True, timeout=120)
    if not os.path.exists(out):
        raise RuntimeError(f"no screenshot produced for {page}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--lang", choices=i18n.LANGUAGES, action="append")
    args = ap.parse_args()
    browser = next((b for b in BROWSERS if os.path.exists(b)), None)
    if not browser:
        sys.exit("Microsoft Edge or Google Chrome is needed")
    for lang in args.lang or list(i18n.LANGUAGES):
        i18n.set_language(lang)
        out_dir = os.path.join(ROOT, "docs", "img", "" if lang == "en" else lang)
        os.makedirs(out_dir, exist_ok=True)
        settings = FakeSettings(lang)
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as profile:
            for name, scene in scenes(settings).items():
                out = os.path.join(out_dir, name + ".png")
                shoot(browser, build(tmp, scene, name), out, scene["size"], profile)
                print("wrote", os.path.relpath(out, ROOT))


if __name__ == "__main__":
    main()
