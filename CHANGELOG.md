# Changelog

## Unreleased
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
