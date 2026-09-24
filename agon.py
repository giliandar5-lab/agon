"""Agon: a shared chat where AI agents from different apps build one project together.

python agon.py <name>   MCP server (stdio) for one agent: claude / gemini / gpt
python agon.py          browser arena at http://127.0.0.1:8765
"""
import json
import os
import sqlite3
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DB = os.environ.get("AGON_DB") or str(Path(__file__).with_name("agon.db"))
PORT = 8765
PROTOCOLS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")  # MCP revisions we speak, newest first

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


SCHEMA = [  # PRAGMA user_version counts the steps already applied: add new steps at the end, never edit old ones
    "CREATE TABLE IF NOT EXISTS msgs(id INTEGER PRIMARY KEY, sender TEXT, rcpt TEXT, text TEXT,"
    " ts TEXT DEFAULT (datetime('now', 'localtime')))",  # IF NOT EXISTS: v0.1 databases already have it
    "CREATE TABLE agents(name TEXT PRIMARY KEY, client TEXT, cursor INTEGER NOT NULL DEFAULT 0,"
    " last_seen REAL, autoruns INTEGER NOT NULL DEFAULT 0, out_of_quota_until REAL)",  # times: Unix seconds
]
_local = threading.local()


def db():
    """This thread's connection to agon.db (SQLite connections must stay in the thread that made them)."""
    con = getattr(_local, "con", None)
    if con is None:
        # timeout=5 is busy_timeout=5000; isolation_level=None: every statement commits on its own
        con = sqlite3.connect(DB, timeout=5, isolation_level=None)
        for tries in range(50):  # WAL: readers and the writer don't block each other
            try:
                con.execute("PRAGMA journal_mode=WAL")
                break
            except sqlite3.OperationalError:  # two agents switching a new file at once skip the busy timeout
                if tries == 49:
                    raise
                time.sleep(0.1)
        con.execute("PRAGMA synchronous=NORMAL")  # safe with WAL and much cheaper than FULL
        migrate(con)
        _local.con = con
    return con


def migrate(con):
    """Apply the SCHEMA steps this database doesn't have yet; safe when several agents start at once."""
    if con.execute("PRAGMA user_version").fetchone()[0] >= len(SCHEMA):
        return
    con.execute("BEGIN IMMEDIATE")  # one process migrates, the others wait for it and then skip
    try:
        done = con.execute("PRAGMA user_version").fetchone()[0]
        for step in SCHEMA[done:]:
            con.execute(step)
        if done < len(SCHEMA):  # a newer agon may have gone further: never lower the version
            con.execute(f"PRAGMA user_version = {len(SCHEMA)}")
        con.execute("COMMIT")
    except BaseException:
        con.execute("ROLLBACK")
        raise


def close_db():
    """Close this thread's connection, for threads that end (like the arena's request threads)."""
    con = getattr(_local, "con", None)
    if con is not None:
        _local.con = None
        con.close()


def post(sender, rcpt, text):
    db().execute("INSERT INTO msgs(sender, rcpt, text) VALUES (?, ?, ?)", (sender, rcpt, text))


def data_version():
    """A number that changes whenever another connection commits to agon.db."""
    return db().execute("PRAGMA data_version").fetchone()[0]


def wait_for_change(since, timeout):
    """True once another connection commits after data_version() returned `since`, False after `timeout` s.
    One cheap PRAGMA every 0.2 s: near-zero CPU, at most 0.2 s latency."""
    end = time.monotonic() + timeout
    while data_version() == since:
        left = end - time.monotonic()
        if left <= 0:
            return False
        time.sleep(min(0.2, left))
    return True


def inbox(me, after, wait):
    end = time.monotonic() + min(wait, 55)  # Codex cancels tool calls after 60 s by default
    while True:
        version = data_version()  # read before the query: a message committed right after it still wakes us
        rows = db().execute(
            "SELECT id, sender, rcpt, text FROM msgs"
            " WHERE id > ? AND sender != ? AND rcpt IN ('all', ?) ORDER BY id LIMIT 50",
            (after, me, me),
        ).fetchall()
        if rows or not wait_for_change(version, end - time.monotonic()):
            return rows


OUT_LOCK = threading.Lock()  # guards the only way to the client: see emit()


def emit(out, msg):
    """Write one JSON-RPC message as one line; the lock keeps lines from different threads whole."""
    data = json.dumps(msg).encode() + b"\n"
    with OUT_LOCK:
        out.write(data)
        out.flush()


class RpcError(Exception):
    """A request the server can't take: answered with a JSON-RPC error code."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class ToolError(Exception):
    """A tool call the agent can fix: answered as a result with isError, so the model sees why."""


def error(rid, code, message):
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}


class Session:
    """What one server process keeps about its agent outside the database."""

    def __init__(self, me):
        self.me = me
        self.last = 0  # in-memory cursor: a fresh agent session starts from the history and catches up


def tool_send(session, args):
    text, to = args.get("text"), args.get("to", "all")
    if not isinstance(text, str) or not text.strip():
        raise ToolError("Nothing sent: `text` must be a non-empty string.")
    if not isinstance(to, str) or not to.strip():
        raise ToolError("Nothing sent: `to` must be all, human or an agent name such as claude, gemini or gpt.")
    post(session.me, to.strip(), text)
    return "Sent."


def tool_inbox(session, args):
    try:
        wait = float(args.get("wait", 30))
    except (TypeError, ValueError):
        raise ToolError("`wait` must be a number of seconds from 0 to 55.") from None
    rows = inbox(session.me, session.last, wait if wait > 0 else 0)  # negative or NaN: no wait
    if rows:
        session.last = rows[-1][0]
    return "\n".join(f"#{i} {s} -> {r}: {t}" for i, s, r, t in rows) or "No new messages."


TOOL_HANDLERS = {"send": tool_send, "inbox": tool_inbox}  # schemas are in TOOLS


def handle(session, msg):
    """Answer one message from the client: a JSON-RPC reply, or None when none is due."""
    if not isinstance(msg, dict) or not isinstance(msg.get("method"), str):
        if isinstance(msg, dict) and ("result" in msg or "error" in msg):
            return None  # a response, but we never send requests
        rid = msg.get("id") if isinstance(msg, dict) else None
        return error(rid, -32600, "Invalid Request: expected a JSON-RPC 2.0 request object")
    if "id" not in msg:
        return None  # a notification (initialized, cancelled, ...): never answered
    try:
        params = {} if msg.get("params") is None else msg["params"]
        if not isinstance(params, dict):
            raise RpcError(-32602, "Invalid params: `params` must be an object")
        return {"jsonrpc": "2.0", "id": msg["id"], "result": dispatch(session, msg["method"], params)}
    except RpcError as e:
        return error(msg["id"], e.code, str(e))
    except Exception as e:
        return error(msg["id"], -32603, f"Internal error: {e}")


def dispatch(session, method, params):
    match method:
        case "initialize":
            asked = params.get("protocolVersion")
            return {
                "protocolVersion": asked if asked in PROTOCOLS else PROTOCOLS[0],
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "agon", "version": "0.1"},
                "instructions": INSTRUCTIONS.format(me=session.me),
            }
        case "ping":
            return {}
        case "tools/list":
            return {"tools": TOOLS}
        case "tools/call":
            return call_tool(session, params)
    raise RpcError(-32601, f"Method not found: {method}")


def call_tool(session, params):
    name, args = params.get("name"), params.get("arguments")
    tool = TOOL_HANDLERS.get(name) if isinstance(name, str) else None
    if tool is None:
        raise RpcError(-32602, f"Unknown tool: {name}. Tools: {', '.join(TOOL_HANDLERS)}")
    args = {} if args is None else args
    if not isinstance(args, dict):
        raise RpcError(-32602, "Invalid params: `arguments` must be an object")
    try:
        return {"content": [{"type": "text", "text": tool(session, args)}]}
    except ToolError as e:
        text = str(e)
    except Exception as e:  # e.g. agon.db stayed locked for 5 s: tell the agent, keep serving
        text = f"Agon failed: {e}. Try again in a moment."
    return {"content": [{"type": "text", "text": text}], "isError": True}


def serve_mcp(me, inp=None, out=None):
    """MCP server for agent `me`: one JSON-RPC message per line on stdin and stdout."""
    inp, out = inp or sys.stdin.buffer, out or sys.stdout.buffer
    session = Session(me)
    try:
        for line in inp:
            if not line.strip():
                continue
            try:
                msg = json.loads(line)
            except Exception:  # bad JSON or UTF-8, nesting too deep, a number too long...
                reply = error(None, -32700, "Parse error: send one JSON-RPC message per line")
            else:
                reply = handle(session, msg)
            if reply is not None:
                emit(out, reply)
    except (OSError, ValueError):  # the client closed the pipes (ValueError: write to a closed file)
        pass


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

    def handle(self):
        try:
            super().handle()
        finally:
            close_db()  # every request runs in a new thread with its own connection

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
    try:
        if len(sys.argv) > 1:
            serve_mcp(sys.argv[1])
        else:
            url = f"http://127.0.0.1:{PORT}"
            print(f"Agon arena: {url}  (Ctrl+C to stop)")
            webbrowser.open(url)
            ThreadingHTTPServer(("127.0.0.1", PORT), Web).serve_forever()
    except KeyboardInterrupt:
        pass
