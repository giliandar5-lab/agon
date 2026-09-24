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
- [x] Phase 3 — Cross-vendor second opinion (`ask`)
- [ ] Phase 3.1 — Review evidence (fix found in a real-CLI audit)
- [ ] Phase 4 — Task board (no downtime)
- [ ] Phase 5 — Autopilot (Agon wakes the agents itself)
- [ ] Phase 6 — The arena
- [ ] Phase 7 — Packaging

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
  Output per app, always a JSON decision on stdout with exit code 0 (Windows shells turn exit code 2 into 1):
  Claude Code and Codex → `{"decision": "block", "reason": "<prompt>"}`; Antigravity →
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
  `--sandbox read-only`), `agy -p=<prompt> --output-format json --add-dir <folder>` (review adds `--mode plan`; agy
  takes no prompt on stdin, see the facts below). Pass the prompt on stdin where supported. Parse the final message
  from each format, falling back to the raw output tail.
- Review prompt template: run the tests, cite the output, end with `VERDICT: approve` or `VERDICT: changes`. A review
  never changes the user's files: a reviewer whose app can't be held to read-only (agy, see the facts below) works
  in a throwaway copy of the repository, uncommitted changes included, which is deleted afterwards.
- Task mode runs in a temporary `git worktree` with write access and returns the summary, `git diff --stat` and
  the branch name; the caller decides whether to merge.
- Out of quota: if the target is marked out of quota or its output matches `AGON_LIMIT_PATTERNS`, mark it and
  try the next agent in `AGON_FALLBACK`; report who actually answered.
- Timeout (default 900 s) kills the whole process tree; a missing CLI gives a clear error; every call is
  logged to the chat (who asked whom, duration, verdict).
- Tests use fake CLI scripts through the same environment variables.

## Phase 3.1 — Review evidence (fix found in a real-CLI audit)

An audit on a Windows 11 PC ran `ask` in review mode with the **real** apps on a tiny repository whose test is
`python test_app.py`. Neither reviewer could run the test, and both still answered `VERDICT: approve`:
- Claude Code 2.1.280 (`-p --permission-mode plan`, model haiku): the Bash call got "This command requires
  approval": plan mode in `-p` has no one to approve commands, so every non-read-only command is denied.
- Codex CLI 0.144.2 (`exec --json --sandbox read-only`): the command ran in Codex's Windows sandbox, where PowerShell
  said `python` is not recognized: the sandbox's PATH doesn't reach the user's Python.
- Fake CLIs can't show this; that is why the tests passed. The same limits hit task mode ("run the tests before you
  finish"), since `acceptEdits` doesn't approve shell commands in `-p` either.

Fix, so that every verdict rests on evidence Agon itself produced:
- **Agon runs the tests, not the reviewer.** `AGON_TEST_CMD` (a command line or a JSON list, set by the human in the
  environment or the plugin config; never taken from a tool argument, so an agent can't use it to run commands
  outside its own app's sandbox) runs with a timeout (`AGON_TEST_TIMEOUT`, default 300 s), no shell, its own stdin
  and the same process-tree kill as `ask`. Review: in the project folder before the reviewer starts (for gemini, in
  its throwaway copy). Task: in the task's worktree after the app finishes, before Agon commits. Its exit code and
  output tail go into the reviewer's prompt ("Test results, run by Agon: …") and into the ask's result.
- **A verdict states its evidence.** The result says `VERDICT: approve (tests passed)`, `VERDICT: approve (tests
  failed)` or `VERDICT: approve (no tests run: set AGON_TEST_CMD)`; the arena line says the same. The review prompt
  tells the reviewer to approve only if the tests Agon ran passed, and to report failing tests as changes.
- **No AGON_TEST_CMD:** the ask still works, the result says clearly that no tests ran, and `setup`/README explain
  how to set it (examples: `python -m pytest -q`, `npm test`, `python test_agon.py`).
- Keep the reviewers read-only (plan mode, read-only sandbox, gemini's copy): with Agon running the tests they no
  longer need shell access.
- README: correct the claims that reviewers run the tests; document `AGON_TEST_CMD`, `AGON_TEST_TIMEOUT`.
- Tests: fake CLIs plus a fake test command that passes, fails, prints a lot, hangs past the timeout; verdict labels
  for each; `AGON_TEST_CMD` passed as a tool argument is ignored; a task's tests run in its worktree.
- Manual test on Windows: repeat the audit (a tiny repo, `AGON_TEST_CMD=python test_app.py`, a real claude review)
  and check that the result quotes Agon's test run and the verdict label.

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

## Phase 5 — Autopilot (Agon wakes the agents itself)

The full specification is [docs/autopilot.md](docs/autopilot.md): treat its **Design**, **Research first**,
**Tests** and **Done means** sections as this phase's bullets. In short:

- `python agon.py autopilot` keeps the team working with no app window open: when a message or task appears
  for an agent, Agon wakes that agent through its vendor's official CLI on the user's own subscription
  (`claude -p` stream-json, `codex exec resume`, `agy -p` stream-json). Idle costs nothing: no model calls,
  ~0% CPU, ~20 MB RAM; no worker process stays alive while idle.
- Wake-up ladder, cheapest first: a live Claude Code session's inbox socket (registered by the hook; no new
  process) → a warm worker kept for `AGON_WARM_SECONDS` → a cold start that resumes the agent's saved session.
- Rule-based triage with zero tokens: wake only on addressed messages, assigned or unblocked tasks and review
  requests; broadcasts wake only the lead; acknowledgments wake nobody; events are debounced into one prompt.
- Hard brakes: wakes per hour, daily USD/token caps, `--max-turns`, turn timeout, STOP, the auto-turn budget
  and out-of-quota parking with task reassignment.
- Session hygiene: reuse sessions while the cache is warm, rotate on token/turn/age thresholds with Agon's recap.
- Every wake is recorded (trigger, tokens, cost, duration, status); `python agon.py stats` reports cost per task.
- Research first, before coding: the inbox-socket wire format on Windows and Linux, exact limit errors of each
  CLI, memory and latency measurements, and cache lifetimes; record the results in this file.

## Phase 6 — The arena

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

## Phase 7 — Packaging

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
- Seen with 2.1.281 against a mock API (Phase 3): with no prompt argument, `claude -p` reads the prompt from stdin.
  `--output-format json` prints one line: `type: "result"`, `subtype`, `is_error`, `result`, `session_id`,
  `total_cost_usd`, `usage`, `api_error_status`, `terminal_reason`. An API 429 (`rate_limit_error`) is retried for
  about 3 minutes, then `is_error: true`, `api_error_status: 429`, `result: "API Error: Request rejected (429) · ..."`
  and exit 1 (with an API key; a plan's usage-limit text wasn't seen). `-p` runs the project's Stop hooks and its
  MCP servers with the caller's environment. On exit Claude Code ends its MCP servers with SIGINT.
- Plan mode lets the auto-mode classifier approve shell commands; without auto mode only the read-only set runs
  ([docs](https://code.claude.com/docs/en/permission-modes)). MCP tool calls: a wall-clock limit of
  `MCP_TOOL_TIMEOUT` (about 28 h by default) or a server's `timeout`, an idle limit of 30 min for stdio servers, and a
  main-conversation call that runs past two minutes moves to a background task ([docs](https://code.claude.com/docs/en/mcp)).

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
- Seen with 0.156.1 against a mock model (Phase 3): with no prompt argument `codex exec` reads it from stdin
  ("Reading prompt from stdin..." on stderr), in a read-only sandbox by default
  ([docs](https://developers.openai.com/codex/noninteractive)). `--json` events: `thread.started`, `turn.started`,
  `item.completed` (the answer is an `agent_message` item's `text`; items of type `error` are only warnings),
  `turn.completed`. A usage limit is not retried: `error` and `turn.failed` say "You’ve hit your usage limit. ... try
  again at 7:48 PM." (or "try again later."), exit 1. Stop hooks get Codex's environment.
- MCP (0.156.1): `tool_timeout_sec` (default 60) fails a longer call and sends no cancel; a plugin's `mcpServers`
  accept `tool_timeout_sec` and `env_vars` (`codex mcp list --json` shows them) and start in the plugin's cache
  folder. The model sees a server's tools as a `namespace` named `mcp__<server>`, described by the server's
  `instructions`. A tool that needs approval fails under `codex exec` ("MCP tool call requires approval, but approval
  policy is never") unless config.toml has `[plugins."<plugin>@<marketplace>".mcp_servers.<server>.tools.<tool>]`
  `approval_mode = "approve"` (the same key through `-c` didn't work). On exit Codex ends MCP servers with SIGTERM.

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
- Seen with agy 1.2.10 for Linux (the official manifest, SHA-512 checked) in API-key mode against a mock API
  (Phase 3): `-p` takes the prompt as its value (`-p --output-format json` fails with `-p took "--output-format" as
  its prompt`), and there is no prompt on stdin in text mode (`-p=-` sends "-"; an empty prompt is an error).
  `--output-format json` prints `conversation_id`, `status`, `response`, `error`, `duration_seconds`, `num_turns`,
  `usage`, on failure too (exit 1). `--mode plan` puts `/plan` before the prompt; `--mode accept-edits` works with
  `-p`. `--print-timeout` defaults to 0 (no limit), though the [docs](https://antigravity.google/docs/cli/headless)
  say 5 minutes.
- Without `--add-dir`, `agy -p` has no workspace: it tells the model "The user does not have any active workspace"
  and would write into a scratch folder of its own. With `--add-dir <folder>` that folder is the workspace (the
  system prompt maps it as `[URI] -> [CorpusName]`), and its `.agents/hooks.json` runs. The global Stop hooks run in
  `-p` mode, with the caller's environment.
- Writes in `-p` mode (1.2.10, a mock model that calls `write_to_file`): in `--mode plan` and `default`, a write in
  the workspace that no rule allows is refused ("a tool required the "write_file" permission that headless mode
  cannot prompt for, so it was auto-denied"), and so is one outside it; `accept-edits` writes. `--mode plan` doesn't
  stop a write the permissions allow: with `write_file(<project>)` in `permissions.allow`, a review overwrote the
  project's uncommitted file, and writes into a temporary folder go through without a rule.
- API-key mode (`"modelProvider": "gemini"` in `~/.gemini/antigravity-cli/settings.json`, `GEMINI_API_KEY`,
  `GOOGLE_GEMINI_BASE_URL`) runs headless without a Google login. A 429 `RESOURCE_EXHAUSTED` is retried 7 times (about
  100 s), then `status: "ERROR"`, `error: "API error (attempt 7): Error 429, Message: ... Status: RESOURCE_EXHAUSTED"`.
- On exit agy closes an MCP server's stdin and sends SIGTERM about 0.2 s later. Its MCP config documents no tool
  timeout ([docs](https://antigravity.google/docs/mcp)).

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
