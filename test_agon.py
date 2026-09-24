"""Self-check: python test_agon.py  (runs three fake agents against a temporary database)"""
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

TMP = tempfile.mkdtemp()
HERE = Path(__file__).resolve().parent
SERVER = str(HERE / "agon.py")
os.environ["AGON_DB"] = str(Path(TMP, "test.db"))
import agon  # noqa: E402  (reads AGON_DB on import, so it comes after the line above)


def agent(name):
    p = subprocess.Popen([sys.executable, SERVER, name], stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    def rpc(method, params):
        p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode() + b"\n")
        p.stdin.flush()
        return json.loads(p.stdout.readline())

    assert rpc("initialize", {"protocolVersion": "2025-06-18"})["result"]["serverInfo"]["name"] == "agon"
    return lambda tool, **a: rpc("tools/call", {"name": tool, "arguments": a})["result"]["content"][0]["text"]


claude, gemini, gpt = agent("claude"), agent("gemini"), agent("gpt")
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
print("ok")
