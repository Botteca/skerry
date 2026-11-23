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

LANGUAGES = ("en", "it", "es", "de", "fr")
DEFAULT = "en"

STRINGS = {
    "en": {
        "outlook.not_running": "Classic Outlook is not open: the meeting appears when you open it",
        "outlook.no_com": "Outlook cannot be read: the COM component is missing",
        "outlook.failed": "Could not read the Outlook calendar (see log)",
        "ics.bad_url": "Paste an https:// or webcal:// calendar link",
        "ics.http_error": "The calendar link answered {code}: check that the calendar is still published",
        "ics.bad_data": "The link does not return a calendar (.ics)",
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
        "azure.no_cli": "Azure CLI not found: install it and run az login, or use a service principal.",
        "azure.cli_failed": "az login needed? {message}",
        "azure.cli_timeout": "The Azure CLI did not answer in time",
        "azure.sp_incomplete": "Enter tenant ID, client ID and client secret.",
        "azure.sign_in_failed": "Sign-in refused: {message}",
        "azure.http_error": "Azure {code}: {message}",
        "azure.network": "Azure unreachable",
        "alert.adf_failed": "Data Factory: {pipeline} failed",
        "tray.profile": "Profile",
        "profile.work": "Work",
        "profile.present": "Presentation",
        "profile.focus": "Focus",
        "alert.profile": "Profile: {name}",
        "google.need_client": "Enter the client ID and the client secret first.",
        "google.cancelled": "Sign-in not completed",
        "google.sign_in_failed": "Sign-in refused: {message}",
        "google.expired": "Access expired or revoked: sign in again.",
        "google.http_error": "Google Calendar {code}: {message}",
        "google.browser_ok": "Skerry is connected to Google Calendar. You can close this window.",
        "google.browser_fail": "Sign-in not completed. You can close this window and try again from Skerry.",
        "sql.err_empty": "Write a query.",
        "sql.err_not_select": "Only queries that start with SELECT or WITH are allowed.",
        "sql.err_multiple": "Only one statement: remove the semicolons.",
        "sql.err_write": "The query contains a command that writes or changes something: only reading is allowed.",
        "sql.err_driver": "Microsoft ODBC Driver 17 or 18 for SQL Server is not installed.",
        "sql.err_pyodbc": "The pyodbc library is missing: run setup_dev.bat to install it.",
        "sql.err_server": "Enter the server.",
        "sql.err_login": "Enter user and password.",
        "alert.sql_red": "{name}: {value}",
    },
    "it": {
        "outlook.not_running": "Outlook classico non è aperto: la riunione compare quando lo apri",
        "outlook.no_com": "Impossibile leggere Outlook: manca il componente COM",
        "outlook.failed": "Impossibile leggere il calendario di Outlook (vedi log)",
        "ics.bad_url": "Incolla un link del calendario https:// o webcal://",
        "ics.http_error": "Il link del calendario ha risposto {code}: controlla che il calendario sia ancora pubblicato",
        "ics.bad_data": "Il link non restituisce un calendario (.ics)",
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
        "azure.no_cli": "Azure CLI non trovata: installala ed esegui az login, oppure usa un service principal.",
        "azure.cli_failed": "Serve az login? {message}",
        "azure.cli_timeout": "La Azure CLI non ha risposto in tempo",
        "azure.sp_incomplete": "Inserisci tenant ID, client ID e client secret.",
        "azure.sign_in_failed": "Accesso rifiutato: {message}",
        "azure.http_error": "Azure {code}: {message}",
        "azure.network": "Azure non raggiungibile",
        "alert.adf_failed": "Data Factory: {pipeline} non riuscita",
        "tray.profile": "Profilo",
        "profile.work": "Lavoro",
        "profile.present": "Presentazione",
        "profile.focus": "Concentrazione",
        "alert.profile": "Profilo: {name}",
        "google.need_client": "Inserisci prima il client ID e il client secret.",
        "google.cancelled": "Accesso non completato",
        "google.sign_in_failed": "Accesso rifiutato: {message}",
        "google.expired": "Accesso scaduto o revocato: accedi di nuovo.",
        "google.http_error": "Google Calendar {code}: {message}",
        "google.browser_ok": "Skerry è collegato a Google Calendar. Puoi chiudere questa finestra.",
        "google.browser_fail": "Accesso non completato. Puoi chiudere questa finestra e riprovare da Skerry.",
        "sql.err_empty": "Scrivi una query.",
        "sql.err_not_select": "Sono ammesse solo query che iniziano con SELECT o WITH.",
        "sql.err_multiple": "Una sola istruzione: togli i punti e virgola.",
        "sql.err_write": "La query contiene un comando che scrive o modifica qualcosa: è ammessa solo la lettura.",
        "sql.err_driver": "Microsoft ODBC Driver 17 o 18 per SQL Server non è installato.",
        "sql.err_pyodbc": "Manca la libreria pyodbc: esegui setup_dev.bat per installarla.",
        "sql.err_server": "Inserisci il server.",
        "sql.err_login": "Inserisci utente e password.",
        "alert.sql_red": "{name}: {value}",
    },
    "es": {
        "outlook.not_running": "Outlook clásico no está abierto: la reunión aparece cuando lo abras",
        "outlook.no_com": "No se puede leer Outlook: falta el componente COM",
        "outlook.failed": "No se ha podido leer el calendario de Outlook (ver registro)",
        "ics.bad_url": "Pega un enlace de calendario https:// o webcal://",
        "ics.http_error": "El enlace del calendario respondió {code}: comprueba que el calendario siga publicado",
        "ics.bad_data": "El enlace no devuelve un calendario (.ics)",
        "tray.expand": "Ampliar / reducir",
        "tray.settings": "Ajustes…",
        "tray.pause": "Pausa",
        "tray.reconnect": "Volver a conectar Claude Code / Codex",
        "tray.autostart": "Iniciar con Windows",
        "tray.check_updates": "Buscar actualizaciones",
        "tray.install_update": "Instalar la actualización {version}",
        "tray.logs": "Abrir la carpeta de registros",
        "tray.quit": "Salir",
        "action.read": "Leyendo {file}",
        "action.write": "Escribiendo {file}",
        "action.edit": "Editando {file}",
        "action.patch": "Aplicando un cambio a los archivos",
        "action.search": "Buscando {pattern}",
        "action.fetch": "Abriendo {url}",
        "action.web_search": "Buscando en la web: {query}",
        "action.agent": "Agente: {description}",
        "action.tasks": "Actualizando la lista de tareas",
        "action.generic": "Acción",
        "action.thinking": "Pensando…",
        "action.working": "Trabajando…",
        "action.error": "Error: {action}",
        "action.waiting": "Esperándote",
        "action.terminal_permission": "Pide permiso: responde en el terminal",
        "action.done": "Hecho",
        "action.failed": "Detenido por un error",
        "perm.denied": "Denegado por el usuario en Skerry",
        "alert.session": "Sesión",
        "alert.context": "{project}: contexto al {pct}%. Considera /compact o una nueva sesión.",
        "limit.five_hour": "Límite de 5 horas",
        "limit.seven_day": "Límite semanal",
        "limit.spend": "Límite de gasto",
        "alert.limit": "{label} al {pct}%",
        "alert.limit_reset": "{label} al {pct}% · se restablece en {h}h {m}m",
        "alert.charging": "Cargando · {pct}%",
        "alert.on_battery": "Con batería · {pct}%",
        "alert.battery_low": "Batería al {pct}%: conecta el cargador",
        "alert.device_battery_low": "{name}: batería al {pct}%",
        "alert.timer_done": "{label}: se acabó el tiempo",
        "alert.pomodoro_break": "Pomodoro terminado: ¡tómate un descanso!",
        "alert.pomodoro_back": "Fin del descanso: de vuelta al trabajo",
        "alert.meeting_soon": {"one": "{title} en {n} min", "other": "{title} en {n} min"},
        "alert.reconnected": "Claude Code conectado: reinicia las sesiones abiertas",
        "alert.connect_failed": "La conexión ha fallado (ver registro)",
        "alert.update_available": "Skerry {version} está disponible",
        "alert.update_ready": "Actualización a v{version} lista: se instala en un momento tranquilo",
        "alert.update_dev": "En desarrollo, actualiza con git pull",
        "timer.focus": "Concentración",
        "timer.short_break": "Pausa corta",
        "timer.long_break": "Pausa larga",
        "timer.minutes": "Temporizador {n} min",
        "meeting.untitled": "(sin título)",
        "m365.need_client_id": "Primero introduce el ID de aplicación (cliente).",
        "m365.need_msal": "Falta la biblioteca msal: ejecuta setup_dev.bat para instalarla.",
        "m365.network": "Red no disponible",
        "m365.cancelled": "Inicio de sesión cancelado",
        "device.bluetooth": "Dispositivo Bluetooth",
        "update.err_check": "No se han podido buscar actualizaciones (ver registro)",
        "update.err_assets": "La versión no tiene instalador o SHA256SUMS.txt",
        "update.err_download": "La descarga ha fallado (ver registro)",
        "update.err_hash": "Descarga descartada: la suma de comprobación SHA-256 no coincide",
        "update.err_install": "No se ha podido iniciar el instalador (ver registro)",
        "m365.graph_error": "Microsoft Graph {code}: {message}",
        "azure.no_cli": "Azure CLI no encontrada: instálala y ejecuta az login, o usa una entidad de servicio.",
        "azure.cli_failed": "¿Hace falta az login? {message}",
        "azure.cli_timeout": "Azure CLI no ha respondido a tiempo",
        "azure.sp_incomplete": "Introduce el ID de inquilino, el ID de cliente y el secreto de cliente.",
        "azure.sign_in_failed": "Inicio de sesión rechazado: {message}",
        "azure.http_error": "Azure {code}: {message}",
        "azure.network": "Azure no disponible",
        "alert.adf_failed": "Data Factory: {pipeline} ha fallado",
        "tray.profile": "Perfil",
        "profile.work": "Trabajo",
        "profile.present": "Presentación",
        "profile.focus": "Concentración",
        "alert.profile": "Perfil: {name}",
        "google.need_client": "Primero introduce el ID de cliente y el secreto de cliente.",
        "google.cancelled": "Inicio de sesión no completado",
        "google.sign_in_failed": "Inicio de sesión rechazado: {message}",
        "google.expired": "Acceso caducado o revocado: vuelve a iniciar sesión.",
        "google.http_error": "Google Calendar {code}: {message}",
        "google.browser_ok": "Skerry está conectado a Google Calendar. Puedes cerrar esta ventana.",
        "google.browser_fail": "Inicio de sesión no completado. Puedes cerrar esta ventana y volver a intentarlo desde Skerry.",
        "sql.err_empty": "Escribe una consulta.",
        "sql.err_not_select": "Solo se permiten consultas que empiecen por SELECT o WITH.",
        "sql.err_multiple": "Solo una instrucción: quita los puntos y coma.",
        "sql.err_write": "La consulta contiene un comando que escribe o modifica algo: solo se permite leer.",
        "sql.err_driver": "Microsoft ODBC Driver 17 o 18 for SQL Server no está instalado.",
        "sql.err_pyodbc": "Falta la biblioteca pyodbc: ejecuta setup_dev.bat para instalarla.",
        "sql.err_server": "Introduce el servidor.",
        "sql.err_login": "Introduce el usuario y la contraseña.",
        "alert.sql_red": "{name}: {value}",
    },
    "de": {
        "outlook.not_running": "Das klassische Outlook ist nicht geöffnet: Die Besprechung erscheint, sobald du es öffnest",
        "outlook.no_com": "Outlook kann nicht gelesen werden: Die COM-Komponente fehlt",
        "outlook.failed": "Der Outlook-Kalender konnte nicht gelesen werden (siehe Protokoll)",
        "ics.bad_url": "Füge einen Kalenderlink mit https:// oder webcal:// ein",
        "ics.http_error": "Der Kalenderlink antwortete mit {code}: Prüfe, ob der Kalender noch veröffentlicht ist",
        "ics.bad_data": "Der Link liefert keinen Kalender (.ics)",
        "tray.expand": "Erweitern / verkleinern",
        "tray.settings": "Einstellungen…",
        "tray.pause": "Pause",
        "tray.reconnect": "Claude Code / Codex neu verbinden",
        "tray.autostart": "Mit Windows starten",
        "tray.check_updates": "Nach Updates suchen",
        "tray.install_update": "Update {version} installieren",
        "tray.logs": "Protokollordner öffnen",
        "tray.quit": "Beenden",
        "action.read": "Liest {file}",
        "action.write": "Schreibt {file}",
        "action.edit": "Bearbeitet {file}",
        "action.patch": "Wendet eine Änderung auf Dateien an",
        "action.search": "Sucht {pattern}",
        "action.fetch": "Öffnet {url}",
        "action.web_search": "Sucht im Web: {query}",
        "action.agent": "Agent: {description}",
        "action.tasks": "Aktualisiert die Aufgabenliste",
        "action.generic": "Aktion",
        "action.thinking": "Denkt nach…",
        "action.working": "Arbeitet…",
        "action.error": "Fehler: {action}",
        "action.waiting": "Wartet auf dich",
        "action.terminal_permission": "Bittet um Erlaubnis: antworte im Terminal",
        "action.done": "Erledigt",
        "action.failed": "Durch einen Fehler angehalten",
        "perm.denied": "Vom Benutzer in Skerry abgelehnt",
        "alert.session": "Sitzung",
        "alert.context": "{project}: Kontext bei {pct}%. Erwäge /compact oder eine neue Sitzung.",
        "limit.five_hour": "5-Stunden-Limit",
        "limit.seven_day": "Wochenlimit",
        "limit.spend": "Ausgabenlimit",
        "alert.limit": "{label} bei {pct}%",
        "alert.limit_reset": "{label} bei {pct}% · setzt sich in {h} Std. {m} Min. zurück",
        "alert.charging": "Wird geladen · {pct}%",
        "alert.on_battery": "Akkubetrieb · {pct}%",
        "alert.battery_low": "Akku bei {pct}%: Ladegerät anschließen",
        "alert.device_battery_low": "{name}: Akku bei {pct}%",
        "alert.timer_done": "{label}: Die Zeit ist um",
        "alert.pomodoro_break": "Pomodoro geschafft: Mach eine Pause!",
        "alert.pomodoro_back": "Pause vorbei: zurück an die Arbeit",
        "alert.meeting_soon": {"one": "{title} in {n} Min.", "other": "{title} in {n} Min."},
        "alert.reconnected": "Claude Code verbunden: offene Sitzungen neu starten",
        "alert.connect_failed": "Verbindung fehlgeschlagen (siehe Protokoll)",
        "alert.update_available": "Skerry {version} ist verfügbar",
        "alert.update_ready": "Update auf v{version} bereit: Es wird in einem ruhigen Moment installiert",
        "alert.update_dev": "In Entwicklung, mit git pull aktualisieren",
        "timer.focus": "Fokus",
        "timer.short_break": "Kurze Pause",
        "timer.long_break": "Lange Pause",
        "timer.minutes": "Timer {n} Min.",
        "meeting.untitled": "(ohne Titel)",
        "m365.need_client_id": "Gib zuerst die Anwendungs-ID (Client) ein.",
        "m365.need_msal": "Die Bibliothek msal fehlt: Führe setup_dev.bat aus, um sie zu installieren.",
        "m365.network": "Netzwerk nicht erreichbar",
        "m365.cancelled": "Anmeldung abgebrochen",
        "device.bluetooth": "Bluetooth-Gerät",
        "update.err_check": "Updates konnten nicht geprüft werden (siehe Protokoll)",
        "update.err_assets": "Die Version enthält kein Installationsprogramm oder keine SHA256SUMS.txt",
        "update.err_download": "Download fehlgeschlagen (siehe Protokoll)",
        "update.err_hash": "Download verworfen: Die SHA-256-Prüfsumme stimmt nicht überein",
        "update.err_install": "Das Installationsprogramm konnte nicht gestartet werden (siehe Protokoll)",
        "m365.graph_error": "Microsoft Graph {code}: {message}",
        "azure.no_cli": "Azure CLI nicht gefunden: Installiere sie und führe az login aus, oder verwende einen Dienstprinzipal.",
        "azure.cli_failed": "az login nötig? {message}",
        "azure.cli_timeout": "Die Azure CLI hat nicht rechtzeitig geantwortet",
        "azure.sp_incomplete": "Gib Mandanten-ID, Client-ID und geheimen Clientschlüssel ein.",
        "azure.sign_in_failed": "Anmeldung abgelehnt: {message}",
        "azure.http_error": "Azure {code}: {message}",
        "azure.network": "Azure nicht erreichbar",
        "alert.adf_failed": "Data Factory: {pipeline} fehlgeschlagen",
        "tray.profile": "Profil",
        "profile.work": "Arbeit",
        "profile.present": "Präsentation",
        "profile.focus": "Fokus",
        "alert.profile": "Profil: {name}",
        "google.need_client": "Gib zuerst die Client-ID und den Clientschlüssel ein.",
        "google.cancelled": "Anmeldung nicht abgeschlossen",
        "google.sign_in_failed": "Anmeldung abgelehnt: {message}",
        "google.expired": "Zugriff abgelaufen oder widerrufen: Melde dich erneut an.",
        "google.http_error": "Google Calendar {code}: {message}",
        "google.browser_ok": "Skerry ist mit Google Calendar verbunden. Du kannst dieses Fenster schließen.",
        "google.browser_fail": "Anmeldung nicht abgeschlossen. Du kannst dieses Fenster schließen und es in Skerry erneut versuchen.",
        "sql.err_empty": "Schreibe eine Abfrage.",
        "sql.err_not_select": "Nur Abfragen, die mit SELECT oder WITH beginnen, sind erlaubt.",
        "sql.err_multiple": "Nur eine Anweisung: Entferne die Semikolons.",
        "sql.err_write": "Die Abfrage enthält einen Befehl, der etwas schreibt oder ändert: Nur Lesen ist erlaubt.",
        "sql.err_driver": "Microsoft ODBC Driver 17 oder 18 for SQL Server ist nicht installiert.",
        "sql.err_pyodbc": "Die Bibliothek pyodbc fehlt: Führe setup_dev.bat aus, um sie zu installieren.",
        "sql.err_server": "Gib den Server ein.",
        "sql.err_login": "Gib Benutzer und Passwort ein.",
        "alert.sql_red": "{name}: {value}",
    },
    "fr": {
        "outlook.not_running": "Outlook classique n'est pas ouvert : la réunion apparaît quand vous l'ouvrez",
        "outlook.no_com": "Impossible de lire Outlook : le composant COM est absent",
        "outlook.failed": "Impossible de lire le calendrier Outlook (voir le journal)",
        "ics.bad_url": "Collez un lien de calendrier https:// ou webcal://",
        "ics.http_error": "Le lien du calendrier a répondu {code} : vérifiez que le calendrier est toujours publié",
        "ics.bad_data": "Le lien ne renvoie pas de calendrier (.ics)",
        "tray.expand": "Agrandir / réduire",
        "tray.settings": "Paramètres…",
        "tray.pause": "Pause",
        "tray.reconnect": "Reconnecter Claude Code / Codex",
        "tray.autostart": "Démarrer avec Windows",
        "tray.check_updates": "Rechercher des mises à jour",
        "tray.install_update": "Installer la mise à jour {version}",
        "tray.logs": "Ouvrir le dossier des journaux",
        "tray.quit": "Quitter",
        "action.read": "Lecture de {file}",
        "action.write": "Écriture de {file}",
        "action.edit": "Modification de {file}",
        "action.patch": "Application d'une modification aux fichiers",
        "action.search": "Recherche de {pattern}",
        "action.fetch": "Ouverture de {url}",
        "action.web_search": "Recherche sur le web : {query}",
        "action.agent": "Agent : {description}",
        "action.tasks": "Mise à jour de la liste des tâches",
        "action.generic": "Action",
        "action.thinking": "Réflexion…",
        "action.working": "Au travail…",
        "action.error": "Erreur : {action}",
        "action.waiting": "Vous attend",
        "action.terminal_permission": "Demande une autorisation : répondez dans le terminal",
        "action.done": "Terminé",
        "action.failed": "Arrêté par une erreur",
        "perm.denied": "Refusé par l'utilisateur dans Skerry",
        "alert.session": "Session",
        "alert.context": "{project} : contexte à {pct} %. Pensez à /compact ou à une nouvelle session.",
        "limit.five_hour": "Limite de 5 heures",
        "limit.seven_day": "Limite hebdomadaire",
        "limit.spend": "Limite de dépenses",
        "alert.limit": "{label} à {pct} %",
        "alert.limit_reset": "{label} à {pct} % · réinitialisation dans {h} h {m} min",
        "alert.charging": "En charge · {pct} %",
        "alert.on_battery": "Sur batterie · {pct} %",
        "alert.battery_low": "Batterie à {pct} % : branchez le chargeur",
        "alert.device_battery_low": "{name} : batterie à {pct} %",
        "alert.timer_done": "{label} : c'est l'heure",
        "alert.pomodoro_break": "Pomodoro terminé : faites une pause !",
        "alert.pomodoro_back": "Fin de la pause : au travail",
        "alert.meeting_soon": {"one": "{title} dans {n} min", "other": "{title} dans {n} min"},
        "alert.reconnected": "Claude Code connecté : redémarrez les sessions ouvertes",
        "alert.connect_failed": "La connexion a échoué (voir le journal)",
        "alert.update_available": "Skerry {version} est disponible",
        "alert.update_ready": "Mise à jour vers v{version} prête : elle s'installe à un moment calme",
        "alert.update_dev": "En développement, mettez à jour avec git pull",
        "timer.focus": "Concentration",
        "timer.short_break": "Pause courte",
        "timer.long_break": "Pause longue",
        "timer.minutes": "Minuteur {n} min",
        "meeting.untitled": "(sans titre)",
        "m365.need_client_id": "Saisissez d'abord l'ID d'application (client).",
        "m365.need_msal": "La bibliothèque msal est absente : exécutez setup_dev.bat pour l'installer.",
        "m365.network": "Réseau inaccessible",
        "m365.cancelled": "Connexion annulée",
        "device.bluetooth": "Appareil Bluetooth",
        "update.err_check": "Impossible de rechercher des mises à jour (voir le journal)",
        "update.err_assets": "La version n'a pas d'installateur ou de SHA256SUMS.txt",
        "update.err_download": "Le téléchargement a échoué (voir le journal)",
        "update.err_hash": "Téléchargement rejeté : la somme de contrôle SHA-256 ne correspond pas",
        "update.err_install": "Impossible de lancer l'installateur (voir le journal)",
        "m365.graph_error": "Microsoft Graph {code} : {message}",
        "azure.no_cli": "Azure CLI introuvable : installez-la et exécutez az login, ou utilisez un principal de service.",
        "azure.cli_failed": "az login nécessaire ? {message}",
        "azure.cli_timeout": "Azure CLI n'a pas répondu à temps",
        "azure.sp_incomplete": "Saisissez l'ID de locataire, l'ID client et le secret client.",
        "azure.sign_in_failed": "Connexion refusée : {message}",
        "azure.http_error": "Azure {code} : {message}",
        "azure.network": "Azure inaccessible",
        "alert.adf_failed": "Data Factory : {pipeline} a échoué",
        "tray.profile": "Profil",
        "profile.work": "Travail",
        "profile.present": "Présentation",
        "profile.focus": "Concentration",
        "alert.profile": "Profil : {name}",
        "google.need_client": "Saisissez d'abord l'ID client et le code secret du client.",
        "google.cancelled": "Connexion non terminée",
        "google.sign_in_failed": "Connexion refusée : {message}",
        "google.expired": "Accès expiré ou révoqué : reconnectez-vous.",
        "google.http_error": "Google Calendar {code} : {message}",
        "google.browser_ok": "Skerry est connecté à Google Calendar. Vous pouvez fermer cette fenêtre.",
        "google.browser_fail": "Connexion non terminée. Vous pouvez fermer cette fenêtre et réessayer depuis Skerry.",
        "sql.err_empty": "Écrivez une requête.",
        "sql.err_not_select": "Seules les requêtes qui commencent par SELECT ou WITH sont autorisées.",
        "sql.err_multiple": "Une seule instruction : supprimez les points-virgules.",
        "sql.err_write": "La requête contient une commande qui écrit ou modifie quelque chose : seule la lecture est autorisée.",
        "sql.err_driver": "Microsoft ODBC Driver 17 ou 18 for SQL Server n'est pas installé.",
        "sql.err_pyodbc": "La bibliothèque pyodbc est absente : exécutez setup_dev.bat pour l'installer.",
        "sql.err_server": "Saisissez le serveur.",
        "sql.err_login": "Saisissez l'utilisateur et le mot de passe.",
        "alert.sql_red": "{name} : {value}",
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
            return {0x10: "it", 0x09: "en", 0x0A: "es", 0x07: "de", 0x0C: "fr"}.get(primary, DEFAULT)
        except Exception:
            log.debug("Could not read the Windows UI language", exc_info=True)
            return DEFAULT
    code = (os.environ.get("LC_ALL") or os.environ.get("LC_MESSAGES") or os.environ.get("LANG") or "")[:2].lower()
    return code if code in LANGUAGES else DEFAULT


def resolve(preference):
    """'auto' (or anything unknown) -> system language; a supported code -> itself."""
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
    if lang == "fr":
        return "one" if n in (0, 1) else "other"
    return "one" if n == 1 else "other"


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
