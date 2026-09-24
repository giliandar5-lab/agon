"""Agon: a shared chat where AI agents from different apps build one project together.

python agon.py <name>   MCP server (stdio) for one agent: claude / gemini / gpt
python agon.py          browser arena at http://127.0.0.1:8765
"""
import json
import os
import sqlite3
import sys
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DB = os.environ.get("AGON_DB") or str(Path(__file__).with_name("agon.db"))
PORT = 8765

INSTRUCTIONS = """You are "{me}" in Agon: a shared chat where AI agents from different apps
(claude = Claude Code, gemini = Antigravity, gpt = Codex) and a human build ONE project together.
- inbox gets your new messages, send replies (to "all" or to claude / gemini / gpt / human).
- Loop: inbox -> do your part -> send a short report -> inbox again. Keep looping until human says STOP.
- Announce a file before editing it, so two agents never edit the same file at once.
- Keep messages short and concrete."""

TOOLS = [
    {
        "name": "send",
        "description": "Send a message to the Agon team chat.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "to": {"type": "string", "description": "all, claude, gemini, gpt or human", "default": "all"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "inbox",
        "description": "Get your new Agon messages. Waits up to `wait` seconds (max 55) for one to arrive.",
        "inputSchema": {"type": "object", "properties": {"wait": {"type": "integer", "default": 30}}},
    },
]


def db():
    con = sqlite3.connect(DB, timeout=10)
    con.execute(
        "CREATE TABLE IF NOT EXISTS msgs(id INTEGER PRIMARY KEY, sender TEXT, rcpt TEXT, text TEXT,"
        " ts TEXT DEFAULT (datetime('now', 'localtime')))"
    )
    return con


def post(sender, rcpt, text):
    with db() as con:
        con.execute("INSERT INTO msgs(sender, rcpt, text) VALUES (?, ?, ?)", (sender, rcpt, text))


def inbox(me, after, wait):
    deadline = time.time() + min(wait, 55)  # Codex cancels tool calls after 60 s by default
    while True:
        rows = db().execute(
            "SELECT id, sender, rcpt, text FROM msgs"
            " WHERE id > ? AND sender != ? AND rcpt IN ('all', ?) ORDER BY id LIMIT 50",
            (after, me, me),
        ).fetchall()
        if rows or time.time() >= deadline:
            return rows
        time.sleep(1)


def serve_mcp(me):
    last = 0  # in-memory cursor: a fresh agent session starts from the history and catches up
    for line in sys.stdin.buffer:
        if not line.strip():
            continue
        req = json.loads(line)
        if "id" not in req:  # notifications need no reply
            continue
        p = req.get("params") or {}
        args = p.get("arguments") or {}
        try:
            match req["method"], p.get("name"):
                case "initialize", _:
                    res = {
                        "protocolVersion": p.get("protocolVersion", "2025-06-18"),
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "agon", "version": "0.1"},
                        "instructions": INSTRUCTIONS.format(me=me),
                    }
                case "tools/list", _:
                    res = {"tools": TOOLS}
                case "tools/call", "send":
                    post(me, args.get("to", "all"), args["text"])
                    res = {"content": [{"type": "text", "text": "Sent."}]}
                case "tools/call", "inbox":
                    rows = inbox(me, last, int(args.get("wait", 30)))
                    if rows:
                        last = rows[-1][0]
                    text = "\n".join(f"#{i} {s} -> {r}: {t}" for i, s, r, t in rows) or "No new messages."
                    res = {"content": [{"type": "text", "text": text}]}
                case "ping", _:
                    res = {}
                case method, name:
                    raise ValueError(f"unknown: {method} {name or ''}")
            out = {"jsonrpc": "2.0", "id": req["id"], "result": res}
        except Exception as e:
            out = {"jsonrpc": "2.0", "id": req["id"], "error": {"code": -32603, "message": str(e)}}
        sys.stdout.buffer.write(json.dumps(out).encode() + b"\n")
        sys.stdout.buffer.flush()


PAGE = """<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Agon</title>
<style>
  body { margin: 0; font: 15px system-ui, sans-serif; background: #16161a; color: #ddd; }
  #log { padding: 16px 16px 90px; max-width: 900px; margin: auto; }
  .m { margin: 10px 0; padding: 10px 14px; border-radius: 10px; background: #222228; border-left: 4px solid #888; }
  .m b { margin-right: 8px; } .m i { color: #777; font-size: 12px; }
  .m pre { margin: 6px 0 0; white-space: pre-wrap; font: inherit; }
  .claude { border-color: #d97757; } .claude b { color: #d97757; }
  .gemini { border-color: #4f8ff7; } .gemini b { color: #4f8ff7; }
  .gpt { border-color: #10a37f; } .gpt b { color: #10a37f; }
  .human { border-color: #eee; background: #2b2b33; }
  form { position: fixed; bottom: 0; left: 0; right: 0; display: flex; gap: 8px; padding: 14px; background: #101013; }
  input, select, button { font: inherit; padding: 10px; border-radius: 8px; border: 1px solid #333; background: #222228; color: #eee; }
  input { flex: 1; min-width: 0; }
</style>
<div id="log"></div>
<form id="f">
  <select id="to"><option>all</option><option>claude</option><option>gemini</option><option>gpt</option></select>
  <input id="t" placeholder="Task or message for the team..." autofocus autocomplete="off">
  <button>Send</button>
</form>
<script>
let last = 0;
async function loop() {
  try {
    const rows = await (await fetch('/msgs?after=' + last)).json();
    for (const [id, sender, rcpt, text, ts] of rows) {
      last = id;
      const d = document.createElement('div');
      d.className = 'm ' + sender;
      d.innerHTML = '<b></b><i></i><pre></pre>';
      d.querySelector('b').textContent = sender + ' \\u2192 ' + rcpt;
      d.querySelector('i').textContent = ts;
      d.querySelector('pre').textContent = text;
      log.append(d);
    }
    if (rows.length) scrollTo(0, document.body.scrollHeight);
  } catch {}
  setTimeout(loop, 1000);
}
loop();
f.onsubmit = async e => {
  e.preventDefault();
  if (!t.value.trim()) return;
  await fetch('/msgs', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                         body: JSON.stringify({ to: to.value, text: t.value }) });
  t.value = '';
};
</script>"""


class Web(BaseHTTPRequestHandler):
    # Agents act on what the chat says, so other websites must never post to it:
    # the Host check stops DNS rebinding, and requiring JSON stops CSRF (plain forms can't send it).
    def local(self):
        if self.headers.get("Host") in (f"127.0.0.1:{PORT}", f"localhost:{PORT}"):
            return True
        self.send_error(403)

    def do_GET(self):
        if not self.local():
            return
        if self.path.startswith("/msgs"):
            after = int(self.path.partition("after=")[2] or 0)
            rows = db().execute(
                "SELECT id, sender, rcpt, text, ts FROM msgs WHERE id > ? ORDER BY id", (after,)
            ).fetchall()
            body, ctype = json.dumps(rows).encode(), "application/json"
        else:
            body, ctype = PAGE.encode(), "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if not self.local():
            return
        if self.headers.get("Content-Type") != "application/json":
            return self.send_error(415)
        msg = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        post("human", msg.get("to", "all"), msg["text"])
        self.send_response(204)
        self.end_headers()

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    if len(sys.argv) > 1:
        serve_mcp(sys.argv[1])
    else:
        url = f"http://127.0.0.1:{PORT}"
        print(f"Agon arena: {url}  (Ctrl+C to stop)")
        webbrowser.open(url)
        ThreadingHTTPServer(("127.0.0.1", PORT), Web).serve_forever()
