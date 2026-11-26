# Changelog

## Unreleased

## 1.0.2 — 2026-11-26

- **Useful links**: a new island section with your favourite sites as tiles, opened in the default browser with one
  click. Edit them in *Settings → Layout → Useful links → Options* (web addresses only, up to 20).
- **Upper / lower case**: a new island section to convert text to UPPER, lower, Sentence, Each Word, aLtErNaTe and
  iNVERSE case, with a character/word count and a copy button.
- Cleaner look: line icons instead of emoji in section headers, rounder media controls, link tiles, and the Botteca
  logo next to the version in the island footer and in the guided setup.

## 1.0.1

- **Claude Code limits** (5-hour session and week) now have their own section, separate from *Claude usage*
  (tokens and chart): each can be moved or hidden in *Settings → Layout*. Percentages are rounded like the official
  app (they were truncated, so they often showed 1% less).
- Claude Code plan approval (*ExitPlanMode*) and multiple-choice questions (*AskUserQuestion*) are no longer offered
  as Allow/Deny in the island, where an answer did not close Claude Code's own dialog: the island shows that the
  agent is waiting for you in the terminal.
- **OpenCode** (experimental, opt-in in *Settings → Agents*): Skerry installs a small dependency-free plugin in
  `~/.config/opencode/plugins/skerry.js` that shows OpenCode's activity and lets you answer its permission requests
  from the island (replied through OpenCode's own local server).

## 1.0.0

First public release.

**Coding agents**
- Live activity of **Claude Code** and **Codex** (current action, tasks, done or error), plus **Gemini CLI** and
  **GitHub Copilot CLI** (opt-in). Several sessions at once, context and 5-hour/weekly limit alerts, terminal focus.
- **Permission requests** answered from the island: Allow, Always, Deny, back to the terminal, or "allow similar
  requests in this project for N minutes" (never for commands that delete, overwrite or reach outside the project).
- Agent **history** of the last 30 days by project, with CSV export (local files only).
- Hooks never block an agent: when Skerry is not running they exit silently.

**The island**
- Always-on-top pill on any screen edge and monitor, with dragging, a vertical tab on the sides, multi-monitor
  support (primary, a chosen screen or the one with the mouse) and **anti-aliased corners**.
- Now Playing with cover colour, seek and volume; microphone/camera in use; laptop and **Bluetooth** battery;
  timer and Pomodoro; file shelf; local **Claude usage** (5 hours / 7 days).
- **Customisable layout**: order and visibility of every section, what may take the closed pill, minimal mode,
  profiles (work, presentation, focus) with an automatic switch during screen sharing or meetings.
- At rest the pill shows Claude usage, the name, a clock or the icon only. Optional animated companion (two eyes).
- Hidden during screen sharing (on by default) and with fullscreen apps; not shown in the taskbar.

**Connections** (all read-only, secrets encrypted with Windows DPAPI)
- Next meeting with a *Join* button, with no setup from **Outlook on this PC** (classic Outlook) or from a
  **calendar link** (ICS, Outlook on the web or Google; encrypted like a password), or with a sign-in from
  **Microsoft 365** or **Google Calendar**.
- **Azure Data Factory** pipeline runs, with an alert when one fails.
- **SQL Server / Azure SQL** query widgets with green, amber and red thresholds.

**Everything else**
- Interface in **English, Italian, Spanish, German and French** (follows Windows, switchable live). Font: Inter.
- Settings window with sidebar, light and dark themes, accent colour, global shortcut, guided setup on first launch,
  settings export/import (passwords and tokens never included), *Copy diagnostics* without personal data.
- **Automatic updates** from GitHub releases: the installer's SHA-256 is verified against `SHA256SUMS.txt` before a
  silent install at a quiet moment. Modes: automatic, notify only, off.
- Security: the local server (127.0.0.1) refuses browsers, DNS rebinding and oversized requests; permission
  decisions never go through HTTP; the update source cannot be changed from the UI.
- Per-user installer (no admin rights) in five languages; start with Windows; automatic restart after a crash.
