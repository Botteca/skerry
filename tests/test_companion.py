"""Companion (ui/companion.js): mood priorities, read with Node (skipped if Node is not installed); setting defaults."""
import json
import os
import shutil
import subprocess

import pytest

from skerry import api, settings

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOW = 1_000_000


def moods(cases):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is needed to run ui/companion.js")
    code = ("const C=require(process.argv[1]);const cases=JSON.parse(process.argv[2]);"
            "process.stdout.write(JSON.stringify(cases.map(([s,q])=>C.mood(s,q))));")
    out = subprocess.run([node, "-e", code, os.path.join(ROOT, "ui", "companion.js"), json.dumps(cases)],
                         capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(out.stdout)


def state(**kw):
    return {"now": NOW, "sessions": [], "pending": [], "alerts": [], "limits": None, "meeting": None,
            "settings": {"alerts": {"limits": [80, 90]}}, **kw}


def sess(status, done_ago=0):
    return {"status": status, "done_at": NOW - done_ago}


def test_mood_priorities():
    cases = [
        (state(), 0),
        (state(), 601),
        (state(sessions=[sess("working")]), 0),
        (state(sessions=[sess("working")], pending=[{"id": 1}]), 0),
        (state(sessions=[sess("done", 1), sess("working")]), 0),
        (state(sessions=[sess("done", 3)]), 0),
        (state(sessions=[sess("error", 5), sess("working")]), 0),
        (state(sessions=[sess("error", 60)]), 0),
        (state(alerts=[{"level": "danger"}]), 0),
        (state(limits={"five_hour": {"used_percentage": 91}}), 0),
        (state(limits={"five_hour": {"used_percentage": 85}}), 0),
        (state(limits={"five_hour": {"used_percentage": 95}}, sessions=[sess("working")]), 0),
        (state(meeting={"start": NOW + 240, "in_progress": False}), 0),
        (state(meeting={"start": NOW + 900, "in_progress": False}), 0),
        (state(meeting={"start": NOW - 60, "in_progress": True}), 700),
    ]
    assert moods(cases) == ["rest", "sleep", "work", "perm", "happy", "rest", "worry", "rest", "worry", "worry",
                            "rest", "work", "meet", "rest", "sleep"]


def test_companion_is_never_on_by_default_and_is_settable():
    assert settings.DEFAULTS["companion"] == {"style": "dot", "energy": "lively"}
    assert {"companion.style", "companion.energy"} <= api.SETTABLE
