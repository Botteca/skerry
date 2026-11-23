"""secrets: DPAPI-encrypted store (Windows) under %APPDATA%\\Skerry\\secrets (redirected to a temp dir)."""
import os
import sys

import pytest

from skerry import paths, secrets

# DPAPI files exist only on Windows (elsewhere secrets stay in memory); CI runs on Windows
pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="DPAPI is Windows only")


def secrets_dir():
    return os.path.join(paths.config_dir(), "secrets")


def test_roundtrip():
    value = '{"AccessToken": {"k": "v"}, "unicode": "città ✓"}'
    secrets.save("m365-token-cache", value)
    assert secrets.load("m365-token-cache") == value
    assert os.listdir(secrets_dir()) == ["m365-token-cache.bin"]


def test_overwrite():
    secrets.save("a", "first")
    secrets.save("a", "second")
    assert secrets.load("a") == "second"
    assert os.listdir(secrets_dir()) == ["a.bin"]  # atomic replace, no leftover .tmp


def test_missing_returns_default():
    assert secrets.load("nothing") is None
    assert secrets.load("nothing", "fallback") == "fallback"


def test_delete():
    secrets.save("gone", "x")
    secrets.delete("gone")
    secrets.delete("gone")  # deleting twice is fine
    assert secrets.load("gone") is None


def test_unreadable_returns_default():
    secrets.save("bad", "x")
    with open(os.path.join(secrets_dir(), "bad.bin"), "wb") as f:
        f.write(b"\x00garbage that is neither DPAPI nor base64\xff")
    assert secrets.load("bad", "fallback") == "fallback"


def test_name_cannot_escape_the_folder():
    secrets.save("../../evil\\name", "x")
    assert os.listdir(secrets_dir()) == ["....evilname.bin"]
    assert secrets.load("../../evil\\name") == "x"


def test_file_is_encrypted_on_windows():
    secrets.save("plain-check", "very-recognisable-value")
    with open(os.path.join(secrets_dir(), "plain-check.bin"), "rb") as f:
        raw = f.read()
    assert b"very-recognisable-value" not in raw
    assert "very-recognisable-value".encode("utf-16-le") not in raw
    assert b"dmVyeS1yZWNvZ25pc2FibGUtdmFsdWU" not in raw      # nor its base64
