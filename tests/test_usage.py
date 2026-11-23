"""LocalUsage: token counts parsed from fake Claude Code session files (*.jsonl)."""
import json
import os
import time
from datetime import datetime, timezone

import pytest

from skerry.usage import LocalUsage

HOUR = 3600
DAY = 86400


def iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat().replace("+00:00", "Z")


def record(ts, msg_id, inp=0, out=0, cw=0, cr=0, request_id="req"):
    return {"type": "assistant", "timestamp": iso(ts), "requestId": request_id,
            "message": {"id": msg_id, "role": "assistant",
                        "usage": {"input_tokens": inp, "output_tokens": out,
                                  "cache_creation_input_tokens": cw, "cache_read_input_tokens": cr}}}


def write(path, lines, newline_at_end=True):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    text = "\n".join(line if isinstance(line, str) else json.dumps(line) for line in lines)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text + ("\n" if newline_at_end else ""))


@pytest.fixture
def root(tmp_path):
    return str(tmp_path / "projects")


def test_windows_and_totals(root):
    now = time.time()
    write(os.path.join(root, "C--rep-ExampleApp", "s1.jsonl"), [
        {"type": "user", "timestamp": iso(now - 60), "message": {"role": "user", "content": "hi"}},
        record(now - 1 * HOUR, "m1", inp=100, out=50, cw=10, cr=1000),
        record(now - 3 * DAY - 6 * HOUR, "m2", inp=200, out=20),  # mid-bucket, away from day boundaries
        record(now - 8 * DAY, "m3", inp=9999),          # older than 7 days: ignored
        record(now + 2 * HOUR, "m4", inp=9999),          # in the future: ignored
    ])
    st = LocalUsage(root=root).refresh(now)

    assert st["h5"] == {"requests": 1, "input": 100, "output": 50, "cache_write": 10, "cache_read": 1000,
                        "tokens": 160}
    assert st["d7"]["requests"] == 2
    assert st["d7"]["tokens"] == 160 + 220
    assert st["days"][-1] == 160          # today is the last bucket
    assert st["days"][-4] == 220          # three days ago
    assert sum(st["days"]) == 380
    assert st["last"] == pytest.approx(now - HOUR, abs=1)


def test_malformed_and_irrelevant_lines_are_skipped(root):
    now = time.time()
    write(os.path.join(root, "p", "s.jsonl"), [
        '{"usage": broken json',
        json.dumps({"type": "summary", "usage": "not a dict"}),
        json.dumps({"timestamp": "yesterday", "message": {"id": "x", "usage": {"input_tokens": 5}}}),
        record(now - 60, "ok", inp=7, out=3),
    ])
    st = LocalUsage(root=root).refresh(now)
    assert st["h5"]["requests"] == 1
    assert st["h5"]["tokens"] == 10


def test_same_response_in_two_files_counted_once(root):
    now = time.time()
    rec = record(now - 60, "dup", inp=10, out=5, request_id="r1")
    write(os.path.join(root, "p", "original.jsonl"), [rec])
    write(os.path.join(root, "p", "resumed.jsonl"), [rec, record(now - 30, "other", inp=1)])
    st = LocalUsage(root=root).refresh(now)
    assert st["h5"]["requests"] == 2
    assert st["h5"]["input"] == 11


def test_incremental_read_waits_for_complete_line(root):
    now = time.time()
    path = os.path.join(root, "p", "live.jsonl")
    write(path, [record(now - 60, "a", inp=1)])
    usage = LocalUsage(root=root)
    assert usage.refresh(now)["h5"]["requests"] == 1

    partial = json.dumps(record(now - 30, "b", inp=2))
    with open(path, "a", encoding="utf-8") as f:
        f.write(partial[:20])                       # the agent is still writing this line
    assert usage.refresh(now)["h5"]["requests"] == 1

    with open(path, "a", encoding="utf-8") as f:
        f.write(partial[20:] + "\n")
    st = usage.refresh(now)
    assert st["h5"]["requests"] == 2
    assert st["h5"]["input"] == 3
    assert usage.state() == st


def test_rewritten_file_is_read_again(root):
    now = time.time()
    path = os.path.join(root, "p", "s.jsonl")
    write(path, [record(now - 60, "a", inp=100), record(now - 50, "b", inp=100)])
    usage = LocalUsage(root=root)
    assert usage.refresh(now)["h5"]["input"] == 200
    write(path, [record(now - 40, "c", inp=5)])     # shorter file: start over
    assert usage.refresh(now)["h5"]["input"] == 5


def test_old_and_deleted_files_are_dropped(root):
    now = time.time()
    old = os.path.join(root, "p", "old.jsonl")
    keep = os.path.join(root, "p", "keep.jsonl")
    write(old, [record(now - 60, "a", inp=100)])
    write(keep, [record(now - 60, "b", inp=1)])
    os.utime(old, (now - 9 * DAY, now - 9 * DAY))  # untouched for more than 7 days: not even opened
    usage = LocalUsage(root=root)
    assert usage.refresh(now)["h5"]["input"] == 1

    os.remove(keep)
    assert usage.refresh(now)["h5"]["requests"] == 0


def test_missing_root(root):
    st = LocalUsage(root=root).refresh()
    assert st["d7"]["tokens"] == 0
    assert st["last"] is None


def test_default_root_uses_claude_config_dir(tmp_path):
    # conftest points CLAUDE_CONFIG_DIR at tmp_path/claude: the real ~/.claude is never read
    assert LocalUsage()._root == os.path.join(str(tmp_path / "claude"), "projects")
