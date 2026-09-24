"""Agon: a shared chat where AI agents from different apps build one project together.

python agon.py <name>   MCP server (stdio) for one agent: claude / gemini / gpt
python agon.py          browser arena at http://127.0.0.1:8765
"""
import json
import os
import queue
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
MAX_TEXT = 8000  # characters in one message
MAX_INBOX = 12000  # characters in one inbox result; the rest waits for the next call
MAX_WAIT = 55  # seconds an inbox call may wait: Codex cancels tool calls after 60 s by default
PAUSED = ("Team paused: the human said STOP. Stop working and end your turn;"
          " the next message from the human resumes the team.")
RECAP = 20  # messages recapped by the first inbox call of a server process...
RECAP_CHARS = 150  # ...each cut to this many characters

INSTRUCTIONS = """You are "{me}" in Agon: a shared chat where AI agents from different apps
(claude = Claude Code, gemini = Antigravity, gpt = Codex) and a human build ONE project together.
- inbox gets your new messages, send replies (to "all" or to claude / gemini / gpt / human).
- Loop: inbox -> do your part -> send a short report -> inbox again.
- When inbox says the team is paused (the human said STOP), stop working and end your turn.
- Announce a file before editing it, so two agents never edit the same file at once.
- Keep messages short and concrete; put long content in a file and send its path."""

TOOLS = [
    {
        "name": "send",
        "description": "Send a message to the Agon team chat (at most 8,000 characters:"
        " put long content in a file and send its path).",
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
        "description": "Get your new Agon messages. Waits up to `wait` seconds (max 55) for one to arrive."
        " A new session starts with a recap of earlier messages; a long backlog comes in parts;"
        " says when the human has paused the team.",
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
        if con.in_transaction:  # SQLite may have rolled back already
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


def paused():
    """True while the human's latest message is exactly STOP; any later message from the human resumes."""
    row = db().execute("SELECT text FROM msgs WHERE sender = 'human' ORDER BY id DESC LIMIT 1").fetchone()
    return bool(row) and isinstance(row[0], str) and row[0].strip() == "STOP"


def too_long(text):
    """Why `text` can't be one message, or None when it can."""
    if len(text) > MAX_TEXT:
        return (f"The message is {len(text):,} characters; the limit is {MAX_TEXT:,}."
                " Put long content in a file and send its path.")


def touch(me, client=None):
    """Note that agent `me` was just seen; `client` (the app, from initialize) is kept until a new one comes."""
    db().execute(
        "INSERT INTO agents(name, client, last_seen) VALUES (?, ?, ?) ON CONFLICT(name) DO UPDATE SET"
        " client = COALESCE(excluded.client, client), last_seen = excluded.last_seen",
        (me, client, time.time()),
    )


def data_version():
    """A number that changes whenever another connection commits to agon.db."""
    return db().execute("PRAGMA data_version").fetchone()[0]


def wait_for_change(since, timeout, stop=lambda: False):
    """True once another connection commits after data_version() returned `since`; False after `timeout` s,
    or as soon as stop() is true. One cheap PRAGMA every 0.2 s: near-zero CPU, at most 0.2 s latency."""
    end = time.monotonic() + timeout
    while data_version() == since:
        left = end - time.monotonic()
        if left <= 0 or stop():
            return False
        time.sleep(min(0.2, left))
    return True


def cursor_of(me):
    """Id of the last message delivered to `me`; 0 for a new agent, which then reads the whole history."""
    row = db().execute("SELECT cursor FROM agents WHERE name = ?", (me,)).fetchone()
    return row[0] if row else 0


def advance(me, last):
    """Move `me`'s cursor to message `last`, never back (two sessions of one agent may overlap)."""
    db().execute("UPDATE agents SET cursor = MAX(cursor, ?) WHERE name = ?", (last, me))


def newest_id():
    return db().execute("SELECT COALESCE(MAX(id), 0) FROM msgs").fetchone()[0]


def line(row, cut=None):
    """One message as agents see it: #id sender -> rcpt: text (squeezed onto one line when cut short)."""
    i, sender, rcpt, text = row
    if cut:
        text = " ".join(str(text).split())
        text = text if len(text) <= cut else text[: cut - 1] + "…"
    return f"#{i} {sender} -> {rcpt}: {text}"


def recap(me, cursor, start):
    """The last RECAP messages `me` knew before this server process started (message `start` was the newest):
    the ones delivered to it and its own. A restarted session reads them to remember what the team was doing."""
    rows = db().execute(
        "SELECT * FROM (SELECT id, sender, rcpt, text FROM msgs WHERE id <= ? AND (sender = ?"
        " OR (id <= ? AND rcpt IN ('all', ?))) ORDER BY id DESC LIMIT ?) ORDER BY id",
        (start, me, cursor, me, RECAP),
    ).fetchall()
    lines = [line(row, RECAP_CHARS) for row in rows]
    return "\n".join(["Recap of the messages before this session (already read):", *lines]) if lines else ""


FOR_ME = "FROM msgs WHERE id > ? AND sender != ? AND rcpt IN ('all', ?)"  # what `me` hasn't read after id ?


def pending(me, after, budget):
    """Messages for `me` after id `after` whose lines fit in `budget` characters (always at least one),
    and how many more are waiting."""
    rows, size = [], 0
    cur = db().execute(f"SELECT id, sender, rcpt, text {FOR_ME} ORDER BY id", (after, me, me))
    try:
        for row in cur:
            size += len(line(row)) + 1
            if rows and size > budget:
                break
            rows.append(row)
    finally:
        cur.close()
    more = db().execute(f"SELECT COUNT(*) {FOR_ME}", (rows[-1][0], me, me)).fetchone()[0] if rows else 0
    return rows, more


def inbox(me, after, wait, budget=MAX_INBOX, stop=lambda: False):
    """Wait up to `wait` s for messages to `me` after id `after`: (the ones that fit in `budget`, how many more)."""
    end = time.monotonic() + min(wait, MAX_WAIT)
    while True:
        version = data_version()  # read before the query: a message committed right after it still wakes us
        rows, more = pending(me, after, budget)
        if rows or paused() or not wait_for_change(version, end - time.monotonic(), stop):
            return rows, more  # paused: return at once so the agent can stop


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

    def __init__(self, me, out):
        self.me, self.out = me, out
        self.client = None  # the app, from initialize.clientInfo.name
        self.start = None  # the newest message id when this process got its first request: bounds the recap
        self.recap = True  # the first inbox call starts with a recap
        self.current = None  # id of the request being handled
        self.cancelled = set()  # ids of requests the client gave up on (notifications/cancelled)
        self.closed = False  # the client closed our stdin

    def stopped(self):
        """Nobody waits for the current request any more (cancelled, or the client left): stop waiting."""
        return self.closed or self.current in self.cancelled


def tool_send(session, args):
    text, to = args.get("text"), args.get("to", "all")
    if not isinstance(text, str) or not text.strip():
        raise ToolError("Nothing sent: `text` must be a non-empty string.")
    if not isinstance(to, str) or not to.strip():
        raise ToolError("Nothing sent: `to` must be all, human or an agent name such as claude, gemini or gpt.")
    if problem := too_long(text):
        raise ToolError(f"Nothing sent: {problem}")
    post(session.me, to.strip(), text)
    return "Sent.", None


def tool_inbox(session, args):
    try:
        wait = float(args.get("wait", 30))
    except (TypeError, ValueError):
        raise ToolError("`wait` must be a number of seconds from 0 to 55.") from None
    cursor = cursor_of(session.me)
    head = recap(session.me, cursor, session.start) if session.recap else ""
    wait = 0 if head or not wait > 0 else wait  # a recap comes back at once; NaN means no wait
    rows, more = inbox(session.me, cursor, wait, MAX_INBOX - len(head) - 300, session.stopped)  # 300: headers
    text = "\n".join(line(row) for row in rows) or "No new messages."
    if more:
        text += f"\n{more} more — call inbox again."
    if head and rows:
        text = f"{head}\n\nNew messages:\n{text}"
    elif head:
        text = f"{head}\n\n{text}"
    if paused():
        text = f"{PAUSED}\n\n{text}"

    def delivered():
        session.recap = False
        if rows:
            advance(session.me, rows[-1][0])

    return text, delivered


TOOL_HANDLERS = {"send": tool_send, "inbox": tool_inbox}  # each returns (text, what to run once it's delivered)


def handle(session, msg):
    """Answer one message from the client: (JSON-RPC reply or None, what to run once the reply is written)."""
    if not isinstance(msg, dict) or not isinstance(msg.get("method"), str):
        if isinstance(msg, dict) and ("result" in msg or "error" in msg):
            return None, None  # a response, but we never send requests
        rid = msg.get("id") if isinstance(msg, dict) else None
        return error(rid, -32600, "Invalid Request: expected a JSON-RPC 2.0 request object"), None
    if "id" not in msg:
        return None, None  # a notification (initialized, ...): never answered
    try:
        params = {} if msg.get("params") is None else msg["params"]
        if not isinstance(params, dict):
            raise RpcError(-32602, "Invalid params: `params` must be an object")
        touch(session.me)  # presence: every request moves last_seen
        if session.start is None:
            session.start = newest_id()
        result, after = dispatch(session, msg["method"], params)
        return {"jsonrpc": "2.0", "id": msg["id"], "result": result}, after
    except RpcError as e:
        return error(msg["id"], e.code, str(e)), None
    except Exception as e:
        return error(msg["id"], -32603, f"Internal error: {e}"), None


def dispatch(session, method, params):
    match method:
        case "initialize":
            info = params.get("clientInfo")
            name = info.get("name") if isinstance(info, dict) else None
            session.client = name if isinstance(name, str) else None
            touch(session.me, session.client)
            asked = params.get("protocolVersion")
            return {
                "protocolVersion": asked if asked in PROTOCOLS else PROTOCOLS[0],
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "agon", "version": "0.1"},
                "instructions": INSTRUCTIONS.format(me=session.me),
            }, None
        case "ping":
            return {}, None
        case "tools/list":
            return {"tools": TOOLS}, None
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
        text, after = tool(session, args)
        return {"content": [{"type": "text", "text": text}]}, after
    except ToolError as e:
        text = str(e)
    except Exception as e:  # e.g. agon.db stayed locked for 5 s: tell the agent, keep serving
        text = f"Agon failed: {e}. Try again in a moment."
    return {"content": [{"type": "text", "text": text}], "isError": True}, None


EOF = object()  # queued after the client's last message


def read_client(session, inp, todo):
    """Read the client's messages: queue requests for work() and handle at once what can't wait behind a long
    inbox call (cancellations, pings, unreadable lines). When the client closes stdin, mark the session closed."""
    try:
        for raw in inp:
            if not raw.strip():
                continue
            try:
                msg = json.loads(raw)
            except Exception:  # bad JSON or UTF-8, nesting too deep, a number too long...
                emit(session.out, error(None, -32700, "Parse error: send one JSON-RPC message per line"))
                continue
            method = msg.get("method") if isinstance(msg, dict) else None
            if method == "notifications/cancelled":
                params = msg.get("params")
                rid = params.get("requestId") if isinstance(params, dict) else None
                if isinstance(rid, (str, int)):
                    session.cancelled.add(rid)
            elif method == "ping" and "id" in msg:
                emit(session.out, {"jsonrpc": "2.0", "id": msg["id"], "result": {}})
            else:
                todo.put(msg)
    except (OSError, ValueError):  # the client closed the pipes (ValueError: I/O on a closed file)
        pass
    finally:
        session.closed = True
        todo.put(EOF)


def work(session, todo):
    """Answer the queued requests one by one, in order."""
    try:
        while (msg := todo.get()) is not EOF:
            rid = msg.get("id") if isinstance(msg, dict) else None
            session.current = rid if isinstance(rid, (str, int)) else None
            if session.current in session.cancelled:  # cancelled while it waited in the queue: don't run it
                session.cancelled.discard(session.current)
                continue
            reply, after = handle(session, msg)
            if session.current in session.cancelled:  # cancelled while it ran: no reply, messages stay unread
                session.cancelled.discard(session.current)
                continue
            if reply is not None:
                try:
                    emit(session.out, reply)
                except (OSError, ValueError):  # the client is gone: unread messages wait for its next session
                    return
            # Only now that the reply is out (at-least-once), and only if the client still reads: one that has
            # closed our stdin is shutting down and won't see this reply, so its messages stay unread.
            if after and not session.closed:
                try:
                    after()
                except Exception as e:  # the cursor stays put and the messages come again
                    print(f"agon: {e}", file=sys.stderr)
    finally:
        close_db()


def serve_mcp(me, inp=None, out=None):
    """MCP server for agent `me`: one JSON-RPC message per line on stdin and stdout. This thread reads and a
    worker answers, so a cancel or a closed pipe is noticed even while inbox waits."""
    session, todo = Session(me, out or sys.stdout.buffer), queue.Queue()
    worker = threading.Thread(target=work, args=(session, todo))
    worker.start()
    read_client(session, inp or sys.stdin.buffer, todo)
    worker.join()


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
  const r = await fetch('/msgs', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                                   body: JSON.stringify({ to: to.value, text: t.value }) });
  if (r.ok) t.value = ''; else alert(await r.text());
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
        try:
            msg = json.loads(self.rfile.read(max(0, min(int(self.headers["Content-Length"]), 1 << 20))))
            text, to = msg["text"], msg.get("to", "all")
        except Exception:
            text = to = None
        if not isinstance(text, str) or not text.strip() or not isinstance(to, str) or not to.strip():
            return self.answer(400, 'Send JSON like {"to": "all", "text": "..."}.')
        if problem := too_long(text):
            return self.answer(413, problem)
        post("human", to.strip(), text)
        self.send_response(204)
        self.end_headers()

    def answer(self, code, text):
        body = text.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

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
