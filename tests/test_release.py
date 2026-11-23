"""Release tooling: one version source, tag check, CHANGELOG notes, SHA256SUMS, no hard-coded versions elsewhere."""
import hashlib
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import release  # noqa: E402

from skerry import VERSION  # noqa: E402


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def test_version_is_read_from_the_package():
    assert release.version() == VERSION
    assert re.fullmatch(r"\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?", VERSION)


def test_no_hard_coded_version_elsewhere():
    """The installer, the version resource and the spec take the version from skerry/__init__.py."""
    iss = read("build", "installer.iss")
    assert "#define AppVersion" not in iss and "#ifndef AppVersion" in iss
    tpl = read("build", "version_info.txt")
    assert "{version}" in tpl and "{numbers}" in tpl
    assert not re.search(r"\d+\.\d+\.\d+", tpl)
    assert "release.version(" in read("build", "skerry.spec")
    assert "tools\\release.py version" in read("build.bat")
    assert "/DAppVersion=" in read(".github", "workflows", "release.yml")


def test_installer_supports_silent_updates():
    iss = read("build", "installer.iss")
    for directive in ("PrivilegesRequired=lowest", "AppMutex=SkerrySingleInstance", "CloseApplications=force",
                      "RestartApplications=yes"):
        assert directive in iss
    assert 'Check: WizardSilent' in iss                     # the app is started again after a silent update
    assert 'name="Local\\\\SkerrySingleInstance"' in read("skerry", "win32.py")


def test_check_tag():
    assert release.check_tag(f"v{VERSION}") == VERSION
    assert release.check_tag(f"refs/tags/v{VERSION}") == VERSION
    for bad in (VERSION, "v0.0.1", f"v{VERSION}.1"):
        with pytest.raises(SystemExit):
            release.check_tag(bad)


CHANGELOG = """# Changelog

## Unreleased
- Not yet.

## 1.2.0 — 2026-12-01
- **New** thing.
- Fix: other thing.

## 1.1.0
- Old.
"""


def test_notes(tmp_path):
    p = tmp_path / "CHANGELOG.md"
    p.write_text(CHANGELOG, encoding="utf-8")
    assert release.notes("1.2.0", str(p)) == "- **New** thing.\n- Fix: other thing."
    assert release.notes("1.1.0", str(p)) == "- Old."
    with pytest.raises(SystemExit):
        release.notes("9.9.9", str(p))


def test_real_changelog_has_the_current_version():
    """A release can only be tagged when CHANGELOG.md documents VERSION (or it is still the first one)."""
    text = read("CHANGELOG.md")
    assert re.search(rf"^## \[?v?{re.escape(VERSION)}\]?([ \t]|$)", text, re.MULTILINE)


def test_sums_and_cli(tmp_path):
    f = tmp_path / "Skerry-Setup-1.2.0.exe"
    f.write_bytes(b"installer bytes")
    expected = f"{hashlib.sha256(b'installer bytes').hexdigest()}  Skerry-Setup-1.2.0.exe\n"
    assert release.sums([str(f)]) == expected
    out = tmp_path / "SHA256SUMS.txt"
    release.main(["sums", str(f), "--out", str(out)])
    assert out.read_text(encoding="utf-8") == expected

    from skerry.updater import parse_sums
    assert parse_sums(expected) == {"Skerry-Setup-1.2.0.exe": hashlib.sha256(b"installer bytes").hexdigest()}
