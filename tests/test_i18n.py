"""Translations: same keys in English and Italian, every used key exists, and no visible string is hard-coded.

The UI dictionaries live in ui/i18n.js and are read with Node (skipped if Node is not installed);
the Python ones live in skerry/i18n.py.
"""
import ast
import html.parser
import json
import os
import re
import shutil
import subprocess

import pytest

from skerry import i18n

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(ROOT, "ui")
PLACEHOLDER = re.compile(r"\{(\w+)\}")
KEY_LITERAL = re.compile(r"""['"]([a-z][A-Za-z0-9]*(?:\.[A-Za-z0-9_]+)+)['"]""")

# Product and brand names are the same in every language.
BRANDS = {"Skerry", "Google Calendar", "Claude Code", "Codex", "Gemini CLI", "Copilot CLI", "GitHub Copilot CLI", "Microsoft 365", "Google Workspace", "SQL Server", "Azure SQL",
          "Azure Data Factory"}


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def settings_script():
    return re.findall(r"<script>(.*?)</script>", read("ui", "settings.html"), re.S)[0]


@pytest.fixture(scope="module")
def ui_strings():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is needed to read ui/i18n.js")
    code = ("const fs=require('fs'),vm=require('vm');const c={};vm.createContext(c);"
            "vm.runInContext(fs.readFileSync(process.argv[1],'utf8')+';this.__s=I18N_STRINGS;',c);"
            "process.stdout.write(JSON.stringify(c.__s));")
    out = subprocess.run([node, "-e", code, os.path.join(UI, "i18n.js")], capture_output=True, text=True,
                         encoding="utf-8", check=True)
    return json.loads(out.stdout)


def placeholders(value):
    forms = value.values() if isinstance(value, dict) else [value]
    return {name for form in forms for name in PLACEHOLDER.findall(form)}


def check_dictionaries(strings):
    assert set(strings) == {"en", "it"}
    en, it = strings["en"], strings["it"]
    assert sorted(set(en) - set(it)) == [], "keys missing in Italian"
    assert sorted(set(it) - set(en)) == [], "keys missing in English"
    for key in en:
        assert type(en[key]) is type(it[key]), key
        if isinstance(en[key], dict):
            assert set(en[key]) == set(it[key]) and "other" in en[key], key
        assert placeholders(en[key]) == placeholders(it[key]), f"different placeholders in {key}"
        forms = en[key].values() if isinstance(en[key], dict) else [en[key]]
        assert all(f.strip() for f in forms), f"empty translation: {key}"


# ---------------------------------------------------------------- dictionaries

def test_ui_dictionaries_match(ui_strings):
    check_dictionaries(ui_strings)


def test_python_dictionaries_match():
    check_dictionaries(i18n.STRINGS)


def test_ui_keys_used_exist_and_are_used(ui_strings):
    en = ui_strings["en"]
    namespaces = {k.split(".")[0] for k in en}
    sources = read("ui", "skerry.js") + read("ui", "settings.html")
    used = {k for k in KEY_LITERAL.findall(sources) if k.split(".")[0] in namespaces}
    used |= set(re.findall(r'data-i18n(?:-html|-title|-placeholder)?="([^"]+)"', sources))
    block = re.search(r"const MODULES = \[(.*?)\];", settings_script(), re.S).group(1)
    modules = re.findall(r"\['(\w+)', '[^']+'", block)                       # MODULES: mod.<k> and mod.<k>.desc
    assert modules, "MODULES list not found"
    used |= {f"mod.{m}.desc" for m in modules} | {f"mod.{m}" for m in modules if f"mod.{m}" in en}
    from skerry.updater import VISIBLE                                        # 'upd.status.' + updater status
    used |= {f"upd.status.{s}" for s in ("idle", "checking", "up_to_date", "error") + VISIBLE}
    assert sorted(used - set(en)) == [], "keys used in the UI but missing from ui/i18n.js"
    assert sorted(set(en) - used) == [], "keys never used by the UI"


def test_python_keys_used_exist_and_are_used():
    en = i18n.STRINGS["en"]
    namespaces = {k.split(".")[0] for k in en}
    sources = ""
    for dirpath, _dirs, names in os.walk(os.path.join(ROOT, "skerry")):
        sources += "".join(read(dirpath, n) for n in names if n.endswith(".py") and n != "i18n.py")
    sources += read("app.py")
    used = {k for k in KEY_LITERAL.findall(sources) if k.split(".")[0] in namespaces}
    used |= {f"timer.{phase}" for phase in ("focus", "short_break", "long_break")}   # Msg("timer." + phase)
    assert sorted(used - set(en)) == []
    assert sorted(set(en) - used) == [], "keys never used by Python code"


# ---------------------------------------------------------------- runtime behaviour

def test_python_translation_and_live_switch():
    old = i18n.current()
    try:
        msg = i18n.Msg("alert.limit", label=i18n.Msg("limit.five_hour"), pct=85)
        i18n.set_language("en")
        assert str(msg) == "5-hour limit at 85%"
        i18n.set_language("it")
        assert str(msg) == "Limite 5 ore al 85%"                       # same object, new language
        assert i18n.t("alert.meeting_soon", title="Standup", n=1) == "Standup tra 1 min"
        assert i18n.t("no.such.key") == "no.such.key"
        assert i18n.render("plain text") == "plain text"
    finally:
        i18n.set_language(old)


def test_language_setting(monkeypatch):
    monkeypatch.setattr(i18n, "system_language", lambda: "it")
    assert i18n.resolve("auto") == "it"
    assert i18n.resolve("en") == "en"
    assert i18n.resolve("fr") == "it"   # unknown values fall back to automatic


def test_language_is_settable_from_the_ui():
    from skerry.api import SETTABLE
    from skerry.settings import DEFAULTS
    assert "language" in SETTABLE
    assert DEFAULTS["language"] == "auto"


# ---------------------------------------------------------------- hard-coded strings: HTML

class TextCollector(html.parser.HTMLParser):
    """Visible text and attributes of a page, skipping script/style and elements filled by data-i18n*."""
    VOID = {"meta", "link", "input", "br", "img", "hr", "source", "path", "circle", "rect"}

    def __init__(self):
        super().__init__()
        self.stack, self.texts, self.attrs = [], [], []
        self.in_body = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "body":
            self.in_body = True
        translated = any(k.startswith("data-i18n") for k in a)
        for name in ("title", "placeholder", "alt", "aria-label"):
            if self.in_body and a.get(name) and f"data-i18n-{name}" not in a:
                self.attrs.append(f"{tag}[{name}]={a[name]!r}")
        if tag not in self.VOID:
            self.stack.append((tag, translated))

    def handle_endtag(self, tag):
        while self.stack:
            if self.stack.pop()[0] == tag:
                break

    def handle_data(self, data):
        if not self.in_body or any(t in ("script", "style") or tr for t, tr in self.stack):
            return
        text = data.strip()
        if re.search(r"[A-Za-zÀ-ÖØ-öø-ÿ]{2,}", text) and text not in BRANDS:
            self.texts.append(text)


@pytest.mark.parametrize("page", ["index.html", "settings.html"])
def test_no_hardcoded_text_in_html(page):
    p = TextCollector()
    p.feed(read("ui", page))
    assert p.texts == [], f"visible text without data-i18n in {page}"
    assert p.attrs == [], f"visible attributes without data-i18n-* in {page}"


# ---------------------------------------------------------------- hard-coded strings: JavaScript

def js_literals(src):
    """String and template literals of a JS source (template expressions replaced by \\x00).
    Small lexer: comments, quotes, nested templates and regex literals."""
    out, i = [], 0

    def code(i, until_brace):
        depth, prev = 0, "("
        while i < len(src):
            c = src[i]
            if src.startswith("//", i):
                i = src.find("\n", i) if "\n" in src[i:] else len(src)
                continue
            if src.startswith("/*", i):
                i = src.index("*/", i) + 2
                continue
            if c in "'\"":
                j = i + 1
                while src[j] != c:
                    j += 2 if src[j] == "\\" else 1
                out.append(("str", src[i + 1:j]))
                i, prev = j + 1, "a"
                continue
            if c == "`":
                i, prev = template(i + 1), "a"
                continue
            if c == "/" and prev in "(,=:[!&|?{};+-*%<>~^":
                j, cls = i + 1, False
                while cls or src[j] != "/":
                    if src[j] == "\\":
                        j += 1
                    elif src[j] == "[":
                        cls = True
                    elif src[j] == "]":
                        cls = False
                    j += 1
                i, prev = j + 1, "a"
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                if until_brace and depth == 0:
                    return i + 1
                depth -= 1
            if not c.isspace():
                prev = c
            i += 1
        return i

    def template(i):
        parts, buf = [], []
        while src[i] != "`":
            if src[i] == "\\":
                buf.append(src[i:i + 2])
                i += 2
            elif src.startswith("${", i):
                buf.append("\x00")
                i = code(i + 2, True)
            else:
                buf.append(src[i])
                i += 1
        parts.append("".join(buf))
        out.append(("tpl", "".join(parts)))
        return i + 1

    code(i, False)
    return out


WORD = r"[A-Za-zÀ-ÖØ-öø-ÿ]{2,}"
JS_ALLOWED = BRANDS | {"Files", "use strict", "ArrowUp", "ArrowDown"}   # DataTransfer type, KeyboardEvent.key names


def visible_js_text(kind, text):
    """Words a literal would show to the user, or [] if it looks like code."""
    found = [m for m in re.findall(r'(?:title|placeholder|alt|aria-label)="([^"]*)"', text)
             if re.search(WORD, m.replace("\x00", " "))]
    if "<" in text:
        stripped = re.sub(r"&\w+;", " ", re.sub(r"<[^>]*>", " ", text)).replace("\x00", " ")
        stripped = re.sub(r"(?<!\w)/\w+", " ", stripped)          # slash commands such as /usage
        for brand in sorted(BRANDS, key=len, reverse=True):
            stripped = stripped.replace(brand, " ")
        found += re.findall(WORD, stripped)
        return found
    plain = text.replace("\x00", " ").strip()
    if not plain or plain in JS_ALLOWED:
        return found
    if ("#" in plain or "[" in plain) and not re.search(r"[A-Z]", plain):
        return found                                       # CSS selector
    if re.search(WORD + r"\s+" + WORD, plain) or re.search(r"[À-ÖØ-öø-ÿ]", plain) or re.match(r"[A-Z][a-z]{2,}", plain):
        found.append(plain)
    return found


@pytest.mark.parametrize("name", ["skerry.js", "settings.html <script>"])
def test_no_hardcoded_text_in_js(name):
    src = read("ui", "skerry.js") if name == "skerry.js" else settings_script()
    problems = [(kind, text[:80]) for kind, text in js_literals(src) if visible_js_text(kind, text)]
    assert problems == [], f"visible strings not going through t()/tx() in {name}"


def test_js_lexer_finds_text():
    """The guided grep must catch the patterns it is meant to catch."""
    sample = r"""const a = `<b>Ciao</b>${x ? `<i title="Suggerimento">${y}</i>` : ''}`; const r = /["']/g;
                 el.textContent = 'Operazione non riuscita'; q('#nav button'); // comment 'Testo'"""
    hits = [text for kind, text in js_literals(sample) if visible_js_text(kind, text)]
    assert sorted(hits) == sorted(["<b>Ciao</b>\x00", '<i title="Suggerimento">\x00</i>', "Operazione non riuscita"])


# ---------------------------------------------------------------- hard-coded strings: Python

PY_MODULES = ["app.py", "skerry/store.py", "skerry/timer.py", "skerry/system.py", "skerry/tray.py",
              "skerry/api.py", "skerry/connectors/m365.py", "skerry/connectors/adf.py",
              "skerry/connectors/azure.py", "skerry/connectors/sql.py", "skerry/connectors/google.py", "skerry/shelf.py", "skerry/usage.py", "skerry/media.py"]
# Strings that look like prose but are data, not UI text.
PY_ALLOWED = {
    "Skerry overlay",                      # internal window title used by FindWindowW (app.py), never shown
    "Hands-Free AG", "Avrcp Transport",    # suffixes Windows adds to Bluetooth names, stripped (system.py)
    "ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server",   # ODBC driver names (connectors/sql.py)
    r"\[SQL Server\]([^\[\]()]+)",         # pattern that extracts the server message from an ODBC error
    "<!doctype html><meta charset='utf-8'><p style='font:16px system-ui'>%s</p>",   # sign-in page shell (google.py)
}
LOG_METHODS = {"debug", "info", "warning", "error", "exception", "critical"}


def prose(text):
    return bool(re.search(WORD + r"\s+" + WORD, text) or re.search(r"[À-ÖØ-öø-ÿ]", text)) and text not in PY_ALLOWED \
        and text not in BRANDS


@pytest.mark.parametrize("module", PY_MODULES)
def test_no_hardcoded_text_in_python(module):
    tree = ast.parse(read(module))
    skip = set()
    for node in ast.walk(tree):
        # docstrings
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body \
                and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant):
            skip.add(id(node.body[0].value))
        # log messages (English by rule), exception messages, Windows/class names passed to APIs
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in LOG_METHODS:
            skip.update(id(n) for a in node.args for n in ast.walk(a))
        if isinstance(node, ast.Raise) and node.exc is not None:
            skip.update(id(n) for n in ast.walk(node.exc))
        # tuples of lowercase patterns (e.g. Bluetooth device-name keywords in system.py) are data
        if isinstance(node, (ast.Tuple, ast.List, ast.Set)) and node.elts and all(
                isinstance(e, ast.Constant) and isinstance(e.value, str) and e.value == e.value.lower()
                for e in node.elts):
            skip.update(id(e) for e in node.elts)
    problems = []
    for node in ast.walk(tree):
        if id(node) in skip:
            continue
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and prose(node.value):
            problems.append((node.lineno, node.value[:70]))
        elif isinstance(node, ast.JoinedStr):
            literal = " ".join(v.value for v in node.values if isinstance(v, ast.Constant))
            if prose(literal):
                problems.append((node.lineno, literal[:70]))
                skip.update(id(v) for v in node.values)
    assert problems == [], f"visible strings not going through skerry.i18n in {module}"
