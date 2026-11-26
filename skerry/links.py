"""Useful links of the island: a name and an http(s) URL, edited in Settings > Layout and opened in the default
browser. Pure: sanitize() is used on save (Api.links_save), on settings import and again before opening."""
import re
from urllib.parse import urlparse

MAX = 20
SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:(?!\d)")   # "mailto:", "javascript:" but not "host:8080"


def valid_url(url):
    try:
        u = urlparse(url)
        return u.scheme in ("http", "https") and bool(u.hostname) and (u.port or 0) >= 0
    except ValueError:
        return False


def sanitize(items):
    """Keep only {name, url} entries with an http(s) URL ("example.com" becomes https://example.com)."""
    out = []
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict):
            continue
        url = str(it.get("url") or "").strip()[:2000]
        if url and not SCHEME.match(url):
            url = "https://" + url
        if not valid_url(url):
            continue
        name = str(it.get("name") or "").strip()[:60] or urlparse(url).hostname
        out.append({"name": name, "url": url})
    return out[:MAX]
