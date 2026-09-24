"""Self-check: python test_agon.py  (runs three fake agents against a temporary database)"""
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

TMP = tempfile.mkdtemp()
HERE = Path(__file__).resolve().parent
SERVER = str(HERE / "agon.py")
os.environ["AGON_DB"] = str(Path(TMP, "test.db"))
import agon  # noqa: E402  (reads AGON_DB on import, so it comes after the line above)


class Agent:
    """A fake MCP client (like Claude Code or Codex) talking to `python agon.py <name>` over stdio."""

    def __init__(self, name, client="fake-client", version="2025-06-18"):
        self.p = subprocess.Popen([sys.executable, SERVER, name], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        info = {"name": client, "version": "1.0"}
        self.hello = self.rpc("initialize", {"protocolVersion": version, "clientInfo": info})["result"]
        assert self.hello["serverInfo"]["name"] == "agon"

    def write(self, msg):  # a JSON-RPC message, or raw bytes to test bad input
        self.p.stdin.write(msg if isinstance(msg, bytes) else json.dumps(msg).encode() + b"\n")
        self.p.stdin.flush()

    def read(self):
        return json.loads(self.p.stdout.readline())

    def rpc(self, method, params=None, id=1):
        self.write({"jsonrpc": "2.0", "id": id, "method": method} | ({} if params is None else {"params": params}))
        return self.read()

    def call(self, tool, **args):  # the whole tools/call result
        return self.rpc("tools/call", {"name": tool, "arguments": args})["result"]

    def __call__(self, tool, **args):  # just its text
        return self.call(tool, **args)["content"][0]["text"]

    def close(self):
        self.p.stdin.close()
        self.p.wait(10)
        self.p.stdout.close()


claude, gemini, gpt = Agent("claude"), Agent("gemini"), Agent("gpt")
claude("send", text="hi team 👋")
claude("send", text="secret for gpt", to="gpt")

g = gemini("inbox", wait=0)
assert "hi team 👋" in g and "secret" not in g, g  # sees broadcasts, not other agents' DMs
assert gemini("inbox", wait=0) == "No new messages."  # cursor moved on
assert "secret for gpt" in gpt("inbox", wait=0)
assert claude("inbox", wait=0) == "No new messages."  # own messages never come back

# 1. Storage: WAL, busy timeout, synchronous=NORMAL
con = agon.db()
assert con.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
assert con.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
assert con.execute("PRAGMA synchronous").fetchone()[0] == 1  # NORMAL

# 2. One connection per thread
assert agon.db() is con  # the same thread reuses its connection
seen = []
t = threading.Thread(target=lambda: (seen.append(id(agon.db())), agon.close_db()))
t.start()
t.join()
assert seen and seen[0] != id(con)  # another thread gets its own

# 4. agents table; schema steps are counted in PRAGMA user_version
cols = [row[1] for row in con.execute("PRAGMA table_info(agents)")]
assert cols == ["name", "client", "cursor", "last_seen", "autoruns", "out_of_quota_until"], cols
assert con.execute("PRAGMA user_version").fetchone()[0] == len(agon.SCHEMA)
old = sqlite3.connect(Path(TMP, "v01.db"), isolation_level=None)  # a database made by agon v0.1
old.execute("CREATE TABLE msgs(id INTEGER PRIMARY KEY, sender TEXT, rcpt TEXT, text TEXT, ts TEXT)")
old.execute("INSERT INTO msgs(sender, rcpt, text) VALUES ('human', 'all', 'kept')")
agon.migrate(old)
assert old.execute("SELECT text FROM msgs").fetchall() == [("kept",)]
assert old.execute("SELECT COUNT(*) FROM agents").fetchone()[0] == 0
assert old.execute("PRAGMA user_version").fetchone()[0] == len(agon.SCHEMA)
old.close()
fresh = dict(os.environ, AGON_DB=str(Path(TMP, "fresh.db")))  # several agents create one database at once
starts = [subprocess.Popen([sys.executable, "-c", "import agon; agon.db()"], cwd=HERE, env=fresh) for _ in range(4)]
assert [p.wait() for p in starts] == [0, 0, 0, 0]
holder = sqlite3.connect(Path(TMP, "held.db"), isolation_level=None, check_same_thread=False)
holder.execute("BEGIN IMMEDIATE")  # another agent is still creating the new file: the WAL switch must wait
release = threading.Timer(0.5, holder.rollback)
release.start()
held = dict(os.environ, AGON_DB=str(Path(TMP, "held.db")))
assert subprocess.run([sys.executable, "-c", "import agon; agon.db()"], cwd=HERE, env=held).returncode == 0
release.join()
holder.close()

# 3. wait_for_change(): wakes up when another connection commits, otherwise times out
v = agon.data_version()
t0 = time.monotonic()
assert not agon.wait_for_change(v, 0.3) and time.monotonic() - t0 >= 0.25
posted = []
threading.Timer(0.3, lambda: (posted.append(time.monotonic()), agon.post("test", "nobody", "wake up"), agon.close_db())).start()
assert agon.wait_for_change(v, 10) and time.monotonic() - posted[0] < 1
got = []  # an agent waiting in inbox gets a new message right away
t = threading.Thread(target=lambda: got.append(gemini("inbox", wait=20)))
t.start()
time.sleep(0.5)
t0 = time.monotonic()
agon.post("test", "gemini", "are you there?")
t.join(10)
assert got and "are you there?" in got[0] and time.monotonic() - t0 < 2, got

# 15. Writes to stdout go through one lock
buf = io.BytesIO()
with agon.OUT_LOCK:
    t = threading.Thread(target=agon.emit, args=(buf, {"n": 1}))
    t.start()
    t.join(0.3)
    assert t.is_alive() and buf.getvalue() == b""  # waits while another thread holds the lock
t.join()
assert buf.getvalue() == b'{"n": 1}\n'
buf = io.BytesIO()  # the server writes to any binary stream, so it can run in-process too
agon.serve_mcp("ivan", io.BytesIO(b'{"jsonrpc": "2.0", "id": 1, "method": "ping"}\n'), buf)
assert json.loads(buf.getvalue()) == {"jsonrpc": "2.0", "id": 1, "result": {}}

# 12. Version negotiation: echo a supported revision, otherwise answer with the newest
assert agon.PROTOCOLS == ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
vera = Agent("vera")
for version in agon.PROTOCOLS:
    assert vera.rpc("initialize", {"protocolVersion": version})["result"]["protocolVersion"] == version
for version in ("2026-07-28", "1999-01-01", 5, None):  # 2026-07-28 is stateless: we keep speaking the older ones
    params = {} if version is None else {"protocolVersion": version}
    assert vera.rpc("initialize", params)["result"]["protocolVersion"] == "2025-11-25"
vera.close()

# 13. Error codes: parse error -32700 (id null), not a request -32600, unknown method -32601, bad params -32602
def code(reply):
    return reply["id"], reply["error"]["code"]


errol = Agent("errol")
errol.write(b"{not json\n")
assert code(errol.read()) == (None, -32700)
errol.write(b"[1, 2]\n")
assert code(errol.read()) == (None, -32600)
errol.write(b'{"jsonrpc": "2.0", "id": 3}\n')
assert code(errol.read()) == (3, -32600)
assert code(errol.rpc("tools/dance", id=4)) == (4, -32601)
assert code(errol.rpc("tools/call", {"name": "dance"}, id=5)) == (5, -32602)
assert code(errol.rpc("tools/call", {"name": "send", "arguments": ["hi"]}, id=6)) == (6, -32602)
assert code(errol.rpc("tools/call", ["send"], id=7)) == (7, -32602)
errol.write({"jsonrpc": "2.0", "method": "notifications/initialized"})  # notifications get no reply
errol.write({"jsonrpc": "2.0", "id": 99, "result": {}})  # neither do responses
assert errol.rpc("ping", id=8) == {"jsonrpc": "2.0", "id": 8, "result": {}}
errol.close()

# 14. Tool failures come back as results with isError = true and say what to fix
tess = Agent("tess")
for args in ({}, {"text": "  "}, {"text": 5}, {"text": "hi", "to": ["gpt"]}):
    res = tess.call("send", **args)
    assert res["isError"] is True and res["content"][0]["text"].startswith("Nothing sent: `"), res
res = tess.call("inbox", wait="soon")
assert res["isError"] is True and "`wait` must be a number" in res["content"][0]["text"], res
assert "isError" not in tess.call("inbox", wait="0")  # numbers as strings still work, as in v0.1
tess.close()


def locked(*args):
    raise sqlite3.OperationalError("database is locked")


agon.post, real_post = locked, agon.post  # a failure inside the tool itself
res = agon.call_tool(agon.Session("tess"), {"name": "send", "arguments": {"text": "hi"}})
agon.post = real_post
assert res["isError"] is True and "database is locked" in res["content"][0]["text"], res

# 16. Bad input never crashes the server: every bad line gets an error and the next request still works
bea = Agent("bea")
for line in (b"\xff\xfe\x00 not utf-8", b"[" * 100_000, b"1" * 5000, b"123", b'"text"', b"null", b"{}",
             b'{"jsonrpc": "2.0", "id": 4, "method": 5}', b'{"jsonrpc": "2.0", "id": 5, "method": "ping", "params": 1}',
             b'{"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": ["send"]}}',
             b'{"jsonrpc": "2.0", "id": 7, "method": "initialize", "params": {"clientInfo": 42}}'):
    bea.write(line + b"\n")
    reply = bea.read()
    assert "error" in reply or "protocolVersion" in reply.get("result", {}), (line[:40], reply)
assert bea.call("inbox", wait=[1])["isError"] is True
assert bea.rpc("ping", id=9) == {"jsonrpc": "2.0", "id": 9, "result": {}} and bea.p.poll() is None
bea.close()


class Gone(io.RawIOBase):  # a client that closed its end of the pipe
    def write(self, data):
        raise BrokenPipeError


agon.serve_mcp("gone", io.BytesIO(b'{"jsonrpc": "2.0", "id": 1, "method": "ping"}\n'), Gone())  # returns quietly


# 7. The app's name from initialize.clientInfo is stored per agent
def agent_row(name, column):
    return con.execute(f"SELECT {column} FROM agents WHERE name = ?", (name,)).fetchone()[0]


cody = Agent("cody", client="claude-code")
assert agent_row("cody", "client") == "claude-code"
cody.rpc("initialize", {"protocolVersion": "2025-06-18"})  # no clientInfo: keep what we know
assert agent_row("cody", "client") == "claude-code"
cody.rpc("initialize", {"protocolVersion": "2025-06-18", "clientInfo": {"name": "codex-mcp-client"}})
assert agent_row("cody", "client") == "codex-mcp-client"

# 6. Presence: every request moves last_seen (Unix time)
before = agent_row("cody", "last_seen")
assert abs(time.time() - before) < 60
time.sleep(0.1)
cody.rpc("tools/list")
assert agent_row("cody", "last_seen") > before
cody.close()
print("ok")
