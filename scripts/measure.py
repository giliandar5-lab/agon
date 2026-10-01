"""Measures Agon for the README's numbers (standard library only; not part of Agon itself).

python scripts/measure.py idle [SECONDS]        idle CPU and memory of an agent's MCP server and of the arena (with
                                                one page open), and the size of what every agent reads at the start
python scripts/measure.py tokens WITH WITHOUT   tokens per turn from two logs of the same prompt, with Agon and
                                                without: claude -p --output-format stream-json --verbose, or
                                                codex exec --json (see the README's "Measured")

Memory: on Windows the private bytes (and the working set), on Linux the proportional set size (PSS: shared pages
split between the processes that share them), on macOS the physical footprint, the number Activity Monitor shows.
"""
import ctypes
import http.client
import json
import os
import platform
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

AGON = Path(__file__).resolve().parent.parent / "agon.py"


def usage(pid, proc=None):
    """(CPU seconds used so far, memory in bytes, a second memory figure or None) of process `pid`."""
    if sys.platform == "win32":
        return windows_usage(proc)
    if sys.platform == "darwin":
        return mac_usage(pid)
    fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    cpu = (int(fields[11]) + int(fields[12])) / os.sysconf("SC_CLK_TCK")  # utime, stime
    memory = {}
    for row in Path(f"/proc/{pid}/smaps_rollup").read_text().splitlines():
        name, _, value = row.partition(":")
        if value.strip().endswith("kB"):
            memory[name] = int(value.split()[0]) * 1024
    return cpu, memory["Pss"], memory["Rss"]


def windows_usage(proc):
    from ctypes import wintypes

    class Counters(ctypes.Structure):  # PROCESS_MEMORY_COUNTERS_EX
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                                                 "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
                                                 "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage",
                                                 "PrivateUsage")]

    handle = wintypes.HANDLE(int(proc._handle))  # Popen's own handle has every access right
    times = [wintypes.FILETIME() for _ in range(4)]
    if not ctypes.windll.kernel32.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
        raise OSError("GetProcessTimes failed")
    cpu = sum((t.dwHighDateTime << 32 | t.dwLowDateTime) for t in times[2:]) / 1e7  # kernel + user, 100 ns units
    counters = Counters()
    counters.cb = ctypes.sizeof(Counters)
    if not ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
        raise OSError("GetProcessMemoryInfo failed")
    return cpu, counters.PrivateUsage, counters.WorkingSetSize


def mac_usage(pid):
    class Info(ctypes.Structure):  # struct rusage_info_v2 (sys/resource.h)
        _fields_ = [("uuid", ctypes.c_uint8 * 16)] + [(name, ctypes.c_uint64) for name in (
            "user_time", "system_time", "pkg_idle_wkups", "interrupt_wkups", "pageins", "wired_size", "resident_size",
            "phys_footprint", "proc_start_abstime", "proc_exit_abstime", "child_user_time", "child_system_time",
            "child_pkg_idle_wkups", "child_interrupt_wkups", "child_pageins", "child_elapsed_abstime",
            "diskio_bytesread", "diskio_byteswritten")]

    class Timebase(ctypes.Structure):
        _fields_ = [("numer", ctypes.c_uint32), ("denom", ctypes.c_uint32)]

    lib = ctypes.CDLL("/usr/lib/libSystem.B.dylib")
    info, base = Info(), Timebase()
    if lib.proc_pid_rusage(pid, 2, ctypes.byref(info)):  # RUSAGE_INFO_V2
        raise OSError("proc_pid_rusage failed")
    lib.mach_timebase_info(ctypes.byref(base))  # the times are in Mach ticks: 1 ns on Intel, 125/3 ns on Apple silicon
    cpu = (info.user_time + info.system_time) * base.numer / base.denom / 1e9
    return cpu, info.phys_footprint, info.resident_size


def idle(proc, seconds):
    """CPU percent of one core and memory of `proc` over `seconds` of idling, after a second to settle."""
    time.sleep(1)
    cpu0, t0 = usage(proc.pid, proc)[0], time.monotonic()
    time.sleep(seconds)
    cpu1, memory, other = usage(proc.pid, proc)
    return {"cpu_percent": round(100 * (cpu1 - cpu0) / (time.monotonic() - t0), 3), "memory_mb": round(memory / 2**20, 1),
            "other_memory_mb": round(other / 2**20, 1) if other else None}


def rpc(proc, method, params=None, id=1):
    proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": id, "method": method, "params": params or {}}).encode() + b"\n")
    proc.stdin.flush()
    return proc.stdout.readline()


def measure_idle(seconds):
    env = dict(os.environ, AGON_DB=str(Path(tempfile.mkdtemp(), "measure.db")))
    found = {"date": time.strftime("%Y-%m-%d"), "os": f"{platform.system()} {platform.release()}",
             "machine": platform.machine(), "python": platform.python_version(), "seconds": seconds}
    server = subprocess.Popen([sys.executable, str(AGON), "claude"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                              env=env)
    try:
        hello = json.loads(rpc(server, "initialize", {"protocolVersion": "2025-06-18",
                                                      "clientInfo": {"name": "measure", "version": "1"}}))
        tools = rpc(server, "tools/list", id=2)
        found["tools_list_bytes"] = len(tools.rstrip(b"\r\n"))
        found["instructions_chars"] = len(hello["result"]["instructions"])
        found["initialize_bytes"] = len(json.dumps(hello))
        found["server"] = idle(server, seconds)  # waiting for the app's next request, as it does all day
    finally:
        server.stdin.close()
        server.wait(30)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    arena = subprocess.Popen([sys.executable, "-c", "import sys, webbrowser; sys.path.insert(0, sys.argv[1]);"
                              " webbrowser.open = lambda url: None; import agon; agon.PORT = int(sys.argv[2]);"
                              " sys.exit(agon.arena())", str(AGON.parent), str(port)],
                             stdout=subprocess.PIPE, env=env)
    try:
        arena.stdout.readline()  # "Agon arena: ...": it listens
        page = http.client.HTTPConnection("127.0.0.1", port, timeout=seconds + 30)
        page.request("GET", "/events", headers={"Host": f"127.0.0.1:{port}"})
        page.getresponse()  # one open page's event stream, which the arena keeps up to date
        found["arena"] = idle(arena, seconds)
        page.close()
    finally:
        arena.terminate()
        arena.wait(30)
    return found


def turns(path):
    """[(input tokens, cached of them, output tokens)] per turn in one app's log: claude's stream-json (its result
    event) or codex exec --json (turn.completed). Input counts every token the model read, cached or not."""
    found = []
    for row in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(row)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        usage_ = event.get("usage") or {}
        if event.get("type") == "result":  # Claude Code
            cached = usage_.get("cache_read_input_tokens", 0)
            found.append((usage_.get("input_tokens", 0) + usage_.get("cache_creation_input_tokens", 0) + cached,
                          cached, usage_.get("output_tokens", 0)))
        elif event.get("type") == "turn.completed":  # Codex: input_tokens already includes the cached ones
            found.append((usage_.get("input_tokens", 0), usage_.get("cached_input_tokens", 0),
                          usage_.get("output_tokens", 0)))
    return found


def measure_tokens(with_agon, without):
    a, b = turns(with_agon), turns(without)
    if not a or not b:
        sys.exit(f"no turns found in {with_agon if not a else without}: use claude -p --output-format stream-json"
                 " --verbose, or codex exec --json")
    mean = [sum(column) / len(column) for column in zip(*a)], [sum(column) / len(column) for column in zip(*b)]
    return {"turns_with_agon": len(a), "turns_without": len(b), "input_with_agon": round(mean[0][0]),
            "input_without": round(mean[1][0]), "agon_adds_input": round(mean[0][0] - mean[1][0]),
            "cached_with_agon": round(mean[0][1]), "output_with_agon": round(mean[0][2])}


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "idle"
    if what == "idle":
        print(json.dumps(measure_idle(float(sys.argv[2]) if len(sys.argv) > 2 else 60), indent=2))
    elif what == "tokens" and len(sys.argv) == 4:
        print(json.dumps(measure_tokens(sys.argv[2], sys.argv[3]), indent=2))
    else:
        sys.exit(__doc__)
