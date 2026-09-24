# Agon roadmap

## Positioning

**Your AI rivals, one team.** Agon turns Claude (Claude Code), GPT (Codex) and Gemini (Antigravity) into one
team working on your project, and shows it live in an arena. Two pillars:

1. **AI team arena.** Agents coordinate on a shared board, review each other's work across vendors, and can
   duel on a task so you learn which AI is best on *your* code.
2. **No downtime from usage limits.** When one agent runs out of quota, its work moves to the others
   automatically and comes back after the reset.

Who it is for: people who already use two or more AI coding tools, including people who work in GUI apps
(VS Code, Codex app, Antigravity IDE) and on Windows, not only in tmux on macOS/Linux.

## Progress

Tick a phase in the same pull request that completes it.

- [x] Phase 1 — Solid core
- [x] Phase 2 — Agents wake up on their own, one-command install, limit awareness
- [ ] Phase 3 — Cross-vendor second opinion (`ask`)
- [ ] Phase 4 — Task board (no downtime)
- [ ] Phase 5 — The arena
- [ ] Phase 6 — Packaging

## How every session works

When asked to do "the next phase":

1. Take the **first phase in Progress that is not ticked**. Implement only that phase; later phases come in
   separate sessions.
2. Read this whole file (including "Working rules" and "Verified platform facts"), then README.md, agon.py and
   test_agon.py.
3. Turn every bullet of the phase into a numbered checklist. Show the checklist and a short plan to the user and
   wait for approval.
4. Work item by item: implement, add assert-based checks to test_agon.py, run `python test_agon.py`, commit.
   Never move on while tests fail.
5. If something is ambiguous, pick the simplest option that satisfies this roadmap and note it in the pull request.
6. Done means: every checklist item is implemented and covered by a test, `python test_agon.py` prints `ok`, the
   phase is ticked in Progress, and a pull request lists each item with how it was verified, what could not be
   verified, and step-by-step manual test instructions for Windows.
7. Reply in the language the user writes in.

## Design principles (and why)

| Principle | Evidence |
|---|---|
| One lead + a shared task board; parallelize only independent work | Multi-agent setups gain up to +80% on decomposable tasks and lose 39–70% on sequential ones; centralized coordination contains error amplification (×4.4 vs ×17.2) — [arXiv 2512.08296](https://arxiv.org/abs/2512.08296) |
| One writer per file; many agents may think, few may write | Parallel writers make conflicting implicit decisions — [Cognition](https://cognition.com/blog/multi-agents-working) |
| Coordinate through a structured board, not only chat | Blackboard beat direct messaging by 13–57% — [arXiv 2510.01285](https://arxiv.org/abs/2510.01285); structured artifacts reduce hallucination — [MetaGPT](https://arxiv.org/abs/2308.00352) |
| Every task gets verified; explicit stop conditions | Adding verification: +15.6 pp; top failures are repetition and not knowing when to stop — [MAST](https://arxiv.org/abs/2503.13657) |
| Reviews come from a different vendor and must include evidence (tests run) | LLM judges favor their own outputs — [arXiv 2404.13076](https://arxiv.org/abs/2404.13076); code judges stay biased without execution — [arXiv 2505.16222](https://arxiv.org/abs/2505.16222) |
| Measure per project; no hard-coded "model X is best at Y" | Winners change by task type — [Copilot Arena](https://arxiv.org/abs/2502.09328); mixing helps when models are close in quality — [Self-MoA](https://arxiv.org/abs/2502.00674) |
| Few, small tools; long outputs go to files | Multi-agent runs cost 3–10× tokens — [Anthropic](https://claude.com/blog/building-multi-agent-systems-when-and-how-to-use-them) |
| Shared folder for the team; git worktrees only for duels and background tasks | Worktrees move conflicts to merge time rather than removing them |
| One file, standard library only, honest numbers | Trust and zero-friction install matter more than feature count |

## Architecture (all in `agon.py`, Python 3.10+ standard library)

- **Storage:** SQLite in WAL mode (`busy_timeout=5000`, `synchronous=NORMAL`), one connection per thread, in
  `~/.agon/agon.db` (`AGON_DB`) so that every app's copy of `agon.py` shares it.
  Tables: `msgs`, `agents(name, client, cursor, last_seen, autoruns, out_of_quota_until)`, `tasks` (Phase 4).
- **Delivery:** per-agent cursor stored in the database; advance it only after the output is written
  (at-least-once). Waiting uses `PRAGMA data_version` every 0.2 s (near-zero CPU, ≤ 0.2 s latency).
- **Agent tools (max 4):** `send`, `inbox`, `ask` (Phase 3), `tasks` (Phase 4).
- **Wake-up layers:** Claude Code channels (a doorbell: the push only says that messages wait) → Stop hooks in all
  three apps (a JSON decision on stdout) → `inbox(wait)` → the human.
- **Security:** arena on 127.0.0.1 with Host and JSON checks; every message shows its author (`[HUMAN]` stands
  out); messages from agents are requests, never permissions; Agon never edits user config files; reviews are
  read-only by default.

## Phase 1 — Solid core

- WAL, connection per thread, `wait_for_change()`, `agents` table, persisted cursors, presence (`last_seen`),
  client name from `initialize.clientInfo`.
- The first `inbox` call of a server process includes a short recap of the last 20 messages before the cursor.
- Size limits: a message ≤ 8,000 characters (otherwise an error that says "put long content in a file and send
  its path"); one `inbox` result ≤ ~12,000 characters, the rest stays pending ("N more — call inbox again").
- Pause: a human message that is exactly `STOP` pauses the team (`inbox` reports the pause, hooks let agents
  stop); any later human message resumes.
- Protocol: supported versions `2025-11-25`, `2025-06-18`, `2025-03-26`, `2024-11-05` (echo the requested one if
  supported, otherwise answer with the newest); parse error → `-32700` (id null); unknown method → `-32601`;
  invalid params → `-32602`; tool failures → `result.isError = true` with a helpful message; stdout writes under
  a lock; the process never crashes on bad input.
- CI: `.github/workflows/test.yml` running `python test_agon.py` on ubuntu, windows and macos × Python 3.10 and 3.13.
- A short `CONTRIBUTING.md` (single file, zero dependencies, tests required, English).
- Tests: cursor survives a restart, recap, size limits, STOP/resume, error codes, version negotiation,
  `tools/list` payload under 2,500 characters.

## Phase 2 — Agents wake up on their own, one-command install, limit awareness

- `python agon.py hook <name> [--wait SECONDS] [--format claude|codex|antigravity]` for the Stop hook of each app.
  It reads the hook's JSON from stdin, then:
  1. team paused → allow the stop;
  2. the payload shows a usage limit (check fields such as `error`, `terminationReason`,
     `last_assistant_message` against `AGON_LIMIT_PATTERNS`, a configurable regex list) → mark the agent
     out of quota (parse the reset time if it is printed), post a short system message to the team, allow the stop;
  3. unread messages → deliver them as the continuation prompt and advance the cursor;
  4. otherwise wait up to `--wait` seconds (default 25) for a message, then allow the stop.
  Output per app: Claude Code and Codex → exit code 2 with the prompt on stderr; Antigravity → stdout
  `{"decision": "continue", "reason": "<prompt>"}`. The default format follows the name
  (claude → claude, gpt → codex, gemini → antigravity).
- Auto-turn budget: `AGON_MAX_AUTORUNS` (default 25) continuations per agent, reset by any human message; at the
  limit the hook allows the stop and posts "gpt paused after 25 automatic turns, waiting for the human".
- Claude Code channels: declare `capabilities.experimental["claude/channel"] = {}` in `initialize`; when the client
  is Claude Code, a daemon thread pushes new messages as `notifications/claude/channel` with
  `{"content": text, "meta": {"sender": ..., "msg_id": ...}}` (meta keys: letters, digits, underscores) and advances
  the cursor. Usage: `claude --dangerously-load-development-channels server:agon` (research preview).
- Plugins for one-command install (MCP server + Stop hook pre-wired): `.claude-plugin/` (with a marketplace
  entry so `/plugin marketplace add giliandar5-lab/agon` works), `.codex-plugin/` (`codex plugin marketplace add`
  + `codex plugin add`; Codex asks the user to trust hooks via `/hooks`), and an Antigravity plugin folder
  (`mcp_config.json` + `hooks.json` shaped as `{"agon": {"enabled": true, "Stop": [...]}}`).
- `python agon.py setup`: finds `claude`, `codex` and `agy` on PATH and **prints** the exact commands and hook
  snippets with absolute paths. It never writes config files.
- README: plugin install first, then `setup`, then manual config; how to use channels.
- Tests: hook output for each format, wait window, auto-turn budget, limit detection (agent marked + message
  posted), channel notifications only for Claude clients, `setup` output contains absolute paths.

## Phase 3 — Cross-vendor second opinion (`ask`)

- `ask(agent, prompt, mode="review" | "task")` runs another vendor's CLI headless and returns only its final answer.
- Command templates are configurable (`AGON_CMD_CLAUDE`, `AGON_CMD_GPT`, `AGON_CMD_GEMINI`); defaults:
  `claude -p --output-format json` (review adds `--permission-mode plan`), `codex exec --json` (review adds
  `--sandbox read-only`), `agy -p --output-format json` (review adds `--mode plan`). Pass the prompt on stdin
  where supported. Parse the final message from each format, falling back to the raw output tail.
- Review prompt template: run the tests, cite the output, end with `VERDICT: approve` or `VERDICT: changes`.
- Task mode runs in a temporary `git worktree` with write access and returns the summary, `git diff --stat` and
  the branch name; the caller decides whether to merge.
- Out of quota: if the target is marked out of quota or its output matches `AGON_LIMIT_PATTERNS`, mark it and
  try the next agent in `AGON_FALLBACK`; report who actually answered.
- Timeout (default 900 s) kills the whole process tree; a missing CLI gives a clear error; every call is
  logged to the chat (who asked whom, duration, verdict).
- Tests use fake CLI scripts through the same environment variables.

## Phase 4 — Task board (no downtime)

- `tasks(action, ...)`: `list | add(title, spec, files, after) | claim(id) | done(id, note) | review(id, verdict, evidence)`.
- Atomic claim (`BEGIN IMMEDIATE` + `UPDATE ... WHERE owner IS NULL`); overlapping files with another task in
  progress → rejected with the owner's name; a task with unfinished `after` dependencies can't be claimed.
- `done` → `review`: the reviewer must be a different agent (vendor); if nobody is online, the review runs
  automatically through `ask`. `changes` sends the task back to its owner.
- When an agent runs out of quota, its in-progress tasks go back to `todo` with a note ("reassigned: claude hit
  its usage limit, resets ~14:00"); after the reset the agent returns to rotation and gets a recap.
- Every state change posts a short system message so the hooks wake the right agent.
- The team playbook (lead, one writer per file, split by context boundaries, evidence-based reviews, don't reply
  to acknowledgments) goes into the server `instructions` and the README.
- Tests: claim race between two processes, file conflict, dependencies, author ≠ reviewer, reassignment on quota.

## Phase 5 — The arena

- Server-Sent Events (`/events`, resumes from `Last-Event-ID`, heartbeat every 15 s) and `/board` JSON.
- UI: chat, team roster with each agent's **fuel** (working / idle / out of quota + reset time), task board,
  STOP/RESUME, `ask` calls with verdicts. Everything inline, no external assets, works on a phone.
- **Duel:** the same task goes to two or three agents, each in its own worktree; run the test command
  (`AGON_TEST_CMD`), cross-review, the human picks the winner.
- **Scoreboard per project:** wins, tests passed, reviews accepted, and a hint about whom to give such tasks.
- **Export** a replay or a scorecard as one self-contained HTML file (explicit user action; warn that it may
  contain code).
- Terminal: `python agon.py watch` (live colored feed) and `python agon.py say [--to NAME] TEXT`.
- Tests: SSE resume, `/board` JSON, a duel with fake CLIs, scoreboard update, exported HTML has no external URLs.

## Phase 6 — Packaging

- PyPI package `agon-arena` with an `agon` command (`uvx agon-arena`), listings in plugin marketplaces and MCP
  directories, a demo video, and measured numbers (idle CPU and RAM, `tools/list` size, tokens per turn).

## Non-goals

A Rust/Go rewrite, Electron, third-party dependencies, dozens of tools, parallel-writer swarms by default,
editing users' config files, hard-coded model rankings, claims we can't measure.

## Working rules for every phase

- Check the current official docs for every CLI flag, hook schema and plugin manifest before relying on it;
  these tools change monthly. If the docs are unreachable from your environment, use the facts below and list
  in the pull request what you could not re-verify.
- `agon.py` stays one file with zero dependencies; existing tools stay backward compatible.
- Every new behavior gets an assert-based check in `test_agon.py`; `python test_agon.py` must print `ok`.
- The real apps (Claude Code, Codex, Antigravity) may not be available where you work: simulate them in tests
  (fake hook payloads, fake MCP clients, fake CLI scripts) and give manual test steps in the pull request.

## Verified platform facts (checked 2026-09-24)

Sources are official docs unless marked *(secondary)*. Re-check when you can; these change often.

**Claude Code — hooks** ([docs](https://code.claude.com/docs/en/hooks); tried with the CLI 2.1.281)
- Configured in `~/.claude/settings.json`, `.claude/settings.json` or a plugin (`hooks/hooks.json` or inline in
  `plugin.json`): `{"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "...", "timeout": 60}]}]}}`.
- Exec form (`"command": "<executable>", "args": [...]`) runs without a shell; on Windows the command must be a real
  `.exe`, and a bare name is looked up with `where.exe`, so `python3` finds the Microsoft Store stub. Shell form runs
  `sh -c`, Git Bash on Windows, or PowerShell when Git for Windows (optional) isn't installed.
- Stop stdin includes `session_id`, `transcript_path`, `cwd`, `hook_event_name`, `stop_hook_active`,
  `last_assistant_message`. To continue: exit 0 with stdout `{"decision": "block", "reason": "<prompt>"}` (what Agon
  does) or exit 2 with the prompt on stderr; the transcript calls either a hook error. After 8 blocks in a row
  Claude Code ends the turn anyway. Default timeout 600 s. Runs in the VS Code extension too.
- A turn that ends in an API error (rate or usage limit, server error, ...) runs `StopFailure` instead of `Stop`:
  stdin has `error` (`rate_limit`, ...), optional `error_details`, and the rendered error in
  `last_assistant_message`. Its output and exit code are ignored.
- Plugin hooks and MCP servers substitute `${CLAUDE_PLUGIN_ROOT}` and `${user_config.KEY}`. A userConfig `default`
  reaches MCP servers but not hooks: a hook using an option that was never set fails ("Plugin option ... isn't set")
  until the user sets it (`/plugin configure`, or `claude plugin install <plugin> --config KEY=VALUE`).

**Claude Code — channels** ([docs](https://code.claude.com/docs/en/channels-reference))
- Declare `capabilities.experimental["claude/channel"] = {}`; send `notifications/claude/channel` with
  `params: {"content": "...", "meta": {"key": "value"}}`. Meta keys must be letters, digits and underscores
  (others are dropped silently). The server `instructions` string is shown to Claude on connect.
- Custom channels need `claude --dangerously-load-development-channels server:<name>` (or `plugin:<plugin>@<market>`)
  during the research preview (CLI only). A channel does not register if protocol revision `2026-07-28` is
  negotiated, nor without the flag, on other providers, or when an organization hasn't enabled channels.
- Claude Code drops the events of an unregistered channel silently and never acknowledges them, and a server can't
  tell (the client's `initialize` carries no channel capability): don't mark anything delivered by a push.

**Claude Code — headless and plugins**
- `claude -p "<prompt>" --output-format json` (final text in `result`), `--resume <session_id>`,
  `--permission-mode plan | acceptEdits`. `clientInfo.name` is `claude-code`; MCP servers inherit Claude Code's
  environment plus `CLAUDECODE=1` and `CLAUDE_PROJECT_DIR`.
- Plugins: manifest `.claude-plugin/plugin.json`, which may declare `mcpServers`, `hooks`, `userConfig` and
  `channels` inline; a `.claude-plugin/marketplace.json` entry with `"source": "./"` makes the repository root the
  plugin; users run `/plugin marketplace add owner/repo` and `/plugin install <plugin>@<marketplace>`
  ([docs](https://code.claude.com/docs/en/plugin-marketplaces)); `claude plugin validate --strict` checks both
  files. Marketplace installs are copied to `~/.claude/plugins/cache/`, which changes with each version: keep no
  state there.

**Codex — hooks** ([docs](https://learn.chatgpt.com/docs/hooks), moved from developers.openai.com; tried with the CLI
0.156.1 against a mock model)
- `~/.codex/hooks.json`, `<project>/.codex/hooks.json`, `[hooks]` in `config.toml`, or a plugin. Every non-managed
  hook, plugin hooks included, must be trusted by the user: the TUI asks at startup, `/hooks` manages them,
  `codex exec` skips untrusted hooks silently, `--dangerously-bypass-hook-trust` skips the check for one run.
- Handler fields: `command`, `commandWindows` (a Windows override), `timeout`, `statusMessage`; no args or exec
  form. Commands run in the user's shell with `-c` and the session's cwd; on Windows in PowerShell
  (`-NoProfile -Command`, read from source).
- Stop stdin includes `session_id`, `turn_id`, `transcript_path`, `cwd`, `hook_event_name`, `model`,
  `stop_hook_active`, `last_assistant_message`. To continue: stdout `{"decision": "block", "reason": "<prompt>"}`
  (any key beyond `continue`, `stopReason`, `suppressOutput`, `systemMessage`, `decision`, `reason` fails the hook)
  or exit 2 with the prompt on stderr. Exit 0 without output ends the turn. No cap on continuations (224 in 20 s).
  Default timeout 600 s.
- Stop doesn't run when a turn fails, a usage limit included, and no hook event reports errors. The limit reads
  "You’ve hit your usage limit. ... try again at 3:57 PM." (curly apostrophe; on another day "Try again at Sep 25th,
  2026 7:40 PM.").

**Codex — headless, MCP and plugins**
- `codex exec --json "<prompt>"` streams JSONL events (`thread.started` carries the session id, `item.*`,
  `turn.completed`, `error`); continue with `codex exec resume <SESSION_ID> --json "<prompt>"`.
  `--full-auto` was removed in 0.147.0 (use explicit `--sandbox read-only | workspace-write`);
  `codex mcp-server` was removed in 0.154.0. `codex mcp add <name> [--env K=V] -- <command> [args]` adds an MCP
  server. *(secondary)*
- MCP: `clientInfo.name` is `codex-mcp-client`. Servers get only a whitelist of environment variables (HOME,
  PATH, ...; on Windows USERPROFILE, APPDATA, ...) plus `env` and `env_vars`. A tool without annotations needs an
  approval on every call (and fails under `codex exec`); `readOnlyHint`, or `destructiveHint: false` with
  `openWorldHint: false`, runs it without asking. Tool timeout: 60 s in the docs (300 s in the source). On Windows
  a command is resolved with PATHEXT relative to the server's `cwd`, so `./agon` finds `agon.cmd`.
- Plugins: `.codex-plugin/plugin.json` (a legacy-compatible manifest; the portable one is a root `plugin.json`
  with the Agent Plugins `$schema`). Inline `mcpServers` and `hooks` (`{"hooks": {...}}`) replace the default
  `.mcp.json` and `hooks/hooks.json`. MCP configs expand nothing (a relative `cwd` joins the plugin root); hook
  commands get `${PLUGIN_ROOT}` substituted and `PLUGIN_ROOT` and `CLAUDE_PLUGIN_ROOT` exported. Without
  `.agents/plugins/marketplace.json`, Codex reads `.claude-plugin/marketplace.json`. Install:
  `codex plugin marketplace add owner/repo` (a git clone), then `codex plugin add <plugin>@<marketplace>`, which
  copies the plugin, executable bits included, to `~/.codex/plugins/cache/`.

**Antigravity (IDE and `agy` CLI)** ([hooks](https://antigravity.google/docs/hooks),
[plugins](https://antigravity.google/docs/plugins), [headless](https://antigravity.google/docs/cli/headless);
tried with agy 1.2.10 for Linux, whose sessions need a Google login, and the 1.2.9 Windows binary)
- Hooks: `~/.gemini/config/hooks.json`, `<workspace>/.agents/hooks.json` or a plugin's `hooks.json`, shaped
  `{"agon": {"enabled": true, "Stop": [{"type": "command", "command": "...", "timeout": 60}]}}`. Commands run with
  `sh -c`, on Windows `cmd /c` (quotes inside the command don't survive), in the folder of `hooks.json`. Stop
  stdin includes `executionNum`, `terminationReason`, `error`, `fullyIdle`, `conversationId`, `workspacePaths`,
  `transcriptPath`, `modelName`. To continue: stdout `{"decision": "continue", "reason": "<prompt>"}` and exit 0;
  any other decision, a non-zero exit, empty output or unknown keys let it stop. Default timeout 30 s.
- `terminationReason`: the docs say `model_stop`, `max_steps_exceeded`, `error`; 1.2.x sends `NO_TOOL_CALL`,
  `ERROR`, `USER_CANCELED`, `QUOTA_EXHAUSTED`, ... Continuing after an error re-enters the loop. A configurable cap
  ends long runs of continuations. Quota: "You have exhausted your quota on this model." (the server's error reads
  "RESOURCE_EXHAUSTED (code 429): ... Your quota will reset after 2h3m4s.").
- Plugins: a folder with `plugin.json` (its schema allows `name` and `description`), `mcp_config.json`, `hooks.json`,
  `skills/`, `agents/`, `rules/`. `agy plugin install <folder>` copies it to `~/.gemini/config/plugins/<name>/`;
  the IDE also loads `<workspace>/.agents/plugins/`. Plugin MCP servers start with `exec.Command(command, args)`
  in the plugin folder (`${PLUGIN_ROOT}` expands in args); `agy plugin validate` looks up the command from its own
  cwd.
- MCP: `~/.gemini/config/mcp_config.json` or `<workspace>/.agents/mcp_config.json` (`{"mcpServers": {...}}`), or
  `agy mcp add [flags] <name> <command> [args]`. `clientInfo.name` is `antigravity-client`.
- Headless: `agy -p "<prompt>" --output-format text | json | stream-json`, `--continue`,
  `--input-format stream-json` for multi-turn over stdin, `--mode default | accept-edits | plan`. Tools that need
  approval are refused in headless mode unless `--dangerously-skip-permissions` is set. Gemini CLI was replaced
  by `agy` on 2026-06-18.

**Windows** ([about_Pwsh](https://learn.microsoft.com/powershell/module/microsoft.powershell.core/about/about_pwsh))
- With `-Command`, Windows PowerShell 5.1 and PowerShell 7 turn an external program's exit code other than 0 or 1
  into 1: a hook can't count on exit code 2 there, while a JSON decision on stdout gets through.
- On Windows 11 with python.org Python 3.12 or 3.14, `python3` is the Microsoft Store stub (exit 9009) and `py -3`
  and `python` work (the maintainer's machine).

**MCP protocol**
- Revision `2026-07-28` is stateless (no `initialize`; version and client info travel in `_meta`; `server/discover`
  lists versions). Older revisions keep working when both sides agree, so keep answering `initialize` with a
  supported older version and reply `-32601` to unknown methods
  ([blog](https://blog.modelcontextprotocol.io/posts/2026-07-28/)).
- Spec 2025-11-25: unknown tools and malformed `tools/call` → JSON-RPC error `-32602`; input validation errors →
  a result with `isError: true` so the model can correct itself
  ([tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)). Tool annotations:
  `readOnlyHint`, `destructiveHint` (default true; false means additive only), `idempotentHint`, `openWorldHint`
  (default true).
- Tried against agon (Phase 1): the official Python SDK 2.2.0 `Client` (default `mode="auto"`) probes
  `server/discover` at `2026-07-28`, gets `-32601` and falls back to `initialize` at `2025-11-25`; the TypeScript SDK
  1.30.1 (the one Claude Code builds on) initializes at `2025-11-25` directly. Aborting a call makes both send
  `notifications/cancelled`.

**CI (GitHub Actions)** *(checked 2026-09-24 in the actions' repositories)*
- Current majors: `actions/checkout@v7`, `actions/setup-python@v7` (node24). `ubuntu-latest` is Ubuntu 24.04,
  `windows-latest` Windows Server 2025, `macos-latest` macOS 26 on arm64.
- Python 3.10 is source-only now: setup-python has 3.10.21 for Linux, but only 3.10.11 for Windows and macOS arm64.
  `python-version: "3.x"` means the newest stable release (3.14 today).
