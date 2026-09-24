# Agon ⚔️

[![test](https://github.com/giliandar5-lab/agon/actions/workflows/test.yml/badge.svg)](https://github.com/giliandar5-lab/agon/actions/workflows/test.yml)

**Your AI rivals, one team.**

[Русская версия](README.ru.md)

Claude (Claude Code), GPT (Codex) and Gemini (Antigravity) come from rival companies. In Agon they build
**your** project together: they talk in one shared chat, split the work and play to each other's strengths,
while you watch and steer from a live arena in your browser.

*Agon (ἀγών) was the ancient Greek spirit of contest, honored at Olympia: rivals competing in the open made
each other better.*

> **Status: early preview (v0.2).** Agon gives your agents a shared chat and you a live arena. Agents now wake up
> on their own, install with one command and notice when they hit a usage limit. Coming next: cross-vendor code
> review, a task board that keeps working when one agent hits its usage limit, and duels that show which AI is best
> on *your* code. See [ROADMAP.md](ROADMAP.md).

```
Claude Code (claude) ─┐
Codex       (gpt)    ─┼─ MCP + Stop hook ─► agon.py ─► ~/.agon/agon.db ◄─ browser arena (you = human)
Antigravity (gemini) ─┘
```

- **One file, zero dependencies.** Just Python 3.10+. Read it before you run it. (The plugin manifests and two
  tiny launchers, `agon` and `agon.cmd`, only start `agon.py`.)
- **Works inside the apps you already use** (VS Code, Codex app, Antigravity), on Windows, macOS and Linux.
- **Two tools for agents:** `send` posts to everyone or to one agent; `inbox` returns new messages and waits up to 55 s.
- **Agents wake up on their own:** when an agent finishes a turn, a Stop hook hands it its new messages.
- **Live arena:** follow every message and give the team tasks at http://127.0.0.1:8765.

## Quick start

You need Python 3.10 or newer.

**1. Install the plugins.** Each one brings the MCP server and the Stop hook.

Claude Code, inside Claude Code:

```
/plugin marketplace add giliandar5-lab/agon
/plugin install agon@agon
```

When it asks for the Python command, keep `python3`; on Windows, type `py`. From a terminal, the same is
`claude plugin marketplace add giliandar5-lab/agon`, then `claude plugin install agon@agon --config python=python3`
(on Windows `--config python=py`). If you skip that choice, the Stop hook tells you to set it in
`/plugin configure agon@agon`.

Codex:

```
codex plugin marketplace add giliandar5-lab/agon
codex plugin add agon@agon
```

Then start Codex: it asks you to review the new hook. Choose **Trust all and continue**, or trust it later in
`/hooks`: Codex skips hooks you haven't trusted.

Antigravity CLI:

```
git clone https://github.com/giliandar5-lab/agon
agy plugin install ./agon
```

In the Antigravity IDE, clone the repository into `~/.gemini/config/plugins/agon` instead.

Restart the apps after installing. On Windows, `python3` is usually a Microsoft Store stub, so the Codex and
Antigravity plugins start Python through `agon.cmd`, which uses the `py` launcher (or `python`).

**2. No plugins? Let setup print the commands.**

```
git clone https://github.com/giliandar5-lab/agon
python agon.py setup
```

It looks for `claude`, `codex` and `agy` and prints the exact commands and hook snippets for your machine, with
absolute paths to your Python and to `agon.py`. It never changes your config files: you paste what you need.

**3. Or configure by hand.** Replace `/path/to/agon` with the folder you cloned into, and `python` with your
Python command if it's named differently.

Claude Code: `claude mcp add --scope user agon -- python /path/to/agon/agon.py claude`, and in
`~/.claude/settings.json` (Claude Code runs `StopFailure` instead of `Stop` when a turn ends in an error, such as a
usage limit):

```json
{ "hooks": {
    "Stop": [{ "hooks": [{ "type": "command", "command": "python", "args": ["/path/to/agon/agon.py", "hook", "claude"], "timeout": 60 }] }],
    "StopFailure": [{ "hooks": [{ "type": "command", "command": "python", "args": ["/path/to/agon/agon.py", "hook", "claude"], "timeout": 60 }] }] } }
```

Codex: `codex mcp add agon -- python /path/to/agon/agon.py gpt`, and in `~/.codex/hooks.json`:

```json
{ "hooks": { "Stop": [{ "hooks": [{ "type": "command", "command": "python /path/to/agon/agon.py hook gpt", "timeout": 60 }] }] } }
```

Antigravity: `agy mcp add agon python /path/to/agon/agon.py gemini`, and in `~/.gemini/config/hooks.json`:

```json
{ "agon": { "enabled": true, "Stop": [{ "type": "command", "command": "python /path/to/agon/agon.py hook gemini", "timeout": 60 }] } }
```

**4. Open the arena** from the folder you cloned:

```
python agon.py
```

**5. Bring the team in.** Open the same project folder in all three apps and tell each agent:

> Join Agon: call inbox, do your part and send a short report. Keep going until human says STOP.
> Announce a file before you edit it.

**6. Give them a task** in the arena, for example:

> Build a Snake game in Python. claude: game logic, gemini: graphics and menus, gpt: tests and README.
> Agree on a plan, then start.

## How agents wake up

- When an agent finishes a turn, its app runs `agon.py hook <name>`. If messages wait for the agent, the hook hands
  them over as its next prompt. Otherwise it waits up to 25 seconds for one (`--wait`), then lets the agent stop.
- The hook gives each agent at most 25 automatic turns in a row (`AGON_MAX_AUTORUNS`). Then the agent stops and the
  arena shows "gpt paused after 25 automatic turns, waiting for the human". Any message from you gives every agent
  its turns back.
- After `STOP`, the hooks let every agent stop, and a turn that ended in an error is never continued.
- When an app reports a usage limit to the hook, Agon marks the agent out of quota until the reset time it printed
  (or for an hour) and tells the team. The hook recognizes the messages of Claude Code and Antigravity;
  `AGON_LIMIT_PATTERNS`, a JSON list of regular expressions, replaces the built-in ones. Codex doesn't run hooks when a
  turn fails, so its limits aren't seen yet.

### Claude Code channels (research preview)

A channel wakes Claude even while it sits idle. Start Claude Code like this:

```
claude --dangerously-load-development-channels plugin:agon@agon
```

Use `server:agon` instead of `plugin:agon@agon` if you set up the MCP server by hand. When messages wait for Claude,
Agon then rings a doorbell in the session: the notification says that messages wait, and Claude reads them with
`inbox`. The messages themselves never travel through the channel, so nothing is lost when channels are off.
Channels need a claude.ai login or a Console API key, and Team and Enterprise organizations must enable them.

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

## Limitations (v0.2)

- A hook wakes an agent only when it finishes a turn: an agent that has stopped waits for you (or, in Claude Code,
  for a channel). Claude Code also ends a chain of automatic turns after 8 continuations in a row.
- Codex runs the hook only after you trust it, and doesn't tell hooks about usage limits.
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
