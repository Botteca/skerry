"""Text case conversions (ui/textcase.js), run with Node (skipped if Node is not installed)."""
import json
import os
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(text):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is needed to run ui/textcase.js")
    code = ("const T=require(process.argv[1]);const s=JSON.parse(process.argv[2]);const o={counts:T.counts(s)};"
            "for(const m of T.MODES)o[m]=T.convert(m,s);process.stdout.write(JSON.stringify(o));")
    out = subprocess.run([node, "-e", code, os.path.join(ROOT, "ui", "textcase.js"), json.dumps(text)],
                         capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(out.stdout)


def test_conversions():
    r = run("ciao MONDO. come stai? l'isola è bella\nnuova riga")
    assert r["upper"] == "CIAO MONDO. COME STAI? L'ISOLA È BELLA\nNUOVA RIGA"
    assert r["lower"] == "ciao mondo. come stai? l'isola è bella\nnuova riga"
    assert r["sentence"] == "Ciao mondo. Come stai? L'isola è bella\nNuova riga"
    assert r["capital"] == "Ciao Mondo. Come Stai? L'isola È Bella\nNuova Riga"
    assert r["alternate"] == "cIaO mOnDo. CoMe StAi? L'iSoLa È bElLa\nNuOvA rIgA"
    assert r["inverse"] == "CIAO mondo. COME STAI? L'ISOLA È BELLA\nNUOVA RIGA"
    assert r["counts"] == {"chars": 49, "words": 9}


def test_empty_text():
    r = run("")
    assert r["upper"] == "" and r["counts"] == {"chars": 0, "words": 0}
