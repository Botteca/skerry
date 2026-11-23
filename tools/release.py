"""Release helpers used by build.bat and .github/workflows/release.yml.

    python tools/release.py version              # print the version (from skerry/__init__.py, the only place it lives)
    python tools/release.py check-tag v1.2.0     # fail unless the tag matches the version
    python tools/release.py notes 1.2.0          # print the CHANGELOG.md section of that version
    python tools/release.py sums FILE...         # print SHA256SUMS.txt lines ("<sha256>  <name>")
"""
import argparse
import hashlib
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSION_RE = re.compile(r'^VERSION\s*=\s*"([^"]+)"', re.MULTILINE)
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")


def version(root=ROOT):
    """Read VERSION from skerry/__init__.py without importing the package."""
    with open(os.path.join(root, "skerry", "__init__.py"), encoding="utf-8") as f:
        m = VERSION_RE.search(f.read())
    if not m or not SEMVER_RE.match(m.group(1)):
        raise SystemExit("skerry/__init__.py: VERSION missing or not a semantic version (X.Y.Z)")
    return m.group(1)


def check_tag(tag, root=ROOT):
    v = version(root)
    if tag.removeprefix("refs/tags/") != f"v{v}":
        raise SystemExit(f"Tag {tag!r} does not match VERSION {v!r} in skerry/__init__.py (expected v{v})")
    return v


def notes(ver, changelog=None):
    """Body of the '## <ver>' section of CHANGELOG.md (a date or other text may follow the version)."""
    changelog = changelog or os.path.join(ROOT, "CHANGELOG.md")
    with open(changelog, encoding="utf-8") as f:
        text = f.read()
    heading = re.compile(rf"^##[ \t]+\[?v?{re.escape(ver)}\]?(?:[ \t].*)?$", re.MULTILINE)
    m = heading.search(text)
    if not m:
        raise SystemExit(f"CHANGELOG.md has no '## {ver}' section")
    nxt = re.compile(r"^##\s", re.MULTILINE).search(text, m.end())
    body = text[m.end():nxt.start() if nxt else len(text)].strip()
    if not body:
        raise SystemExit(f"CHANGELOG.md section {ver} is empty")
    return body


def sums(files):
    lines = []
    for path in files:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        lines.append(f"{h.hexdigest()}  {os.path.basename(path)}")
    return "\n".join(lines) + "\n"


def main(argv=None):
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-o", "--out", help="write to this file (UTF-8) instead of stdout")
    ap = argparse.ArgumentParser(description="Skerry release helpers")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("version", parents=[common])
    sub.add_parser("check-tag", parents=[common]).add_argument("tag")
    sub.add_parser("notes", parents=[common]).add_argument("version")
    sub.add_parser("sums", parents=[common]).add_argument("files", nargs="+")
    a = ap.parse_args(argv)
    out = {"version": lambda: version(), "check-tag": lambda: check_tag(a.tag), "notes": lambda: notes(a.version),
           "sums": lambda: sums(a.files)}[a.cmd]()
    out = out if out.endswith("\n") else out + "\n"
    if a.out:
        with open(a.out, "w", encoding="utf-8", newline="\n") as f:
            f.write(out)
    else:
        sys.stdout.write(out)


if __name__ == "__main__":
    main()
