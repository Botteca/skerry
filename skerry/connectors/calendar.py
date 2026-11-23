"""Pure helpers shared by the calendar sources that are not an online API (Outlook on this PC, calendar link).

Events are normalised to: {"id", "title", "start", "end" (timestamps), "location", "text" (body/description),
"cancelled", "all_day", "declined", "free"}; `pick()` returns the meeting the island shows, in the same shape as
the Microsoft 365 and Google connectors.
"""
import re
from urllib.parse import unquote

# links that open a video meeting, most specific first
JOIN_PATTERNS = (
    ("Teams", r"https://teams\.microsoft\.com/l/meetup-join/[^\s\"'<>]+"),
    ("Teams", r"https://teams\.live\.com/meet/[^\s\"'<>]+"),
    ("Meet", r"https://meet\.google\.com/[a-z]{3}-[a-z]{4}-[a-z]{3}[^\s\"'<>]*"),
    ("Zoom", r"https://[\w.-]*zoom\.us/[jw]/[^\s\"'<>]+"),
    ("Webex", r"https://[\w.-]*webex\.com/[^\s\"'<>]+"),
)


def join_link(*texts):
    """(provider, https url) of the first video-meeting link found in the texts, or ("", "")."""
    blob = "\n".join(t for t in texts if isinstance(t, str))
    for text in (blob, unquote(blob)):              # the second pass finds links wrapped by Safe Links
        for provider, pattern in JOIN_PATTERNS:
            m = re.search(pattern, text)
            if m:
                return provider, m.group(0).rstrip(".,;)>]")
    return "", ""


def pick(events, now, prefix):
    """Event in progress or next (cancelled, all-day, declined and finished events skipped)."""
    best = None
    for e in events or []:
        if e.get("cancelled") or e.get("all_day") or e.get("declined"):
            continue
        s, en = e.get("start"), e.get("end")
        if s is None or en is None or en <= now or en <= s:
            continue
        if best is None or s < best["start"]:
            provider, url = join_link(e.get("location"), e.get("text"), e.get("url"))
            loc = (e.get("location") or "").strip()
            best = {"id": f"{prefix}:{e.get('id') or ''}", "title": (e.get("title") or "").strip(), "start": s,
                    "end": en, "join_url": url, "provider": provider,
                    "location": "" if url or loc.startswith("http") else loc[:120],
                    "show_as": "free" if e.get("free") else "busy"}
    if best:
        best["in_progress"] = best["start"] <= now < best["end"]
    return best
