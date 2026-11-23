## What and why

<!-- What does this change and which problem does it solve? Link the issue: "Fixes #123". -->

## How it was tested

<!-- Windows version, what you clicked/ran, screenshots or a short clip for UI changes. -->

## Checklist

- [ ] `python -m ruff check .` and `python -m pytest` pass
- [ ] `py_compile` on all `.py` files and `node --check` on `ui/*.js` (and the inline script of `ui/settings.html` if touched)
- [ ] Launched with `.\run_dev.bat` and checked `logs\skerry.log` for errors/tracebacks
- [ ] Code, comments and docs in English
- [ ] No real company, server, person or personal data in code, tests or screenshots
- [ ] No secrets in `settings.json`: secrets go through `skerry/secrets.py`
- [ ] Permission decisions still go only through `js_api`, never HTTP
- [ ] `CHANGELOG.md` updated for user-visible changes
