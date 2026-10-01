"""Checks of the PyPI package agon-arena, for CI and the release workflow (standard library only; not part of Agon).

python scripts/check_package.py dist DIR            the wheel and sdist in DIR: what they hold, their metadata
python scripts/check_package.py installed CMD...    an installed agon: --version, and setup (it writes nothing)
python scripts/check_package.py uvx-kill WHEEL      killing uvx ends the Agon it started (the Python under it)
python scripts/check_package.py versions [TAG]      agon.py, the plugin manifests, server.json (and the tag) agree
"""
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import time
import zipfile
from email.parser import Parser
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
VERSION = re.search(r'^__version__ = VERSION = "([^"]+)"', (HERE / "agon.py").read_text(encoding="utf-8"), re.M)[1]


def check(ok, what):
    print(("ok    " if ok else "FAIL  ") + what)
    if not ok:
        sys.exit(1)


def dist(folder):
    wheels, sdists = sorted(Path(folder).glob("*.whl")), sorted(Path(folder).glob("*.tar.gz"))
    check(len(wheels) == 1 and len(sdists) == 1, f"one wheel and one sdist in {folder}: {wheels + sdists}")
    wheel, sdist = wheels[0], sdists[0]
    check(wheel.name == f"agon_arena-{VERSION}-py3-none-any.whl", f"the wheel's name: {wheel.name}")
    with zipfile.ZipFile(wheel) as z:
        names = z.namelist()
        info = f"agon_arena-{VERSION}.dist-info/"
        check([n for n in names if not n.startswith(info)] == ["agon.py"], f"the wheel holds agon.py only: {names}")
        check(z.read("agon.py") == (HERE / "agon.py").read_bytes(), "the wheel's agon.py is this agon.py")
        meta = Parser().parsestr(z.read(info + "METADATA").decode())
        entry = z.read(info + "entry_points.txt").decode()
    check(meta["Name"] == "agon-arena" and meta["Version"] == VERSION, f"name and version: {meta['Name']} {meta['Version']}")
    check(meta["License-Expression"] == "MIT" and meta["Requires-Python"] == ">=3.10", "MIT, Python 3.10+")
    check(meta.get_all("Requires-Dist") is None, "no dependencies")
    check("Author-email" not in meta and "Maintainer-email" not in meta and "@" not in "".join(
        f"{k}{v}" for k, v in meta.items()), "no e-mail address in the metadata")
    check("<!-- mcp-name: io.github.giliandar5-lab/agon -->" in meta.get_payload(), "the README with the mcp-name")
    scripts = {k.strip(): v.strip() for k, _, v in (row.partition("=") for row in entry.splitlines()) if v}
    check(scripts == {"agon": "agon:cli", "agon-arena": "agon:cli"}, f"the agon and agon-arena commands: {scripts}")
    with tarfile.open(sdist) as t:
        files = {Path(n).name for n in t.getnames()}
    check({"agon.py", "pyproject.toml", "README.md", "LICENSE", "PKG-INFO"} <= files and "test_agon.py" not in files,
          f"the sdist: {sorted(files)}")


def installed(command):
    out = subprocess.run([*command, "--version"], capture_output=True, text=True, timeout=120)
    check(out.returncode == 0 and out.stdout == f"agon {VERSION}\n", f"{command} --version: {out.stdout!r} {out.stderr!r}")
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp, "agon.db")
        p = subprocess.run([*command, "setup"], capture_output=True, text=True, timeout=120,
                           env=dict(os.environ, AGON_DB=str(db)))
        check(p.returncode == 0 and not db.exists(), f"{command} setup runs and writes nothing: {p.stderr!r}")
    line = next((row for row in p.stdout.splitlines() if row.startswith("Agon    ")), "")
    check("archive-v0" not in p.stdout and "environments-v2" not in p.stdout, "no path into uv's cache")
    check("agon" in line and not line.endswith(".py"), f"setup names the agon command: {line!r}")
    print(p.stdout)


def tree():  # {pid: (parent, name)} of every process
    if os.name == "nt":
        rows = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-CimInstance Win32_Process | ForEach-Object"
                               " { \"$($_.ProcessId) $($_.ParentProcessId) $($_.Name)\" }"],
                              capture_output=True, text=True, timeout=60).stdout.splitlines()
    else:
        rows = subprocess.run(["ps", "-A", "-o", "pid=,ppid=,comm="], capture_output=True, text=True).stdout.splitlines()
    found = {}
    for row in rows:
        parts = row.split(None, 2)
        if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
            found[int(parts[0])] = (int(parts[1]), parts[2])
    return found


def descendants(pid):
    procs, found, todo = tree(), [], [pid]
    while todo:
        parent = todo.pop()
        for child, (ppid, name) in procs.items():
            if ppid == parent and child not in found:
                found.append(child)
                todo.append(child)
    return {child: procs[child][1] for child in found}


def uvx_kill(wheel):
    """uvx starts Agon as a child. When an app closes Agon, it ends uvx (TerminateProcess on Windows, SIGTERM elsewhere)
    and closes Agon's stdin: Agon's Python must not outlive both. Prints which of the two ended it: on Windows, uv's
    trampoline puts the child in a job object that dies with uvx; elsewhere uv passes SIGTERM on, and Agon ends at the
    end of its stdin anyway."""
    p = subprocess.Popen(["uvx", "--from", str(Path(wheel).resolve()), "agon-arena", "claude"], stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, env=dict(os.environ, AGON_DB=str(Path(tempfile.mkdtemp(), "a.db"))))
    hello = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2025-06-18", "clientInfo": {"name": "check", "version": "1"}}}
    p.stdin.write(json.dumps(hello).encode() + b"\n")
    p.stdin.flush()
    reply = json.loads(p.stdout.readline())
    check(reply["result"]["serverInfo"]["version"] == VERSION, "Agon answers through uvx")
    under = descendants(p.pid)
    print(f"uvx is {p.pid}; under it: {under}")
    agon = {pid for pid, name in under.items() if "python" in name.lower() or "agon" in name.lower()}
    check(bool(agon), "Agon's Python runs under uvx")

    def gone(seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end and agon & set(tree()):
            time.sleep(0.5)
        return not agon & set(tree())

    p.terminate()  # its stdin stays open on this side for now
    p.wait(30)
    if gone(15):
        print("RESULT: ending uvx ends Agon's Python at once, while its stdin is still open")
        return p.stdin.close()
    print(f"after ending uvx, still running: {agon & set(tree())}; now closing its stdin")
    p.stdin.close()
    check(gone(15), "Agon's Python ends once its stdin closes")
    print("RESULT: ending uvx leaves Agon's Python running until its stdin closes, then it ends")


def versions(tag=""):
    found = {"agon.py": VERSION}
    for name in (".claude-plugin/plugin.json", ".codex-plugin/plugin.json"):
        found[name] = json.loads((HERE / name).read_text(encoding="utf-8"))["version"]
    server = json.loads((HERE / "server.json").read_text(encoding="utf-8"))
    found["server.json"], found["server.json package"] = server["version"], server["packages"][0]["version"]
    if tag:
        found["the tag"] = tag.removeprefix("v")
    check(len(set(found.values())) == 1, f"one version: {found}")


if __name__ == "__main__":
    what, args = sys.argv[1], sys.argv[2:]
    {"dist": lambda: dist(args[0]), "installed": lambda: installed(args), "uvx-kill": lambda: uvx_kill(args[0]),
     "versions": lambda: versions(*args)}[what]()
