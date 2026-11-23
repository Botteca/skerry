"""User-facing strings produced by Python: tray menu, alerts, agent actions and errors shown in the UI.

Log messages stay in English and never go through this module.

English is the reference language: every key must exist in every language (tests/test_i18n.py checks it).
A value is a string with {placeholders}, or {"one": ..., "other": ...} for plurals chosen by the `n` parameter.

Text that is stored and shown later (alerts, session actions, errors) is kept as a `Msg` and rendered when the
state is sent to the UI, so a language change applies immediately, also to what is already on screen.
"""
import logging
import os
import sys
import threading

log = logging.getLogger("skerry")

LANGUAGES = ("en", "it")
DEFAULT = "en"

STRINGS = {
    "en": {
        # tray
        "tray.expand": "Expand / collapse",
        "tray.settings": "Settings…",
        "tray.pause": "Pause",
        "tray.reconnect": "Reconnect Claude Code / Codex",
        "tray.autostart": "Start with Windows",
        "tray.check_updates": "Check for updates",
        "tray.install_update": "Install update {version}",
        "tray.logs": "Open log folder",
        "tray.quit": "Quit",
        # agent actions
        "action.read": "Reading {file}",
        "action.write": "Writing {file}",
        "action.edit": "Editing {file}",
        "action.patch": "Applying a change to files",
        "action.search": "Searching {pattern}",
        "action.fetch": "Opening {url}",
        "action.web_search": "Searching the web: {query}",
        "action.agent": "Agent: {description}",
        "action.tasks": "Updating the task list",
        "action.generic": "Action",
        "action.thinking": "Thinking…",
        "action.working": "Working…",
        "action.error": "Error: {action}",
        "action.waiting": "Waiting for you",
        "action.terminal_permission": "Asks for permission: answer in the terminal",
        "action.done": "Done",
        "action.failed": "Stopped by an error",
        "perm.denied": "Denied by the user in Skerry",
        # alerts
        "alert.session": "Session",
        "alert.context": "{project}: context at {pct}%. Consider /compact or a new session.",
        "limit.five_hour": "5-hour limit",
        "limit.seven_day": "Weekly limit",
        "limit.spend": "Spending limit",
        "alert.limit": "{label} at {pct}%",
        "alert.limit_reset": "{label} at {pct}% · resets in {h}h {m}m",
        "alert.charging": "Charging · {pct}%",
        "alert.on_battery": "On battery · {pct}%",
        "alert.battery_low": "Battery at {pct}%: plug in the charger",
        "alert.device_battery_low": "{name}: battery at {pct}%",
        "alert.timer_done": "{label}: time's up",
        "alert.pomodoro_break": "Pomodoro done: take a break!",
        "alert.pomodoro_back": "Break over: back to work",
        "alert.meeting_soon": {"one": "{title} in {n} min", "other": "{title} in {n} min"},
        "alert.reconnected": "Claude Code connected: restart open sessions",
        "alert.connect_failed": "Connection failed (see log)",
        "alert.update_available": "Skerry {version} is available",
        "alert.update_ready": "Update to v{version} ready: it installs at a quiet moment",
        "alert.update_dev": "In development, update with git pull",
        # timer
        "timer.focus": "Focus",
        "timer.short_break": "Short break",
        "timer.long_break": "Long break",
        "timer.minutes": "Timer {n} min",
        # meetings and connectors
        "meeting.untitled": "(untitled)",
        "m365.need_client_id": "Enter the application (client) ID first.",
        "m365.need_msal": "The msal library is missing: run setup_dev.bat to install it.",
        "m365.network": "Network unreachable",
        "m365.cancelled": "Sign-in cancelled",
        "device.bluetooth": "Bluetooth device",
        "update.err_check": "Could not check for updates (see log)",
        "update.err_assets": "The release has no installer or SHA256SUMS.txt",
        "update.err_download": "Download failed (see log)",
        "update.err_hash": "Download discarded: the SHA-256 checksum does not match",
        "update.err_install": "Could not start the installer (see log)",
        "m365.graph_error": "Microsoft Graph {code}: {message}",
    },
    "it": {
        "tray.expand": "Espandi / riduci",
        "tray.settings": "Impostazioni…",
        "tray.pause": "Pausa",
        "tray.reconnect": "Ricollega Claude Code / Codex",
        "tray.autostart": "Avvia con Windows",
        "tray.check_updates": "Cerca aggiornamenti",
        "tray.install_update": "Installa aggiornamento {version}",
        "tray.logs": "Apri cartella log",
        "tray.quit": "Esci",
        "action.read": "Legge {file}",
        "action.write": "Scrive {file}",
        "action.edit": "Modifica {file}",
        "action.patch": "Applica una modifica ai file",
        "action.search": "Cerca {pattern}",
        "action.fetch": "Apre {url}",
        "action.web_search": "Cerca sul web: {query}",
        "action.agent": "Agente: {description}",
        "action.tasks": "Aggiorna la lista dei task",
        "action.generic": "Azione",
        "action.thinking": "Sta pensando…",
        "action.working": "Sta lavorando…",
        "action.error": "Errore: {action}",
        "action.waiting": "Ti aspetta",
        "action.terminal_permission": "Chiede un permesso: rispondi nel terminale",
        "action.done": "Fatto",
        "action.failed": "Interrotto per errore",
        "perm.denied": "Negato dall'utente da Skerry",
        "alert.session": "Sessione",
        "alert.context": "{project}: contesto al {pct}%. Valuta /compact o una nuova sessione.",
        "limit.five_hour": "Limite 5 ore",
        "limit.seven_day": "Limite settimanale",
        "limit.spend": "Limite di spesa",
        "alert.limit": "{label} al {pct}%",
        "alert.limit_reset": "{label} al {pct}% · reset tra {h}h {m}m",
        "alert.charging": "In carica · {pct}%",
        "alert.on_battery": "A batteria · {pct}%",
        "alert.battery_low": "Batteria al {pct}%: collega l'alimentatore",
        "alert.device_battery_low": "{name}: batteria al {pct}%",
        "alert.timer_done": "{label}: tempo scaduto",
        "alert.pomodoro_break": "Pomodoro completato: pausa!",
        "alert.pomodoro_back": "Pausa finita: si torna al lavoro",
        "alert.meeting_soon": {"one": "{title} tra {n} min", "other": "{title} tra {n} min"},
        "alert.reconnected": "Claude Code collegato: riavvia le sessioni aperte",
        "alert.connect_failed": "Collegamento non riuscito (vedi log)",
        "alert.update_available": "Disponibile Skerry {version}",
        "alert.update_ready": "Aggiornamento a v{version} pronto: si installa in un momento tranquillo",
        "alert.update_dev": "In sviluppo aggiorna con git pull",
        "timer.focus": "Concentrazione",
        "timer.short_break": "Pausa breve",
        "timer.long_break": "Pausa lunga",
        "timer.minutes": "Timer {n} min",
        "meeting.untitled": "(senza titolo)",
        "m365.need_client_id": "Inserisci prima l'ID applicazione (client ID).",
        "m365.need_msal": "Manca la libreria msal: esegui setup_dev.bat per installarla.",
        "m365.network": "Rete non raggiungibile",
        "m365.cancelled": "Accesso annullato",
        "device.bluetooth": "Dispositivo Bluetooth",
        "update.err_check": "Controllo aggiornamenti non riuscito (vedi log)",
        "update.err_assets": "La release non contiene l'installer o SHA256SUMS.txt",
        "update.err_download": "Download non riuscito (vedi log)",
        "update.err_hash": "Download scartato: il checksum SHA-256 non corrisponde",
        "update.err_install": "Impossibile avviare l'installer (vedi log)",
        "m365.graph_error": "Microsoft Graph {code}: {message}",
    },
}

_lock = threading.Lock()
_lang = DEFAULT


def system_language():
    """Windows display language reduced to a supported language ('en' when unsupported)."""
    if sys.platform == "win32":
        try:
            import ctypes
            langid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            primary = langid & 0x3FF
            return {0x10: "it", 0x09: "en"}.get(primary, DEFAULT)
        except Exception:
            log.debug("Could not read the Windows UI language", exc_info=True)
            return DEFAULT
    code = (os.environ.get("LC_ALL") or os.environ.get("LC_MESSAGES") or os.environ.get("LANG") or "")[:2].lower()
    return code if code in LANGUAGES else DEFAULT


def resolve(preference):
    """'auto' (or anything unknown) -> system language; 'en' / 'it' -> itself."""
    return preference if preference in LANGUAGES else system_language()


def set_language(preference):
    """Apply the `language` setting. Returns the language now in use."""
    global _lang
    lang = resolve(preference)
    with _lock:
        changed, _lang = lang != _lang, lang
    if changed:
        log.info("Language: %s (setting %r)", lang, preference)
    return lang


def current():
    return _lang


def _plural(lang, n):
    if lang in ("en", "it"):
        return "one" if n == 1 else "other"
    return "other"


def t(key, lang=None, **params):
    """Translate `key` into the current language; params may themselves be `Msg` objects."""
    lang = lang or _lang
    value = STRINGS.get(lang, {}).get(key)
    if value is None:
        value = STRINGS[DEFAULT].get(key)
    if value is None:
        log.warning("Missing translation key %r", key)
        return key
    if isinstance(value, dict):
        value = value.get(_plural(lang, params.get("n", 0)), value["other"])
    if not params:
        return value
    rendered = {k: (v.render(lang) if isinstance(v, Msg) else v) for k, v in params.items()}
    try:
        return value.format(**rendered)
    except (KeyError, IndexError, ValueError):
        log.warning("Bad parameters for translation key %r", key)
        return value


class Msg:
    """A translatable message rendered later, in the language in use at that moment."""
    __slots__ = ("key", "params")

    def __init__(self, key, **params):
        self.key, self.params = key, params

    def render(self, lang=None):
        return t(self.key, lang, **self.params)

    def __str__(self):
        return self.render()

    def __repr__(self):
        return f"Msg({self.key!r}, {self.params!r})"

    def __eq__(self, other):
        return isinstance(other, Msg) and (self.key, self.params) == (other.key, other.params)

    __hash__ = None


def render(value):
    """str for a Msg, anything else unchanged (plain text such as file names or messages from the agent)."""
    return value.render() if isinstance(value, Msg) else value
