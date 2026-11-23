"""Local store for secrets and tokens (connector token caches).

On Windows the data is encrypted with DPAPI (CryptProtectData): only the same user on this PC can read it.
Elsewhere (development and tests on Linux/macOS) secrets live in memory only, never on disk.
No passwords in settings.json.
"""
import ctypes
import logging
import os
import sys
from ctypes import wintypes

from . import paths

log = logging.getLogger("skerry")
IS_WIN = sys.platform == "win32"
_MEMORY = {}                      # non-Windows only: nothing is written to disk without DPAPI


def _dir():
    d = os.path.join(paths.config_dir(), "secrets")
    os.makedirs(d, exist_ok=True)
    return d


def _file(name):
    safe = "".join(c for c in name if c.isalnum() or c in "-_.")
    return os.path.join(_dir(), safe + ".bin")


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(data):
    buf = ctypes.create_string_buffer(data, len(data))
    return _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf


def _dpapi(data, protect):
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32")
    inb, keep = _blob(data)
    out = _Blob()
    fn = crypt.CryptProtectData if protect else crypt.CryptUnprotectData
    if not fn(ctypes.byref(inb), None, None, None, None, 0, ctypes.byref(out)):
        raise OSError(ctypes.get_last_error(), "DPAPI call failed")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel.LocalFree(out.pbData)
        del keep


def save(name, text):
    if not IS_WIN:
        _MEMORY[name] = text
        return
    encrypted = _dpapi(text.encode("utf-8"), True)
    path = _file(name)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(encrypted)
    os.replace(tmp, path)


def load(name, default=None):
    if not IS_WIN:
        return _MEMORY.get(name, default)
    try:
        with open(_file(name), "rb") as f:
            data = f.read()
        return _dpapi(data, False).decode("utf-8")
    except FileNotFoundError:
        return default
    except Exception:
        log.warning("A stored secret could not be decrypted (ignored)")
        return default


def delete(name):
    if not IS_WIN:
        _MEMORY.pop(name, None)
        return
    try:
        os.remove(_file(name))
    except FileNotFoundError:
        pass
