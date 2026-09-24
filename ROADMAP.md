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

- [ ] Phase 1 — Solid core
- [ ] Phase 2 — Agents wake up on their own, one-command install, limit awareness
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

- **Storage:** SQLite in WAL mode (`busy_timeout=5000`, `synchronous=NORMAL`), one connection per thread.
  Tables: `msgs`, `agents(name, client, cursor, last_seen, autoruns, out_of_quota_until)`, `tasks` (Phase 4).
- **Delivery:** per-agent cursor stored in the database; advance it only after the output is written
  (at-least-once). Waiting uses `PRAGMA data_version` every 0.2 s (near-zero CPU, ≤ 0.2 s latency).
- **Agent tools (max 4):** `send`, `inbox`, `ask` (Phase 3), `tasks` (Phase 4).
- **Wake-up layers:** Claude Code channels (push) → Stop hooks in all three apps → `inbox(wait)` → the human.
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

**Claude Code — Stop hook** ([docs](https://code.claude.com/docs/en/hooks))
- Configured in `~/.claude/settings.json`, `.claude/settings.json` or a plugin's `hooks/hooks.json`:
  `{"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "...", "timeout": 60}]}]}}`.
- stdin JSON includes `session_id`, `transcript_path`, `cwd`, `hook_event_name`, `stop_hook_active`,
  `last_assistant_message`.
- Exit code 2 blocks the stop and shows stderr to Claude as the reason. Default timeout 600 s. Runs in the VS Code
  extension too.

**Claude Code — channels** ([docs](https://code.claude.com/docs/en/channels-reference))
- Declare `capabilities.experimental["claude/channel"] = {}`; send `notifications/claude/channel` with
  `params: {"content": "...", "meta": {"key": "value"}}`. Meta keys must be letters, digits and underscores
  (others are dropped silently). The server `instructions` string is shown to Claude on connect.
- Custom channels need `claude --dangerously-load-development-channels server:<name>` during the research
  preview (CLI only). A channel does not register if protocol revision `2026-07-28` is negotiated.

**Claude Code — headless and plugins**
- `claude -p "<prompt>" --output-format json` (final text in `result`), `--resume <session_id>`,
  `--permission-mode plan | acceptEdits`.
- Plugins: manifest `.claude-plugin/plugin.json`; MCP servers in `.mcp.json`; hooks in `hooks/hooks.json` (same
  schema as settings); a `.claude-plugin/marketplace.json` lets users run `/plugin marketplace add owner/repo` and
  `/plugin install <plugin>@<marketplace>` ([docs](https://code.claude.com/docs/en/plugin-marketplaces)).

**Codex — hooks** ([docs](https://developers.openai.com/codex/hooks)) *(details partly secondary)*
- `~/.codex/hooks.json`, `<project>/.codex/hooks.json`, or a plugin's `hooks.json`. On by default since 0.150.1;
  every non-managed hook must be trusted by the user in `/hooks`.
- Stop stdin includes `turn_id`, `stop_hook_active`, `last_assistant_message`. To continue: stdout
  `{"decision": "block", "reason": "<new prompt>"}` or exit code 2 with the prompt on stderr. `"continue": false`
  ends the turn. The Stop output schema rejects unknown fields. Default timeout 600 s.

**Codex — headless and plugins** *(secondary)*
- `codex exec --json "<prompt>"` streams JSONL events (`thread.started` carries the session id, `item.*`,
  `turn.completed`, `error`); continue with `codex exec resume <SESSION_ID> --json "<prompt>"`.
  `--full-auto` was removed in 0.147.0 (use explicit `--sandbox read-only | workspace-write`);
  `codex mcp-server` was removed in 0.154.0. `codex mcp add <name> -- <command> [args]` adds an MCP server.
- Plugins: `.codex-plugin/plugin.json` is required; optional `.mcp.json`, `hooks.json`, `skills/` at the plugin
  root. Install: `codex plugin marketplace add owner/repo`, then `codex plugin add <plugin>@<marketplace>` (0.146+).

**Antigravity (IDE and `agy` CLI)** ([hooks](https://antigravity.google/docs/hooks/),
[headless](https://antigravity.google/docs/cli/headless/))
- Hooks: `~/.gemini/config/hooks.json` or `<workspace>/.agents/hooks.json`, shaped
  `{"agon": {"enabled": true, "Stop": [{"type": "command", "command": "...", "timeout": 60}]}}`. Stop stdin
  includes `executionNum`, `terminationReason`, `error`, `fullyIdle`, `conversationId`, `workspacePaths`,
  `transcriptPath`, `modelName`. To continue: stdout `{"decision": "continue", "reason": "<prompt>"}`; any other
  decision lets it stop. Default timeout 30 s. Applies to the IDE and the CLI.
- MCP: `~/.gemini/config/mcp_config.json` or `<workspace>/.agents/mcp_config.json` (`{"mcpServers": {...}}`), or
  `agy mcp add <name> <command> [args]` *(secondary)*.
- Headless: `agy -p "<prompt>" --output-format text | json | stream-json`, `--continue`,
  `--input-format stream-json` for multi-turn over stdin, `--mode default | accept-edits | plan`. Tools that need
  approval are refused in headless mode unless `--dangerously-skip-permissions` is set. Gemini CLI was replaced
  by `agy` on 2026-06-18.

**MCP protocol**
- Revision `2026-07-28` is stateless (no `initialize`; version and client info travel in `_meta`; `server/discover`
  lists versions). Older revisions keep working when both sides agree, so keep answering `initialize` with a
  supported older version and reply `-32601` to unknown methods
  ([blog](https://blog.modelcontextprotocol.io/posts/2026-07-28/)).
