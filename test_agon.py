"""Self-check: python test_agon.py  (runs three fake agents against a temporary database)"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ["AGON_DB"] = str(Path(tempfile.mkdtemp()) / "test.db")
SERVER = str(Path(__file__).with_name("agon.py"))


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
print("ok")
