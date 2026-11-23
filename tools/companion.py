"""Companion checks and README sprite sheet, with headless Microsoft Edge (or Chrome).

    python tools/companion.py              # self-checks (normal + reduced motion), CPU at rest, docs/img/companion.png
    python tools/companion.py --no-cpu     # skip the 4 x 12 s CPU measurement
    python tools/companion.py --style puffin

Self-checks run in tools/companion.html: contrast of every mood colour in both themes (>= 3:1), no looping animation
at rest, every animation and timer stopped while the window is hidden, nothing looping with reduced motion, fixed size.
CPU: the island at rest with the classic dot and with the companion, CPU time of the whole browser process tree.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = "file:///" + os.path.join(ROOT, "tools", "companion.html").replace("\\", "/")
BROWSERS = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe"]
CPU_LIMIT = 1.5     # extra % of one core the companion may add at rest over the classic dot (run-to-run noise ~1%)


def browser_cmd(browser, profile, *extra):
    return [browser, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
            "--disable-extensions", "--allow-file-access-from-files", f"--user-data-dir={profile}", *extra]


def self_check(browser, style, reduced):
    with tempfile.TemporaryDirectory() as profile:
        extra = ["--force-prefers-reduced-motion"] if reduced else []
        cmd = browser_cmd(browser, profile, *extra, "--virtual-time-budget=6000", "--dump-dom", f"{PAGE}?mode=check&style={style}")
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=45).stdout
        except subprocess.TimeoutExpired as e:   # headless Edge sometimes prints the DOM and then does not exit
            out = e.stdout or ""
            out = out.decode("utf-8", "replace") if isinstance(out, bytes) else out
    m = re.search(r'<pre id="out">(.*?)</pre>', out, re.S)
    if not m:
        return {"fails": ["the check page produced no result"]}
    return json.loads(m.group(1).replace("&quot;", '"').replace("&amp;", "&"))


def cpu_seconds(marker):
    """{pid: CPU seconds} of the browser processes whose command line contains marker (our temporary profile)."""
    ps = ("Get-CimInstance Win32_Process | Where-Object { $_.Name -ne 'powershell.exe' -and $_.CommandLine -like '*%s*' } | "
          "ForEach-Object { '{0} {1}' -f $_.ProcessId, ($_.KernelModeTime + $_.UserModeTime) }") % marker
    out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True).stdout
    return {int(pid): int(t) / 1e7 for pid, t in (line.split() for line in out.splitlines() if line.strip())}


def cpu_at_rest(browser, style, seconds=12):
    """% of one core used by the page at rest, summed over the processes alive for the whole window."""
    with tempfile.TemporaryDirectory(prefix="skerry-cpu-") as profile:
        proc = subprocess.Popen(browser_cmd(browser, profile, "--window-size=400,80", f"{PAGE}?mode=idle&style={style}"),
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            time.sleep(5)                  # let start-up settle
            marker = os.path.basename(profile)
            a, t0 = cpu_seconds(marker), time.time()
            time.sleep(seconds)
            b, t1 = cpu_seconds(marker), time.time()
        finally:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
            time.sleep(1)
    return 100 * sum(b[p] - a[p] for p in a.keys() & b.keys()) / (t1 - t0)


def sheet(browser, style, out):
    with tempfile.TemporaryDirectory() as profile:
        subprocess.run(browser_cmd(browser, profile, "--force-device-scale-factor=2", "--window-size=880,248",
                                   "--virtual-time-budget=3000", f"--screenshot={out}", f"{PAGE}?mode=sheet&style={style}"),
                       check=True, capture_output=True, timeout=120)
    if not os.path.exists(out):
        raise RuntimeError("no sprite sheet produced")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--style", default="eyes")
    ap.add_argument("--no-cpu", action="store_true")
    args = ap.parse_args()
    browser = next((b for b in BROWSERS if os.path.exists(b)), None)
    if not browser:
        sys.exit("Microsoft Edge or Google Chrome is needed")
    fails = []
    for reduced in (False, True):
        r = self_check(browser, args.style, reduced)
        label = "reduced motion" if reduced else "normal"
        print(f"[{label}] rest={r.get('rest')} work={r.get('work')} hidden={r.get('hidden')}")
        if not reduced:
            print("contrast:", ", ".join(f"{k} {v}" for k, v in r.get("contrast", {}).items()))
        fails += [f"{label}: {f}" for f in r["fails"]]
    if not args.no_cpu:
        runs = [cpu_at_rest(browser, s) for s in ("dot", args.style, "dot", args.style)]   # alternated: less drift
        dot, comp = (runs[0] + runs[2]) / 2, (runs[1] + runs[3]) / 2
        print(f"CPU at rest (% of one core): dot {dot:.2f}, {args.style} {comp:.2f}")
        if comp - dot > CPU_LIMIT:
            fails.append(f"CPU at rest: {args.style} adds {comp - dot:.2f}% over the dot")
    out = os.path.join(ROOT, "docs", "img", "companion.png" if args.style == "eyes" else f"companion-{args.style}.png")
    sheet(browser, args.style, out)
    print("wrote", os.path.relpath(out, ROOT))
    if fails:
        sys.exit("FAILED:\n  " + "\n  ".join(fails))
    print("all checks passed")


if __name__ == "__main__":
    main()
