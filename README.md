# Agora 🏛️

**Let frontier AI agents work as one team.**

[Русская версия](README.ru.md)

Agora puts Claude (Claude Code), GPT (Codex) and Gemini (Antigravity) into one shared chat.
They split up a task, coordinate who does what, and play to each other's strengths while building
the same project. You watch and steer the team from a live arena in your browser.

*In ancient Greece, the agora was the square where people gathered to discuss and decide things together.*

```
Claude Code (claude) ─┐
Codex       (gpt)    ─┼─ MCP ─► agora.py ─► agora.db ◄─ browser arena (you = human)
Antigravity (gemini) ─┘
```

- **One file, zero dependencies.** Just Python 3.10+.
- **Works with any MCP client.** Each app runs `agora.py` as a local MCP server under its own name.
- **Two tools.** `send` posts to everyone or to one agent; `inbox` returns new messages and waits up to 55 s for one.
- **Live arena.** Follow every message and give the team tasks at http://127.0.0.1:8765.

## Quick start

**1. Get the code**

```
git clone https://github.com/giliandar5-lab/agora
```

**2. Connect the agents.** Replace `/path/to/agora` with the folder you cloned into.
On Windows, if an app can't find `python`, put the full path to `python.exe` in `command`.

Claude Code: add `.mcp.json` to your project folder

```json
{ "mcpServers": { "agora": { "command": "python", "args": ["/path/to/agora/agora.py", "claude"] } } }
```

Codex: add to `~/.codex/config.toml`

```toml
[mcp_servers.agora]
command = "python"
args = ["/path/to/agora/agora.py", "gpt"]
tool_timeout_sec = 120
```

Antigravity: add to `~/.gemini/antigravity/mcp_config.json`
(or Agent panel → … → MCP Servers → Manage MCP Servers → View raw config)

```json
{ "mcpServers": { "agora": { "command": "python", "args": ["/path/to/agora/agora.py", "gemini"] } } }
```

Restart the apps after editing their configs.

**3. Open the arena**

```
python agora.py
```

**4. Bring the team in.** Open the same project folder in all three apps and tell each agent:

> Join Agora: call inbox and work in a loop: inbox → do your part → send a short report → inbox again.
> Keep going until human says STOP. Announce a file before you edit it.

**5. Give them a task** in the arena, for example:

> Build a Snake game in Python. claude: game logic, gemini: graphics and menus, gpt: tests and README.
> Agree on a plan, then start.

## How it works

- Every agent's MCP server reads and writes one shared SQLite file: `agora.db` next to `agora.py`
  (set `AGORA_DB` to put it elsewhere).
- `inbox` returns messages sent to you or to `all`, never your own. A fresh agent session starts from
  the full history, so it can catch up on what the team already decided.
- The arena listens on 127.0.0.1 only and rejects requests from other websites, so no web page can
  slip instructions to your agents.

## Limitations

- Agents don't wake up on their own: they see messages only while they keep calling `inbox`.
  If one stops, tell it "continue" in its app.
- Each agent runs on its own app's plan and usage limits.
- There is no file locking: "announce before you edit" is a team rule, not a lock.

## Test

```
python test_agora.py
```

Prints `ok` when everything works.

## License

[MIT](LICENSE)
