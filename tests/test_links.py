"""Useful links: only http(s) URLs survive saving and settings import, and they are never writable through set_setting."""
from skerry import api, backup, links, settings


def test_sanitize_keeps_only_web_links():
    out = links.sanitize([
        {"name": "Docs", "url": "https://docs.example.invalid/start"},
        {"name": "", "url": "example.invalid"},                       # scheme added, name from the host
        {"name": "Script", "url": "javascript:alert(1)"},
        {"name": "File", "url": "file:///C:/Windows/notepad.exe"},
        {"name": "Run", "url": "ms-settings:privacy"},
        {"name": "Broken", "url": "http://["},
        "not a dict", {"name": "No url"},
    ])
    assert out == [{"name": "Docs", "url": "https://docs.example.invalid/start"},
                   {"name": "example.invalid", "url": "https://example.invalid"}]
    assert links.sanitize("nope") == []
    assert len(links.sanitize([{"url": f"https://e{i}.example.invalid"} for i in range(50)])) == links.MAX


def test_links_are_not_settable_and_import_is_sanitized(tmp_path):
    assert "links" not in api.SETTABLE and settings.DEFAULTS["links"] == []
    s = settings.Settings(str(tmp_path / "settings.json"))
    backup.import_data(s, {"format": backup.FORMAT, "settings": {"links": [
        {"name": "Ok", "url": "https://ok.example.invalid"}, {"name": "Bad", "url": "file:///C:/x.exe"}]}})
    assert s.get("links") == [{"name": "Ok", "url": "https://ok.example.invalid"}]
