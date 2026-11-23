"""Updates from GitHub releases (installer .exe asset)."""
import json
import logging
import os
import subprocess
import tempfile
import urllib.request

from . import VERSION

log = logging.getLogger("skerry")


def _ver(tag):
    parts = []
    for p in str(tag).lstrip("vV").split("."):
        digits = "".join(ch for ch in p if ch.isdigit())
        parts.append(int(digits or 0))
    return tuple(parts + [0] * (3 - len(parts)))


def check(url, token=None):
    """Return {'version','url','notes'} if a newer version exists, else None."""
    if not url:
        return None
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "Skerry"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=10) as r:
            rel = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        log.info("Controllo aggiornamenti non riuscito: %s", e)
        return None
    tag = rel.get("tag_name", "")
    if _ver(tag) <= _ver(VERSION):
        return None
    asset = next((a for a in rel.get("assets", []) if a.get("name", "").lower().endswith(".exe")), None)
    if not asset:
        return None
    return {"version": tag.lstrip("vV"), "url": asset["browser_download_url"], "notes": rel.get("body", "")[:500]}


def download_and_run(info):
    path = os.path.join(tempfile.gettempdir(), f"Skerry-Setup-{info['version']}.exe")
    log.info("Scarico aggiornamento %s", info["version"])
    urllib.request.urlretrieve(info["url"], path)
    subprocess.Popen([path, "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART"], close_fds=True)
