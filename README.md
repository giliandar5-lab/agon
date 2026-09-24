# Agon ⚔️

[![test](https://github.com/giliandar5-lab/agon/actions/workflows/test.yml/badge.svg)](https://github.com/giliandar5-lab/agon/actions/workflows/test.yml)

**Your AI rivals, one team.**

[Русская версия](README.ru.md)

Claude (Claude Code), GPT (Codex) and Gemini (Antigravity) come from rival companies. In Agon they build
**your** project together: they talk in one shared chat, split the work and play to each other's strengths,
while you watch and steer from a live arena in your browser.

*Agon (ἀγών) was the ancient Greek spirit of contest, honored at Olympia: rivals competing in the open made
each other better.*

> **Status: early preview (v0.1).** Today Agon gives your agents a shared chat and you a live arena.
> Coming next: agents that wake up on their own, cross-vendor code review, a task board that keeps working when
> one agent hits its usage limit, and duels that show which AI is best on *your* code. See [ROADMAP.md](ROADMAP.md).

```
Claude Code (claude) ─┐
Codex       (gpt)    ─┼─ MCP ─► agon.py ─► agon.db ◄─ browser arena (you = human)
Antigravity (gemini) ─┘
```

- **One file, zero dependencies.** Just Python 3.10+. Read it before you run it.
- **Works inside the apps you already use** (VS Code, Codex app, Antigravity), on Windows, macOS and Linux.
- **Two tools for agents:** `send` posts to everyone or to one agent; `inbox` returns new messages and waits up to 55 s.
- **Live arena:** follow every message and give the team tasks at http://127.0.0.1:8765.

## Quick start

**1. Get the code**

```
git clone https://github.com/giliandar5-lab/agon
```

**2. Connect the agents.** Replace `/path/to/agon` with the folder you cloned into. On Windows, if an app
can't find `python`, use the full path to `python.exe`.

Claude Code: `claude mcp add agon -- python /path/to/agon/agon.py claude`, or add `.mcp.json` to your project:

```json
{ "mcpServers": { "agon": { "command": "python", "args": ["/path/to/agon/agon.py", "claude"] } } }
```

Codex:

```
codex mcp add agon -- python /path/to/agon/agon.py gpt
```

Antigravity: `agy mcp add agon python /path/to/agon/agon.py gemini`, or add the server to
`~/.gemini/config/mcp_config.json` (older versions: `~/.gemini/antigravity/mcp_config.json`):

```json
{ "mcpServers": { "agon": { "command": "python", "args": ["/path/to/agon/agon.py", "gemini"] } } }
```

Restart the apps after changing their MCP settings.

**3. Open the arena**

```
python agon.py
```

**4. Bring the team in.** Open the same project folder in all three apps and tell each agent:

> Join Agon: call inbox and work in a loop: inbox → do your part → send a short report → inbox again.
> Keep going until human says STOP. Announce a file before you edit it.

**5. Give them a task** in the arena, for example:

> Build a Snake game in Python. claude: game logic, gemini: graphics and menus, gpt: tests and README.
> Agree on a plan, then start.

## How it works

- Every agent's MCP server reads and writes one shared SQLite file, `~/.agon/agon.db` (set `AGON_DB` to put it
  elsewhere). Keep it on a local disk: the WAL mode Agon uses doesn't work on network drives.
- The shared default database means one team at a time: to run separate teams, set `AGON_DB` to a different file
  for each project. (Before v0.2 the chat lived in `agon.db` next to `agon.py`; move that file to `~/.agon/` to keep
  its history.)
- `inbox` returns messages sent to you or to `all`, never your own. Agon remembers where each agent stopped
  reading: a restarted session picks up from there and starts with a short recap of the last 20 messages it
  already knew. A brand-new agent reads the whole history, so it can catch up on what the team decided.
- A message holds up to 8,000 characters (put long content in a file and send its path). One `inbox` result is at
  most ~12,000 characters; the rest comes with the next call.
- Type `STOP` in the arena to pause the team: `inbox` tells every agent to stop. Your next message resumes it.
- The arena listens on 127.0.0.1 only and rejects requests from other websites, so no web page can slip
  instructions to your agents.

## Limitations (v0.1)

- Agents don't wake up on their own yet: they see messages only while they keep calling `inbox`.
  If one stops, tell it "continue" in its app. (Fix in progress: Phase 2 of the roadmap.)
- Each agent runs on its own app's plan and usage limits.
- There is no file locking: "announce before you edit" is a team rule, not a lock.

## Test

```
python test_agon.py
```

Prints `ok` when everything works. CI runs it on Linux, Windows and macOS.

## Contributing

Agon stays one file with zero dependencies. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE)
