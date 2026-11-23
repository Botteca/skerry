"""Settings > History: local records + Claude Code session files, 30-day window, CSV export."""
import csv
import io
import json
import time

from skerry import history

NOW = time.time()


def iso(ts):
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(ts))


def claude_line(sid, ts, msg_id, inp, out, model="claude-sonnet-5-5"):
    return json.dumps({"sessionId": sid, "cwd": "C:\\rep\\ExampleApp", "timestamp": iso(ts), "requestId": "r" + msg_id,
                       "message": {"id": msg_id, "model": model,
                                   "usage": {"input_tokens": inp, "output_tokens": out,
                                             "cache_creation_input_tokens": 10, "cache_read_input_tokens": 1000}}})


def test_sessions_merge_own_records_and_claude_files(tmp_path, monkeypatch):
    monkeypatch.setattr(history.time, "time", lambda: NOW - 3600)
    history.record("claude", "c1", "ExampleApp")
    history.record("codex", "x1", "OtherApp")
    monkeypatch.setattr(history.time, "time", lambda: NOW - 600)
    history.record("claude", "c1", "ExampleApp", cost=0.42)
    history.record("codex", "x1", "OtherApp")

    proj = tmp_path / "claude" / "projects" / "C--rep-ExampleApp"
    proj.mkdir(parents=True)
    lines = [claude_line("c1", NOW - 3000, "m1", 100, 50), claude_line("c1", NOW - 2000, "m2", 200, 70),
             claude_line("c1", NOW - 2000, "m2", 200, 70)]                         # duplicate response counted once
    (proj / "c1.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")

    rows = {r["sid"]: r for r in history.sessions(now=NOW, claude_root=str(tmp_path / "claude" / "projects"))}
    c, x = rows["c1"], rows["x1"]
    assert (c["agent"], c["project"], c["model"], c["cost"]) == ("claude", "ExampleApp", "claude-sonnet-5-5", 0.42)
    assert (c["input"], c["output"], c["cache_write"], c["cache_read"]) == (300, 120, 20, 2000)
    assert round(c["duration"]) == 3000                    # first record (own file) to last one
    assert (x["agent"], x["project"], x["input"], x["cost"]) == ("codex", "OtherApp", None, None)
    assert round(x["duration"]) == 3000


def test_records_older_than_30_days_are_dropped(monkeypatch):
    monkeypatch.setattr(history.time, "time", lambda: NOW - 31 * 86400)
    history.record("copilot", "old", "ExampleApp")
    monkeypatch.setattr(history.time, "time", lambda: NOW - 60)
    history.record("copilot", "new", "ExampleApp")
    assert [r["sid"] for r in history.sessions(now=NOW, claude_root="missing")] == ["new"]
    with open(history._file(), encoding="utf-8") as f:
        assert "old" not in f.read()                       # pruned from disk too


def test_csv_is_safe_for_spreadsheets():
    row = {"agent": "gemini", "project": "=HYPERLINK(\"x\")", "sid": "s1", "start": NOW - 120, "end": NOW,
           "duration": 120, "model": "", "input": None, "output": None, "cache_write": None, "cache_read": None,
           "cost": None}
    header, values = list(csv.reader(io.StringIO(history.to_csv([row]))))
    assert header[0] == "agent" and len(header) == len(values)
    assert values[1].startswith("'=")                      # not run as a formula
    assert values[5] == "2.0" and values[7] == "" and values[-1] == ""
