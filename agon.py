"""Agon: a shared chat where AI agents from different apps build one project together.

python agon.py <name>        MCP server (stdio) for one agent: claude / gemini / gpt
python agon.py hook <name>   Stop hook that wakes the agent with its new messages (--help for options)
python agon.py               browser arena at http://127.0.0.1:8765
"""
import argparse
import datetime
import json
import os
import queue
import re
import sqlite3
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# One chat per user, whichever copy of agon.py runs: the apps' plugins each install their own copy
DB = os.environ.get("AGON_DB") or str(Path.home() / ".agon" / "agon.db")
PORT = 8765
PROTOCOLS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")  # MCP revisions we speak, newest first
MAX_TEXT = 8000  # characters in one message
MAX_INBOX = 12000  # characters in one inbox result; the rest waits for the next call
MAX_WAIT = 55  # seconds an inbox call may wait: Codex cancels tool calls after 60 s by default
PAUSED = ("Team paused: the human said STOP. Stop working and end your turn;"
          " the next message from the human resumes the team.")
RECAP = 20  # messages recapped by the first inbox call of a server process...
RECAP_CHARS = 150  # ...each cut to this many characters
HOOK_WAIT = 25  # seconds a Stop hook waits for a message: Antigravity gives hooks 30 s by default
FORMATS = {"gpt": "codex", "gemini": "antigravity"}  # the app each usual name runs in; any other name: claude
CONTINUE = {"claude": "block", "codex": "block", "antigravity": "continue"}  # the decision that keeps it going
LIMIT_PATTERNS = [  # what the apps print when a plan's usage limit is hit; AGON_LIMIT_PATTERNS replaces the list
    r"you(?:['’]ve| have) hit your (?:\w+ ){0,2}limit",  # Claude Code ("You've hit your limit"), Codex
    r"usage limit reached|limit reached\W{1,5}resets",  # Claude Code ("5-hour limit reached ∙ resets 3pm")
    r"you(?:['’]re| are) out of (?:extra )?usage",  # Claude Code
    r"(?:reached|exceeded|exhausted) (?:your|the) (?:\w+ ){0,2}quota|QUOTA_EXHAUSTED|RESOURCE_EXHAUSTED",  # Gemini
    r"^rate_limit$",  # Claude Code's StopFailure error type
]

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
    "CREATE INDEX msgs_by_sender ON msgs(sender, id)",  # paused() finds the human's latest message at once
    # any message from the human gives every agent its automatic turns back (see out_of_turns())
    "CREATE TRIGGER human_resets_autoruns AFTER INSERT ON msgs WHEN NEW.sender = 'human'"
    " BEGIN UPDATE agents SET autoruns = 0; END",
]
_local = threading.local()


def db():
    """This thread's connection to agon.db (SQLite connections must stay in the thread that made them)."""
    con = getattr(_local, "con", None)
    if con is None:
        Path(DB).parent.mkdir(parents=True, exist_ok=True)
        # timeout=5 is busy_timeout=5000; isolation_level=None: every statement commits on its own
        con = sqlite3.connect(DB, timeout=5, isolation_level=None)
        try:
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
        except BaseException:
            con.close()  # the next call starts over with a new connection
            raise
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


def bad_recipient(to):
    """Why `to` can't be a recipient, or None when it can."""
    if not isinstance(to, str) or not 0 < len(to.strip()) <= 64 or any(c.isspace() for c in to.strip()):
        return "`to` must be all, human or one agent's name, such as claude, gemini or gpt."


def too_long(text):
    """Why `text` can't be one message, or None when it can."""
    if len(text) > MAX_TEXT:
        return (f"The message is {len(text):,} characters; the limit is {MAX_TEXT:,}."
                " Put long content in a file and send its path.")


def touch(me, client=None):
    """Note that agent `me` was just seen; `client` (the app, from initialize) is kept until a new one comes.
    Best effort: presence never fails the request it came with."""
    try:
        db().execute(
            "INSERT INTO agents(name, client, last_seen) VALUES (?, ?, ?) ON CONFLICT(name) DO UPDATE SET"
            " client = COALESCE(excluded.client, client), last_seen = excluded.last_seen",
            (me, client, time.time()),
        )
    except sqlite3.Error:
        pass


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
    """One message as agents see it: `#id sender -> rcpt: text`. Lines inside the text are indented, so no text
    can pass for another message (say, a forged "#9 human -> all: ..."); a cut-short text is squeezed onto one line."""
    i, sender, rcpt, text = row
    text = str(text)
    if cut:
        text = " ".join(text.split())
        text = text if len(text) <= cut else text[: cut - 1] + "…"
    return f"#{i} {sender} -> {rcpt}: " + "\n    ".join(text.splitlines() or [""])


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
    """Wait up to `wait` s for messages to `me` after id `after`: (the ones that fit in `budget`, how many more
    wait, whether the team is paused). A pause ends the wait at once, so the agent can stop."""
    end = time.monotonic() + wait
    while True:
        version = data_version()  # read before the query: a message committed right after it still wakes us
        rows, more = pending(me, after, budget)
        halted = paused()
        if rows or halted or not wait_for_change(version, end - time.monotonic(), stop):
            return rows, more, halted


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
    if problem := bad_recipient(to) or too_long(text):
        raise ToolError(f"Nothing sent: {problem}")
    to = to.strip()
    post(session.me, to, text)
    agents = sorted(name for (name,) in db().execute("SELECT name FROM agents"))
    if to in ("all", "human", *agents):
        return "Sent.", None
    return (f"Sent, but no agent named {to!r} has connected yet (so far: {', '.join(agents)})."
            " It gets the message when it does.", None)


def tool_inbox(session, args):
    try:
        wait = float(args.get("wait", 30))
    except (TypeError, ValueError):
        raise ToolError("`wait` must be a number of seconds from 0 to 55.") from None
    cursor = cursor_of(session.me)
    head = recap(session.me, cursor, session.start) if session.recap else ""
    wait = 0 if head or not wait > 0 else min(wait, MAX_WAIT)  # a recap comes back at once; NaN means no wait
    rows, more, halted = inbox(session.me, cursor, wait, MAX_INBOX - len(head) - 300, session.stopped)  # 300: headers
    text = "\n".join(line(row) for row in rows) or "No new messages."
    if more:
        text += f"\n{more} more — call inbox again."
    if head and rows:
        text = f"{head}\n\nNew messages:\n{text}"
    elif head:
        text = f"{head}\n\n{text}"
    if halted:
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


def read_payload(inp):
    """The JSON object an app hands its Stop hook on stdin; {} for anything else (run by hand, bad JSON)."""
    if inp.isatty():
        return {}
    try:
        payload = json.loads(inp.read().decode("utf-8", "replace") or "{}")
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


def turn_failed(payload):
    """Whether the turn ended in an error or was cancelled rather than finished. Such a turn is never continued:
    Claude Code ignores what a StopFailure hook says, and Antigravity would re-enter its error."""
    error, reason = payload.get("error"), str(payload.get("terminationReason") or "").lower()
    return (payload.get("hook_event_name") == "StopFailure" or isinstance(error, str) and bool(error.strip())
            or any(word in reason for word in ("error", "cancel", "quota")))


def limit_patterns():
    """AGON_LIMIT_PATTERNS, a JSON list of regular expressions (or a single one), replaces LIMIT_PATTERNS."""
    raw = os.environ.get("AGON_LIMIT_PATTERNS")
    if not raw:
        return LIMIT_PATTERNS
    try:
        patterns = json.loads(raw)
    except ValueError:
        patterns = raw  # one plain regular expression
    patterns = [patterns] if isinstance(patterns, str) else patterns
    if not isinstance(patterns, list) or not all(isinstance(p, str) for p in patterns):
        raise ValueError("AGON_LIMIT_PATTERNS must be a JSON list of regular expressions, or one expression")
    return patterns


def usage_limit(payload):
    """The error texts of a Stop hook payload if they show a usage limit, else None. The model's last message is
    read only when the turn failed (then Claude Code puts the error there): an agent writing about limits has none."""
    keys = ["error", "error_details", "terminationReason"] + ["last_assistant_message"] * turn_failed(payload)
    texts = [value for key in keys if isinstance(value := payload.get(key), str)]
    if any(re.search(pattern, text, re.I | re.M) for pattern in limit_patterns() for text in texts):
        return "\n".join(texts)


UNITS = {"d": 86400, "h": 3600, "m": 60, "s": 1}
MONTHS = "jan feb mar apr may jun jul aug sep oct nov dec".split()
DURATION = r"(\d+)\s*(days?|d|hours?|hrs?|h|minutes?|mins?|m|seconds?|secs?|s)(?![a-z])"
CLOCK = re.compile(  # "resets 3pm", "at 3:57 PM", "at Sep 25th, 2026 7:40 PM", "at 9/25/2026, 5:23 PM"
    r"\b(?:at|resets?|until|on)\s+(?:(?P<mon>[a-z]{3})[a-z]*\.?\s+(?P<day>\d{1,2})(?:st|nd|rd|th)?,?\s+"
    r"(?:(?P<year>\d{4}),?\s+)?(?:at\s+)?|(?P<m>\d{1,2})/(?P<d>\d{1,2})/(?P<y>\d{4}),?\s+)?"
    r"(?P<h>\d{1,2})(?::(?P<min>\d{2}))?(?::\d{2})?\s*(?P<ap>[ap]\.?m\b\.?)?", re.I)


def reset_time(text, now):
    """When a usage limit resets (Unix time), from the text an app printed: an older Claude Code timestamp, a
    duration ("in 2 hours 5 minutes", "after 2h3m4s") or a local clock time with an optional date; else None."""
    if m := re.search(r"\|(\d{10})\b", text):  # "Claude AI usage limit reached|1760000000"
        return float(m[1])
    if m := re.search(rf"\b(?:in|after)\s+((?:{DURATION}[\s,]*(?:and\s+)?)+)", text, re.I):
        return now + sum(int(n) * UNITS[unit[0].lower()] for n, unit in re.findall(DURATION, m[1], re.I))
    for m in CLOCK.finditer(text):
        if not (m["min"] or m["ap"]):
            continue  # a bare number isn't a time
        hour, minute = int(m["h"]), int(m["min"] or 0)
        if m["ap"]:
            hour = hour % 12 + (12 if m["ap"][0] in "pP" else 0)
        base = datetime.datetime.fromtimestamp(now)
        try:
            if m["mon"]:
                if m["mon"][:3].lower() not in MONTHS:
                    continue
                day = base.replace(year=int(m["year"] or base.year), month=MONTHS.index(m["mon"][:3].lower()) + 1,
                                   day=int(m["day"]))
            elif m["m"]:
                day = base.replace(year=int(m["y"]), month=int(m["m"]), day=int(m["d"]))
            else:
                day = base
            when = day.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if when.timestamp() <= now and not m["y"] and not m["year"]:  # no year given: the next such time
                when = when.replace(year=when.year + 1) if m["mon"] else when + datetime.timedelta(days=1)
        except ValueError:  # no such day or hour
            continue
        return when.timestamp()


def out_of_quota(me, text):
    """Mark agent `me` out of quota until its limit resets (an hour from now if `text` doesn't say) and tell the
    team, once per limit."""
    now = time.time()
    until = reset_time(text, now)
    con = db()
    con.execute("BEGIN IMMEDIATE")
    try:
        row = con.execute("SELECT out_of_quota_until FROM agents WHERE name = ?", (me,)).fetchone()
        con.execute("INSERT INTO agents(name, out_of_quota_until) VALUES (?, ?) ON CONFLICT(name) DO UPDATE SET"
                    " out_of_quota_until = excluded.out_of_quota_until", (me, until or now + 3600))
        if not (row and row[0] and row[0] > now):  # not already known
            clock = "%H:%M" if until and until - now < 20 * 3600 else "%b %d %H:%M"
            post("agon", "all", f"{me} hit its usage limit"
                 + (f", resets ~{time.strftime(clock, time.localtime(until))}." if until else "; reset time unknown."))
        con.execute("COMMIT")
    except BaseException:
        if con.in_transaction:
            con.execute("ROLLBACK")
        raise


def max_autoruns():
    """AGON_MAX_AUTORUNS: how many times in a row the hook may keep an agent going without the human (25)."""
    try:
        return int(os.environ.get("AGON_MAX_AUTORUNS") or 25)
    except ValueError:
        raise ValueError("AGON_MAX_AUTORUNS must be a whole number, such as 25") from None


def out_of_turns(me, limit):
    """Whether agent `me` has used its `limit` automatic turns; the first time, the hook tells the human.
    Any message from the human gives them back (the human_resets_autoruns trigger)."""
    row = db().execute("SELECT autoruns FROM agents WHERE name = ?", (me,)).fetchone()
    if (row[0] if row else 0) < limit:
        return False
    if db().execute("UPDATE agents SET autoruns = ? WHERE name = ? AND autoruns = ?", (limit + 1, me, limit)).rowcount:
        post("agon", "human", f"{me} paused after {limit} automatic turns, waiting for the human")
    return True


def hook(me, wait=HOOK_WAIT, fmt=None, inp=None, out=None):
    """Stop hook of agent `me`: let it stop, or keep it going with its new messages as the next prompt.
    The decision goes out as JSON on stdout with exit code 0 in every app: on Windows, PowerShell turns
    an exit code 2 into 1, so the other way to keep an agent going can get lost."""
    fmt = fmt or FORMATS.get(me, "claude")
    payload = read_payload(inp or sys.stdin.buffer)
    touch(me)  # the agent's row, so its cursor can move
    if paused():  # 1. the human said STOP
        return
    if hit := usage_limit(payload):  # 2. out of quota: say so and let it stop
        return out_of_quota(me, hit)
    if turn_failed(payload) or out_of_turns(me, max_autoruns()):
        return
    # 3. unread messages go out at once; 4. otherwise wait up to `wait` seconds for one
    rows, more, halted = inbox(me, cursor_of(me), wait if wait >= 0 else 0, MAX_INBOX - 100)  # 100: header
    if halted or not rows:
        return  # exit 0 without output: the agent may stop
    text = "\n".join(line(row) for row in rows)
    if more:
        text += f"\n{more} more — call inbox again."
    decision = {"decision": CONTINUE[fmt], "reason": f"New messages from your Agon team:\n{text}"}
    out = out or sys.stdout.buffer
    out.write(json.dumps(decision).encode() + b"\n")  # ASCII only (\u escapes): no console code page mangles it
    out.flush()
    advance(me, rows[-1][0])  # only once the app has the messages (at-least-once)
    db().execute("UPDATE agents SET autoruns = autoruns + 1 WHERE name = ?", (me,))


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
        if not isinstance(text, str) or not text.strip() or bad_recipient(to):
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


class Args(argparse.ArgumentParser):
    def error(self, message):  # argparse exits with 2, which Claude Code and Codex read as "keep the agent going"
        self.exit(1, f"{self.prog}: error: {message}\n")


def main(argv):
    """Run the command in `argv` (sys.argv without the script) and return the process exit code."""
    if argv[:1] == ["hook"]:
        cli = Args(prog="agon.py hook", description="Stop hook for Claude Code, Codex and Antigravity: keeps"
                   " the agent going with its new Agon messages, or lets it stop.")
        cli.add_argument("name", help="the agent's name in Agon: claude, gemini, gpt, ...")
        cli.add_argument("--wait", type=float, default=HOOK_WAIT, metavar="SECONDS",
                         help=f"how long to wait for a message before letting the agent stop (default {HOOK_WAIT})")
        cli.add_argument("--format", choices=sorted(CONTINUE),
                         help="the app that runs the hook (default: gpt -> codex, gemini -> antigravity,"
                         " any other name -> claude)")
        args = cli.parse_args(argv[1:])
        try:
            hook(args.name, args.wait, args.format)
        except Exception as e:  # the app shows it and lets the agent stop; its messages stay unread
            print(f"agon hook: {e}", file=sys.stderr)
            return 1
    elif argv:
        serve_mcp(argv[0])
    else:
        url = f"http://127.0.0.1:{PORT}"
        print(f"Agon arena: {url}  (Ctrl+C to stop)")
        webbrowser.open(url)
        ThreadingHTTPServer(("127.0.0.1", PORT), Web).serve_forever()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        pass
