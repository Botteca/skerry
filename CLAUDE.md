# CLAUDE.md

## What this is

**Skerry** is a Windows 10/11 always-on-top "dynamic island": a small pill snapped to a
screen edge that shows live Claude Code and Codex activity (current action, tasks, done/error), permission
requests to approve or deny, Now Playing media and volume, mic/camera in use, laptop and Bluetooth battery, a
timer/Pomodoro, a file shelf, local token usage, and the next Microsoft 365 meeting.

Stack: Python 3.11+ (dev venv runs 3.13), pywebview on WinForms/WebView2, a local Flask server on
`127.0.0.1:47800`, UI in plain HTML/JS/CSS (`ui/`). Packaged with PyInstaller and Inno Setup.

## Module map

| Path | Role |
|---|---|
| `app.py` | Entry point. `supervise()` restarts the child on crash (max 5 in 10 min; exit 0/3 = stop). `SkerryApp` wires everything, creates the pywebview window, runs the guard loop (fullscreen hide, keep-on-top) and update loop. |
| `cli.py` | `skerry-cli`: `hook <claude\|codex>` (stdin JSON → HTTP), `statusline` (forwards to Skerry, then runs the chained status line), `connect`/`disconnect`. |
| `skerry/server.py` | Flask, 127.0.0.1 only: `POST /hook/<event>`, `POST /statusline`, `POST /ui/show`, `GET /health`. |
| `skerry/store.py` | Thread-safe state: sessions, pending permissions (blocking `threading.Event`), tasks, alerts, rate limits. `snapshot()` is what the UI sees. |
| `skerry/api.py` | `js_api` exposed to the UI as `window.pywebview.api.*`. `SETTABLE` whitelists settings the UI may write. |
| `skerry/integrations.py` | Writes/removes our hooks in `~/.claude/settings.json` and `~/.codex/hooks.json` (backup first). Bump `HOOKS_VERSION` when the hook list changes. |
| `skerry/win32.py` | ctypes: pill window (region, DWM, animation, drag/snap), fullscreen detection, focus, clipboard (CF_HDROP), single-instance mutex, global hotkey. |
| `skerry/settings.py` | `%APPDATA%\Skerry\settings.json`, `DEFAULTS` merged on load, dotted keys, change listeners. |
| `skerry/secrets.py` | DPAPI-encrypted secrets in `%APPDATA%\Skerry\secrets\*.bin`. |
| `skerry/connectors/` | Optional external services. `m365.py`: MSAL + Graph `calendarView`, read-only; `pick_meeting()` is pure. |
| `skerry/media.py`, `audio.py` | Now Playing via WinRT GSMTC; master volume via pycaw. |
| `skerry/system.py` | Mic/camera via ConsentStore registry, battery, Bluetooth battery via SetupAPI. |
| `skerry/usage.py` | Token usage parsed incrementally from `~/.claude/projects/**/*.jsonl` (no network). |
| `skerry/timer.py`, `shelf.py`, `sounds.py`, `tray.py`, `autostart.py`, `updater.py`, `terminal.py`, `paths.py`, `log.py` | Timer/Pomodoro, shelf, beeps, tray menu, HKCU Run key, GitHub release updater, terminal HWND lookup, paths, rotating log. |
| `ui/index.html`, `skerry.js`, `skerry.css` | The pill. Polls `get_state()` every 250 ms, picks a view, calls `resize(w,h,r)`. |
| `ui/settings.html` | Settings window (inline script, same `js_api`). |
| `build/` | `skerry.spec` (two exes: `Skerry.exe` windowed, `skerry-cli.exe` console), `installer.iss`, `version_info.txt`. |
| `demo.py` | Simulates Claude Code and Codex against a running Skerry (includes a permission request). |

## Data flow

```
Claude Code ─ http hooks ───────────────────────────▶ POST /hook/<Event>?agent=claude ┐
Claude Code ─ command hook SessionStart (skerry-cli) ▶ (adds terminal_hwnd)           │
Claude Code ─ statusLine command (skerry-cli) ──────▶ POST /statusline                ├▶ Store
Codex ─────── command hooks (skerry-cli hook codex) ▶ POST /hook/<Event>?agent=codex  ┘    │
Windows (media, audio, registry, power, Bluetooth), M365, local usage ─▶ modules ──────────┤
                                                                                          ▼
              UI (skerry.js) ◀── window.pywebview.api.get_state() every 250 ms ── Api (js_api)
              UI ──▶ api.decide(pid, allow|always|deny|terminal) ──▶ Store.decide() ──▶ Event.set()
```

`PermissionRequest` blocks the HTTP request inside `Store.request_permission()` until the UI decides, the timeout
(`permission_wait`, default 300 s) expires, or the session moves on (`PostToolUse`, `Stop`, `UserPromptSubmit`,
`SessionEnd` cancel it). Timeout/cancel/"terminal" return `{}` so the agent falls back to its own prompt.
If Skerry is not running, `skerry-cli` exits 0 silently so agents are never blocked.

## Commands (Windows, PowerShell, from the repo root)

The dev venv lives **outside** the repo: `%LOCALAPPDATA%\venvs\skerry`.

```powershell
.\setup_dev.bat                                   # create venv + install requirements (does not upgrade pip)
.\run_dev.bat                                     # run without supervisor; log in .\logs\skerry.log
$env:SKERRY_DEBUG=1; .\run_dev.bat                # same, with WebView2 devtools
& "$env:LOCALAPPDATA\venvs\skerry\Scripts\python.exe" demo.py   # fake agent traffic (Skerry must be running)
.\build.bat                                       # PyInstaller → dist\Skerry\, Inno Setup → dist\Skerry-Setup-x.y.z.exe

# Checks (run all before calling work done)
$py = "$env:LOCALAPPDATA\venvs\skerry\Scripts\python.exe"
Get-ChildItem -Recurse -Filter *.py | Where-Object FullName -notmatch '\\(dist|build\\work)\\' | ForEach-Object { & $py -m py_compile $_.FullName }
Get-ChildItem ui\*.js | ForEach-Object { node --check $_.FullName }
# ui/settings.html has an inline <script>: extract it to a temp .js and node --check it when you touch it.
```

Automated tests and lint (`& $py -m pip install -r requirements-dev.txt` once): `& $py -m pytest` and
`& $py -m ruff check .` (config in `pyproject.toml`). `tests/conftest.py` redirects APPDATA/LOCALAPPDATA/
CLAUDE_CONFIG_DIR to a temp dir and blocks outbound network and `winreg`: keep tests that way.
CI (`.github/workflows/ci.yml`, windows-latest) runs ruff, py_compile, `node --check` and pytest.

Runtime files: settings `%APPDATA%\Skerry\settings.json`, shelf `%APPDATA%\Skerry\shelf.json`, secrets
`%APPDATA%\Skerry\secrets\`, logs `%LOCALAPPDATA%\Skerry\logs\` (plus `.\logs\` in dev), agent config backups
`%LOCALAPPDATA%\Skerry\backup\`. Version lives in three places: `skerry/__init__.py`, `build/installer.iss`,
`build/version_info.txt`.

## Known delicate points — do not regress

- **Window shape.** The pill is `create_window(..., shadow=False, min_size=(20, 20))`, then on `shown`
  `_release_min_size()` sets the native WinForms `MinimumSize` to 0 (otherwise it stays ~200x100 × DPI).
  The shape comes only from `SetWindowRgn(CreateRoundRectRgn(...))`, set **before** `SetWindowPos` on every frame.
  Animation (`SkerryWindow.animate_to`) is time-based (ease-out, 300 ms) and paced by `DwmFlush` with 1 ms timer
  resolution. `dwm_flat()` turns off Mica backdrop, NC rendering, rounded corners and border, and is re-applied
  periodically. **Never re-enable pywebview's shadow or Mica**: they cause the grey border/rectangle.
- **Permission decisions go only through `js_api`** (`Api.decide`), never through HTTP. Do not add any HTTP
  endpoint that resolves, lists or alters pending permissions. The server only receives requests.
- **No passwords or tokens in `settings.json`.** Secrets go through `skerry/secrets.py` (DPAPI). Connectors store
  only non-secret config (client id, tenant) in settings.
- **Screen-capture exclusion.** When `hide_from_capture` is on, the pill (and the settings window) must be
  excluded from screen capture with `SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)`.
  Implemented in `SkerryWindow.capture_hidden()` (`skerry/win32.py`): falls back to `WDA_MONITOR` on older builds,
  is called from `setup()`, `keep_on_top()` and, for the settings window, from the guard loop in `app.py`.
- **The venv is outside the project folder** because the endpoint protection (EDR) corrupts pip operations inside the repo. Never
  create `.venv` in the repo and don't upgrade pip in `setup_dev.bat`.
- Internal window title is `"Skerry overlay"` on purpose (must differ from an Explorer folder named "Skerry";
  `FindWindowW` uses it). The settings window is found by `SETTINGS_TITLE`; changing either title breaks lookups.
- `integrations._is_ours()` recognises our hooks by URL `http://127.0.0.1:<port>/hook/` or by `CLI_MARKERS` in the
  command (`skerry-cli`, the pre-rename `island-cli`, `cli.py`). Keep that true when changing hook commands, or
  uninstall will leave stale hooks.
- **Pre-rename names** appear only where migration needs them: `paths.LEGACY_NAMES` (data folders and Run values,
  copied once by `paths._migrate` while `%APPDATA%\Skerry` / `%LOCALAPPDATA%\Skerry` do not exist),
  `integrations.CLI_MARKERS`, the legacy uninstall key and Run values in `build/installer.iss`, and
  `tests/test_rename.py`. Don't add new ones elsewhere.
- Hook timeouts: `PermissionRequest` uses `permission_wait + 30` in agent config and `+ 20` in the CLI. Keep the
  agent-side timeout larger than Skerry's wait.
- UI escapes every dynamic string with `esc()` before `innerHTML`. Keep it that way.
- `join_meeting` opens only `https://` URLs. Keep that check.

## Working rules

- **Language.** Code, comments, commit messages and docs in **English**. In any file you touch, translate existing
  Italian comments/docstrings to English. (User-facing UI strings are currently Italian; change them only when
  asked.) Replies to the user in **Italian**.
- **Definition of done.** Before saying something is finished: `py_compile` on all `.py`, `node --check` on
  `ui/*.js` (and the settings inline script if touched), automated tests when they exist, and a real launch with
  `.\run_dev.bat` while checking `logs\skerry.log` for errors/tracebacks.
- **Never commit:** venvs, `logs/`, `build/work/`, `dist/`, `settings.json`, anything under `secrets/`, `.env` files,
  `.claude/settings.local.json`.
- **No real companies, servers, tables or people** anywhere in the repo, examples and demo data included. Use
  invented names (e.g. `Contoso`-style placeholders, `C:/rep/ExampleApp`, `example.invalid`).
- **No push and no release** (tags, GitHub releases, publishing installers) unless the user asks.
- Keep changes small and in the existing style: stdlib + ctypes first, no new dependency for a few lines,
  every background loop catches and logs its own exceptions.
