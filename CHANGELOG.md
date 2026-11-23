# Changelog

## Unreleased
- **Multiple screens**: choose the primary screen, a specific one (remembered by a stable id, so docking and
  renumbering don't lose it) or the screen with the mouse pointer. The island follows screens being connected,
  disconnected or docked, sizes itself with the target screen's DPI, comes back if it ends up off-screen, and logs
  every display change.
- **Copy diagnostics** (Settings → About and logs): version, Windows, DPI, screens, enabled modules, connector
  and agent status and the last 80 log lines go to the clipboard, with user paths, Bluetooth device names and
  email addresses hidden.
- **Guided setup on first launch**: three short steps in the island (edge and screen, connect Claude Code and
  Codex, shortcut tips). It can be skipped and shown again from *Settings → General*. Existing installs don't see it.
- **No more "hook failed: ECONNREFUSED" in Claude Code when Skerry is not running.** Claude Code hooks are now
  `skerry-cli` command hooks that exit silently in that case (hooks v4, rewritten automatically). They run in the
  background, except the permission request, so they add no latency.
- **Automatic updates.** Skerry checks GitHub releases at startup and every 6 hours (ETag), ignores pre-releases and,
  in the default *Automatic* mode, downloads the installer, verifies its SHA-256 against `SHA256SUMS.txt` and installs
  it silently at a quiet moment (or with *Update now*), then restarts. Modes: Automatic / Notify only / Off
  (the old "check automatically" switch is migrated). *Settings → Updates* shows status, last check and release notes.
- Releases are built and published by GitHub Actions on a `v*` tag; the version lives only in `skerry/__init__.py`.
- Installer in English and Italian, detects a running Skerry (AppMutex) and supports silent updates.
- **English and Italian interface.** The language follows Windows by default; *Settings → General → Language*
  (Automatic / English / Italiano) switches the pill, the settings window, alerts and the tray menu immediately,
  without a restart. Dates, times and numbers follow the language. Log messages are now always in English.
- Screenshots regenerated in English (`docs/img/`) and Italian (`docs/img/it/`) by `tools/screenshots.py`.
- **Renamed to Skerry**: `Skerry.exe` / `skerry-cli.exe`, new installer identity, data in `%APPDATA%\Skerry` and
  `%LOCALAPPDATA%\Skerry`. On first run the data of the previous version is copied over once; old autostart entries,
  old installs and old agent hooks are removed and replaced automatically (hooks v3).
- New icon and logo (`assets/brand/`), explicit AppUserModelID, icon on the settings window.
- Updates now come from `github.com/fabrisimo/skerry`.
- **Connections** page in settings and the first connector: **Microsoft 365** — next Outlook/Teams meeting with a
  *Join* button and an alert before it starts (Microsoft Graph, read-only, browser sign-in, DPAPI-encrypted tokens).
- Settings redesigned with a sidebar.
- Hide the pill while the screen is being shared (optional, on by default).
- MIT license.
- Open-source project files: README in English and Italian, CONTRIBUTING, SECURITY, Code of Conduct, issue and pull
  request templates, pytest suite and GitHub Actions CI (ruff, py_compile, pytest on Windows).
- Animations synced to the display refresh; entry animations only when the view changes.
- Bluetooth: real device name from the Windows registry, icon per device type, battery bar.
- "Claude usage" section: tokens of the last 5 hours / 7 days read from local files.
- Fixed the grey (Mica) background around the pill.

## 1.0.0
- Pill snaps to any edge and monitor, with dragging and a vertical tab on the sides
- Start with Windows, single instance, supervisor with automatic restart, tray icon
- Settings page, light/dark themes, accent colour, global hotkey
- Hides with fullscreen apps
- Claude Code: multiple sessions, tasks, "Always allow", context and limit alerts, terminal focus
- Codex: actions, permissions and completion through hooks
- Media: colour from the cover, seek, volume
- Microphone/camera in use, battery, Bluetooth headphones
- Timer and Pomodoro, file shelf
- Rotating logs, updates from GitHub releases, Inno Setup installer
