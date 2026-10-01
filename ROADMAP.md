# Agon roadmap

## Positioning

**Your AI rivals, one team.** Agon turns the agents of Claude Code, OpenAI Codex and Antigravity into one
team working on your project (not affiliated with Anthropic, OpenAI or Google; in commands and settings they are
`claude`, `gpt` and `gemini`), and shows it live in an arena. Two pillars:

1. **AI team arena.** Agents coordinate on a shared board, review each other's work across vendors, and can
   duel on a task so you learn which AI is best on *your* code.
2. **No downtime from usage limits.** When one agent runs out of quota, its work moves to the others
   automatically and comes back after the reset.

Who it is for: people who already use two or more AI coding tools, including people who work in GUI apps
(VS Code, Codex in the ChatGPT desktop app, Antigravity IDE) and on Windows, not only in tmux on macOS/Linux.

## Progress

Tick a phase in the same pull request that completes it.

- [x] Phase 1 — Solid core
- [x] Phase 2 — Agents wake up on their own, one-command install, limit awareness
- [x] Phase 3 — Cross-vendor second opinion (`ask`)
- [x] Phase 3.1 — Review evidence (fix found in a real-CLI audit)
- [x] Phase 4 — Task board (no downtime)
- [x] Phase 5 — Autopilot (Agon wakes the agents itself)
- [x] Phase 6 — The arena
- [x] Phase 7 — Packaging

## How every session works

When asked to do "the next phase":

1. Take the **first phase in Progress that is not ticked**. Implement only that phase; later phases come in
   separate sessions.
2. Read this whole file (including "Working rules" and "Verified platform facts"), then README.md, agon.py and
   test_agon.py.
3. Research before you plan. Find the phase's open questions: how comparable tools solve the same problem, the
   current docs of every CLI, hook and manifest it relies on, and what can go wrong on Windows. Show the user these
   questions and the exact `/deep-research …` line, then stop: no research starts before the user says yes, even
   when you could start it yourself. The user may send the line as a message of its own; wait for its report.
   Then give the strongest argument against each key decision. Where the findings contradict this roadmap, say so
   and let the user decide.
4. Turn every bullet of the phase into a numbered checklist. Show the research's findings, the checklist and a short
   plan to the user and wait for approval.
5. Work item by item: implement, add assert-based checks to test_agon.py, run `python test_agon.py`, commit.
   Never move on while tests fail.
6. If something is ambiguous, pick the simplest option that satisfies this roadmap and note it in the pull request.
7. Done means: every checklist item is implemented and covered by a test, `python test_agon.py` prints `ok`, the
   phase is ticked in Progress, and a pull request lists each item with how it was verified, what could not be
   verified, and step-by-step manual test instructions for Windows.
8. Reply in the language the user writes in.

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
  Tables: `msgs`, `agents(name, client, cursor, last_seen, autoruns, out_of_quota_until)`, `tasks` and `releases`
  (Phase 4); `runs`, `pilot`, `live` and `state` (Phase 5); `asks`, `reviews`, `duels`, `entries` and `gauges`
  (Phase 6). New steps only ever go at the end of `SCHEMA`, counted in `PRAGMA user_version`.
- **Delivery:** per-agent cursor stored in the database; advance it only after the output is written
  (at-least-once). Waiting uses `PRAGMA data_version` every 0.2 s (near-zero CPU, ≤ 0.2 s latency).
- **Agent tools (max 4):** `send`, `inbox`, `ask` (Phase 3), `board` (Phase 4).
- **Wake-up layers:** Claude Code channels (a doorbell: the push only says that messages wait) → Stop hooks in all
  three apps (a JSON decision on stdout) → `inbox(wait)` → the human. `UserPromptSubmit` hooks (Claude Code, Codex)
  tell an agent that comes back which of its tasks went to others.
- **Security:** arena on 127.0.0.1 with Host (plus exact `AGON_ARENA_HOSTS`), Origin and JSON checks and a
  nonce-based CSP; every message shows its author (`[HUMAN]` stands out); messages from agents are requests, never
  permissions; Agon never edits user config files; reviews are read-only by default.

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
- **Agon runs the tests, not the reviewer.** `AGON_TEST_CMD` (a command line or a JSON list) is set by the human, in
  the environment or in the Claude Code plugin's Test command option, which the plugin hands to Agon's server as
  `CLAUDE_PLUGIN_OPTION_TEST_COMMAND` (`AGON_TEST_CMD` comes first). It is never taken from a tool argument, so an agent
  can't choose the command line; it can still edit what the command runs (tests, `package.json`, `conftest.py`), and
  the README says so.
  - How it runs: found with `shutil.which` (so npm finds npm.cmd; a relative path is taken from the tests' folder), no
    shell (a command line with `&&`, `;`, `|`, `>` or a leading `NAME=value` is refused with a hint: a script, or a
    shell named in a JSON list; on Windows a batch file whose arguments hold `&`, `|`, `<`, `>`, `^`, `%` or quotes
    can't start, since cmd.exe would read them), its own stdin, no console window, and without Agon's own settings
    (`AGON_*`) in its environment, so a suite that uses Agon never starts an ask of its own. A timeout (`AGON_TEST_TIMEOUT`, default
    300 s) inside the ask's own time (so Codex's 960 s still cover the whole ask), and the same process-tree kill as
    `ask`, at the timeout and on STOP or a cancel; what the tests leave running when they exit is stopped too (the
    process group on POSIX, a job of its own on Windows).
  - Review: once per ask, in the project folder, before the first reviewer starts. Every reviewer reads that run: a
    fallback, and gemini in its throwaway copy, which lacks what `.gitignore` leaves out (`node_modules`, `.venv`).
  - Task: in the task's worktree once the app has finished, before Agon commits. Agon stages the app's work first and
    commits only that, so what the tests leave behind stays out of the branch.
  - Its exit code and output tail go into the reviewer's prompt ("Test results, run by Agon: …", indented as data from
    the code under test) and into the ask's result: stdout and stderr in order, the last ~3,000 characters, read as
    UTF-8, else on Windows as the ANSI code page (`mbcs`, not `locale.getpreferredencoding()`, see the facts below).
- **A verdict states its evidence.** The result says `VERDICT: approve (tests passed)`, `(tests failed)`,
  `(tests timed out)`, `(tests could not start)` or `(no tests run: set AGON_TEST_CMD)`, decided only from what Agon saw
  itself (the exit code, its own kill, a start that failed), never from the output; the arena line says the same, and
  a task names the outcome after its branch. The review prompt tells the reviewer to approve only if the tests Agon ran
  passed, to report failing or unfinished tests as changes, and to say so when no tests ran.
- **No AGON_TEST_CMD:** the ask still works, the result says clearly that no tests ran, and `setup`/README explain
  how to set it (examples: `python -m pytest -q`, `npm test`, `python test_agon.py`).
- Keep the reviewers read-only (plan mode, read-only sandbox, gemini's copy): with Agon running the tests they no
  longer need shell access.
- README: correct the claims that reviewers run the tests; document `AGON_TEST_CMD`, `AGON_TEST_TIMEOUT`.
- Tests: fake CLIs plus a fake test command that passes, fails, prints a lot, hangs past the timeout, forges Agon's
  report, writes cp1251, leaves a process behind; verdict labels for each; `AGON_TEST_CMD` passed as a tool argument
  is ignored; a task's tests run in its worktree; the ANSI fallback under `-X utf8`; the real `npm test` where npm is.
- Manual test on Windows: repeat the audit (a tiny repo, `AGON_TEST_CMD=python test_app.py`, a real claude review)
  and check that the result quotes Agon's test run and the verdict label.

## Phase 4 — Task board (no downtime)

- `board(action, ...)`: `list [id] | add(title, spec, files, after) | claim(id) | done(id, note, cwd) |
  review(id, verdict, evidence)`. The fourth tool is `board`, not `tasks`: the apps have task tools of their own
  (Antigravity's `manage_task`, Claude Code's Task tools, Codex's `update_plan`). It is marked local, and the four tools
  stay within the 2,500 characters of `tools/list`.
- Atomic claim (`BEGIN IMMEDIATE` + `UPDATE ... WHERE owner IS NULL`), with every check inside that transaction. A claim
  is refused while another agent's task in progress or in review has one of its files, naming the owner, and while a
  task in `after` isn't done (approved). A task's files are paths in the project: a file, a folder (`src/`) or `.`,
  compared as text whatever the letter case or slashes; no patterns, absolute paths or line breaks, and no `|` in them
  or in a title. `claim` answers with the task's spec and notes, newest first (a reviewer's changes stay there when the
  task goes back to the board).
- `done` (the owner only): Agon runs `AGON_TEST_CMD` in the project folder, unasked, and its outcome labels the review;
  red tests never stop `done`. The task goes to an online agent (seen in the last 15 minutes) of another company, the
  one that asked for changes first; an agent whose company had the task before it went back to the board comes last. The
  reviewer must be a different agent and vendor (by the app it connected with, else by its name). `changes` sends the
  task back to its owner, or to the board when the owner is away; `approve` closes it and tells everyone which tasks it
  frees. `done` and `review` from an agent that no longer has the task say who has it now and why.
- Nobody from another company online: the human is told, and the next board call once one is online asks it. With
  `AGON_AUTO_REVIEW=1` (off by default: it sends the code to another company's app and spends that plan, unasked), Agon
  runs one's app headless for the review through `ask`; its verdict counts only if the task hasn't moved on meanwhile.
- When an agent's hook reports its usage limit, its in-progress tasks go back to `todo` with a note ("reassigned: claude
  hit its usage limit, resets ~14:00"), and its reviews go to another agent. A claim also lasts
  `AGON_LEASE` seconds (7200) after its owner's last sign of life, any Agon request or hook run, and goes back at the
  next board call, as does a review: a crashed app, and Codex, whose hooks never see a limit. A limit that an `ask` ran
  into on an agent's plan only takes it out of reviews and asks, until the reset or its next tool call (its model runs,
  so it isn't out of quota): the agent may be in the middle of a task. After the reset the agent returns to rotation, and
  before it works again it hears once which of its tasks went to others, who has them and not to edit their files:
  through `UserPromptSubmit` in Claude Code (which resumes the interrupted task by itself) and Codex, else at the start
  of `inbox` or of the Stop hook's prompt.
- Every state change posts a short message to the agent that must act (a review request to the reviewer, a verdict to
  the owner); a task anyone can take goes to everyone but its author, and a claim only to the arena.
- The team playbook (lead, one writer per file, split by context boundaries, evidence-based reviews, don't reply to
  acknowledgments) is in the server `instructions` (the board's rules in the first 512 characters, all of it within
  2,048) and in the README, which also says what runs without asking.
- Tests: a claim race between two processes (the same 30 tasks, each claimed by both at once), file conflicts,
  dependencies, author ≠ reviewer and vendor, reassignment on quota, leases, the returning agent's note, the automatic
  review with fake CLIs.

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
- Done in v0.5.0, with what the research changed (docs/autopilot.md, "What the research changed"): no warm workers
  (a cold resume sends the same request, so the prompt cache should serve it); agy runs only in its API-key mode; the
  inbox socket only for an idle Claude Code session, posted by its own Agon server when autopilot asks;
  `AGON_MAX_WORKERS` 3; a session idle past the cache's life with a large context starts anew; Claude Code's tokens
  from `modelUsage`, a run's share from the highest totals seen, and claude rests on extra usage
  (`AGON_EXTRA_USAGE=1`). Measured facts: see Phase 5 additions below.

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
- Done in v0.6.0, with what the research changed: fuel is states for every agent, plus Claude's plan percentages from
  the status line command the human sets (Agon keeps only the numbers, their reset times and the session id); a phone
  goes through SSH or Tailscale, with exact extra names in `AGON_ARENA_HOSTS` and an Origin check on every POST; a
  hidden tab lets its event stream go (six connections per site); duels get `AGON_SETUP_CMD` in each worktree, a
  baseline test run on the commit they start from, blind A/B/C labels until the pick, one duel and one setup or test
  run at a time; the scoreboard counts only work whose author Agon knows, and hints need three results, shown as raw
  counts; export masks known key formats, e-mail addresses and the home folder (`--no-redact` keeps them), with its
  CSP first and hashes; `say` reads stdin or a file (PowerShell drops quotes); the arena no longer shares its port on
  Windows. Measured facts: see Phase 6 additions below.

## Phase 7 — Packaging

- PyPI package `agon-arena` with an `agon` command (`uvx agon-arena`), listings in plugin marketplaces and MCP
  directories, a demo video, and measured numbers (idle CPU and RAM, `tools/list` size, tokens per turn).
- Every tool says its `title` and all four hints (`readOnlyHint`, `destructiveHint`, `idempotentHint`,
  `openWorldHint`; `ask` keeps the default open world): the claude.ai directory requires them, and an app reads a
  missing hint as the riskier value. `board` is not destructive: it records task state on Agon's own board, every
  action also posts to the chat, and reviews have a table of their own. `ask` is: another company's agent may write
  files (on a branch of its own). So the `tools/list` limit in the tests went from 2,500 to 2,900 bytes (the new size
  and a small margin) instead of cutting the descriptions: Claude Code and Codex defer tool schemas behind tool
  search, so the model reads the names and the server instructions first, and a schema only when it needs the tool.
- Listings: the official MCP Registry (`io.github.giliandar5-lab/agon`, from `server.json`, published by the release
  workflow), the claude.ai directory (its form, by the maintainer), awesome-mcp-servers, mcp.so, Glama, the
  Antigravity interest form and awesome-codex-plugins. The texts for the lists run by other people go in the pull
  request; the maintainer submits them after the release (no pull requests in other people's repositories from a
  session).
- Tokens per turn: Claude Code and Codex, from the usage each app reports, with and without Agon. Antigravity's
  `gemini` is "not measured": its headless usage needs an API key.
- Done in v0.7.0: the package (`agon-arena`, built by `flit_core` at release time), the `agon` command, setup that
  prints the command an install keeps, a database that older copies keep working on, annotations, the directory policy
  checks, PRIVACY.md and SECURITY.md, CI that builds and installs the package on each system, the release workflow,
  `server.json`, the measuring and screenshot scripts, and the numbers CI measured. Left to the maintainer: the
  TestPyPI dry run and the tag that publishes to PyPI and the MCP Registry (after testing with the real apps on
  Windows), the token numbers for Claude Code and Codex, the listings' forms and pull requests, and the demo video (a
  real recording only).

## Non-goals

A Rust/Go rewrite, Electron, third-party dependencies, dozens of tools, parallel-writer swarms by default,
editing users' config files, hard-coded model rankings, claims we can't measure. (`flit_core` builds the PyPI package
at release time only: nothing installs it to run Agon, and the package depends on nothing.)

## Working rules for every phase

- Check the current official docs for every CLI flag, hook schema and plugin manifest before relying on it;
  these tools change monthly. If the docs are unreachable from your environment, use the facts below and list
  in the pull request what you could not re-verify.
- `agon.py` stays one file with zero dependencies; existing tools stay backward compatible.
- Every schema step stays backward compatible (new tables, or new columns with defaults, never a new meaning for an
  old column), so an older copy keeps working: each app keeps its own copy of Agon, and all share one database. The
  arena and setup name the app whose copy is older and say how to update it.
- Every new behavior gets an assert-based check in `test_agon.py`; `python test_agon.py` must print `ok`.
- The real apps (Claude Code, Codex, Antigravity) may not be available where you work: simulate them in tests
  (fake hook payloads, fake MCP clients, fake CLI scripts) and give manual test steps in the pull request.

## Verified platform facts (checked 2026-09-24; Phase 4 and 5 additions 2026-09-25; Phase 6 additions 2026-09-26 to 30)

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
- Stop stdin also has `background_tasks` and `session_crons`. StopFailure's `error` is one of `rate_limit`, `overloaded`,
  `authentication_failed`, `oauth_org_not_allowed`, `account_on_hold`, `billing_error`, `invalid_request`,
  `model_not_found`, `server_error`, `max_output_tokens`, `cloud_credential_error`, `unknown`: a plan's usage limit has no
  value of its own, and "API Error: Server is temporarily limiting requests (not your usage limit)", a throttle retried
  since v2.1.199, may end a turn too.
- `UserPromptSubmit` runs before a prompt reaches Claude (stdin adds `prompt`); stdout
  `{"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "..."}}` or plain text adds context.
  Its default timeout is 30 s. After a usage limit resets, an interactive claude.ai session (v2.1.234+, on by default)
  continues the interrupted task with a fixed prompt that goes through this hook (blocking it ends the wait); not in
  `-p`, for agent-team teammates, or when the reset is over 24 hours away. Notification types
  `quota_auto_resume_fired`, `_stale` and `_disabled` report it.
- The plan limits read "You've hit your session limit · resets 3:45pm" (also `weekly`, `Opus`, `Sonnet`; the weekly one
  says "resets Mon 12:00am"). The session and weekly limits are shared across models
  ([errors](https://code.claude.com/docs/en/errors)).
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
- Plugin options (`userConfig`), seen with 2.1.282 and a real `claude -p` against a mock API (Phase 3.1): hooks get them
  as `CLAUDE_PLUGIN_OPTION_<KEY>`, but a plugin's MCP server doesn't, although the
  [docs](https://code.claude.com/docs/en/plugins-reference) say it does (nor does `claude mcp list`'s health check).
  `"env": {"NAME": "${user_config.KEY}"}` in the server's config passes one; an option that was never set arrives as
  its `default` (`claude plugin install` then says "1 userConfig option not yet set"). Plugin options are read only
  from user, `--settings` and managed settings, never from a project's `.claude/settings*.json` (docs).
- Claude Code cuts each MCP tool description and each server's `instructions` at 2,048 characters
  (`CLAUDE_CODE_MAX_MCP_DESCRIPTION_LENGTH`, v2.1.280+). MCP tool search is on by default: at the start Claude sees only
  the tool names and the servers' instructions (`alwaysLoad` in a server's config, or `_meta["anthropic/alwaysLoad"]` on
  a tool, loads them up front). A root-level `oneOf`/`anyOf` is flattened (v2.1.195+); `_meta["anthropic/
  requiresUserInteraction"]: true` asks on every call (v2.1.199+). The built-in Task tools are on by default only on
  older models (`CLAUDE_CODE_ENABLE_TODO_TOOLS=1` elsewhere) ([mcp](https://code.claude.com/docs/en/mcp)).
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
- Twelve hook events (PreToolUse, PermissionRequest, PostToolUse, PreCompact, PostCompact, UserPromptSubmit,
  SubagentStart, SubagentStop, Stop, Interrupt, SessionStart, SessionEnd), none for a failed turn (source 0.157.0: a
  usage limit ends the turn with an error event and runs no hook; the legacy `notify` fires only on a finished turn).
  `UserPromptSubmit` stdin adds `turn_id` and `prompt`; plain stdout or `hookSpecificOutput.additionalContext` becomes
  developer context, and exit 0 with no output adds nothing. Model-visible hook output is cut at about 2,500 tokens.
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
- MCP docs (2026-09-25): keep the first 512 characters of a server's `instructions` self-contained; per server
  `default_tools_approval_mode` is auto, prompt, writes (asks for tools not marked read-only) or approve, and
  `tools.<tool>.approval_mode` sets one tool. `clientInfo.name` is `codex-mcp-client` (source).
- Plugins ([docs](https://developers.openai.com/plugins/build/plugins), source c98e263, 2026-09-25): OpenAI's portable
  format has a root `plugin.json` with `"$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"`. Codex
  takes a root `plugin.json` as the manifest only when its `$schema` starts with `https://agent-plugins.org/schemas/`;
  otherwise it reads `.codex-plugin/plugin.json`, then `.claude-plugin/plugin.json`, then `.cursor-plugin/plugin.json`
  (a root `plugin.json` that is a link or not a file stops the search). A portable package's MCP servers come only from
  a root `mcp.json`, and `.codex-plugin`'s `mcpServers` are ignored. Agon's root `plugin.json` has Antigravity's
  `$schema`, so Codex never takes it for its own.
- On 2026-07-09 the Codex desktop app became a mode of the ChatGPT desktop app (Chat, Work and Codex; macOS and
  Windows) *(the date: secondary)*. The codex CLI, the ChatGPT app and the IDE extension share `~/.codex/config.toml`,
  MCP servers, hooks and plugins, and the app loads plugins from the same cache.
- The usage limit (source 0.157.0): "You’ve hit your usage limit." then " Try again at {time}." or, with an upsell,
  " or try again at {time}." (or "later"); the time is local, `3:05 PM` or `Sep 26th, 2026 3:05 PM`. A plan limit is not
  retried. ChatGPT plans have a ~5-hour and a weekly window (not the 5-hour one on Pro for now) *(secondary)*.
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
- Stop stdin (docs, 2026-09-25) also has `fullyIdle` and the common fields `artifactDirectoryPath` and `modelName`; hooks
  run in Antigravity 2.0, the CLI and the IDE. Built-in tools include `manage_task` (background tasks: `list`, `kill`,
  `status`, `send_input`) and `send_message`. An MCP tool that no rule allows runs in Ask mode, asking every time;
  `mcp(server/tool)` and `mcp(server/*)` rules allow it ([mcp](https://antigravity.google/docs/mcp)).
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
- Python writes to a file or a pipe in the ANSI code page (cp1251 on a Russian Windows) unless UTF-8 mode is on
  ([docs](https://docs.python.org/3/library/sys.html#sys.stdout)). In UTF-8 mode (`PYTHONUTF8=1`, `-X utf8`, the default
  from Python 3.15) `locale.getpreferredencoding(False)` says `utf-8` whatever the other programs write, while
  `bytes.decode("mbcs")` still reads the ANSI code page (the maintainer's Windows 11, Russian locale, Python 3.12.10 and
  3.14.0 under `-X utf8`). `mbcs` exists on Windows only.
- A batch file such as npm's `npm.cmd` starts through CreateProcess only by its full name (`shutil.which` adds the
  PATHEXT ending), and then cmd.exe parses its arguments
  ([docs](https://docs.python.org/3/library/subprocess.html#security-considerations)). In Python 3.12.0,
  `shutil.which` could return the extensionless `npm` next to it, which Windows can't start
  ([cpython#109590](https://github.com/python/cpython/issues/109590)) *(secondary)*.

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
- Tasks (2025-11-25, experimental: `tasks/*` methods, `execution.taskSupport` per tool, capability
  `tasks.requests.tools.call`) became the extension `io.modelcontextprotocol/tasks` in 2026-07-28: no clash with a tool
  named `board` or `tasks`. Tool names are 1–128 of `A-Za-z0-9_.-`; the spec sets no length on descriptions, and "there
  SHOULD always be a human in the loop with the ability to deny tool invocations". 2026-07-28 moves `instructions` to
  `server/discover`, which clients may skip.
- Tried against agon (Phase 1): the official Python SDK 2.2.0 `Client` (default `mode="auto"`) probes
  `server/discover` at `2026-07-28`, gets `-32601` and falls back to `initialize` at `2025-11-25`; the TypeScript SDK
  1.30.1 (the one Claude Code builds on) initializes at `2025-11-25` directly. Aborting a call makes both send
  `notifications/cancelled`.

**SQLite and Python** (checked 2026-09-25)
- `BEGIN IMMEDIATE` takes SQLite's one write lock at BEGIN and waits the busy timeout for it; a deferred transaction
  that reads and then writes fails at once with `SQLITE_BUSY` (or `SQLITE_BUSY_SNAPSHOT`), without waiting. So a claim's
  checks and its write go in one IMMEDIATE transaction ([docs](https://sqlite.org/lang_transaction.html)).
- Python's `sqlite3`: `isolation_level=None` (3.10, 3.11) and `autocommit=True` (3.12+) leave SQLite in its autocommit
  mode, where an explicit `BEGIN IMMEDIATE` works. The default `autocommit=LEGACY_TRANSACTION_CONTROL` will change to
  `False`, which keeps a transaction open, and then `BEGIN` fails ([docs](https://docs.python.org/3/library/sqlite3.html)).
- Two processes that claim the same 30 tasks at once (Python 3.10–3.13, SQLite 3.45.1): every task got one owner.
- Windows paths: `os.path.normcase` lowercases only on Windows, and `realpath` resolves 8.3 names and junctions only for
  paths that exist. Agon compares a task's files as text (relative, `/`, NFC, case-folded) and resolves no links.
- Clocks on Windows before Python 3.13: `time.time()` (`GetSystemTimeAsFileTime`) and `time.monotonic()`
  (`GetTickCount64`) move in 15.6 ms steps; `time.get_clock_info("time").resolution` is 0.015625. From 3.13 both have
  1 µs ([What's New in 3.13](https://docs.python.org/3/whatsnew/3.13.html)). So two quick events can get the same time:
  a task's `version`, not its time, tells its changes apart, and `last_seen` only grows across agents. The tests run
  every Python process of theirs on such a clock, on every system (found by CI on windows-latest, Python 3.10).

**Phase 5 additions (checked 2026-09-25, hands-on against local mocks of each vendor's API; no real model calls)**

*Claude Code 2.1.282* (the public npm build, `env -i`, its own HOME, a mock of the Messages API)
- Every session, `-p` stream-json and interactive alike, binds an inbox for cross-session messaging: a Unix socket
  `/tmp/cc-socks-<uid>/<pid>.sock` (folder 0700; `system/init` shows `messaging_socket_path`); on Windows a named pipe
  ([docs](https://code.claude.com/docs/en/cross-session-messaging): v2.1.224+, Windows v2.1.234+). Hooks (not
  SessionEnd), the Bash tool and **MCP servers** get `CLAUDE_CODE_MESSAGING_SOCKET`, `CLAUDE_CODE_MESSAGING_TOKEN`,
  `CLAUDE_CODE_SESSION_ID` and `CLAUDE_PROJECT_DIR` (MCP servers as seen here: the docs name only hooks and the Bash
  tool).
- Wire format: newline-terminated JSON, `{"type":"auth","token":"…"}` then
  `{"type":"user","message":{"role":"user","content":"…"},"priority":"next"}`. No reply. Linux and macOS know the
  session's own children by the process (the auth line is optional for them); on Windows the token is the proof.
  `now` aborts a running turn (`error_during_execution`, `aborted_streaming`); `next` waits for it, and queued `next`
  messages merge into one turn; `later` runs after them. An idle interactive session starts a turn; its
  `UserPromptSubmit` hook gets the raw text as `prompt`. The model sees "Another Claude session sent a message: …".
  Delivered messages count toward usage like typed ones; repeats are throttled, at most 50 queue.
- stream-json: input `{"type":"user","message":{"role":"user","content":"…"}}`, one turn per line; each turn prints
  `system/init` (with `claude_code_version`), `assistant` events (`message.usage`: the context of that call) and a
  `result` whose `usage` sums the turn's calls (the main loop's, without subagents), `total_cost_usd` and `modelUsage`
  (tokens per model, subagents included) the process's running totals (since 2.1.277 with a resumed session's
  earlier spend, restored from the transcript on a normal exit, which a kill skips; a crash result may carry them
  zeroed; "Do not bill end users or trigger financial decisions from these fields":
  [docs](https://code.claude.com/docs/en/agent-sdk/cost-tracking)), `num_turns`, `permission_denials`,
  `terminal_reason`. `{"type":"control_request","request_id":"…","request":{"subtype":"interrupt"}}` on stdin ends
  the turn with a result, and the process stays. SIGINT exits 0 with no
  result, SIGTERM 143; every case resumes. `claude -p` with stdin left open waits 3 s for it.
- **A cold `--resume` sends what a warm process would:** the request of `-p --resume <id>` in a new process equals the
  next request of a running stream-json process (same system, tools, messages and cache marks), so the prompt cache
  should serve both. Not measured on the live API; one user's unverified report
  ([anthropics/claude-code#96163](https://github.com/anthropics/claude-code/issues/96163)) says print mode rewrites
  ~25k tokens every turn on some models, warm or cold alike. A plan's main conversation, `-p` included, gets a 1-hour
  cache TTL, 5 minutes on usage credits (extra usage) or an API key
  ([docs](https://code.claude.com/docs/en/prompt-caching)); Codex's and Gemini's weren't found.
  Start → first request 0.54 s, a trivial turn 0.66 s, peak RSS 238 MB; a stream-json process 202-250 MB.
- `-p` denies MCP tools in every permission mode (`default`, `acceptEdits`, `auto`, `dontAsk`, `plan`) unless
  `--allowedTools` names them (`mcp__agon`, or `mcp__plugin_agon_agon` for the plugin's server). `acceptEdits` writes
  files and runs `echo > file`, not `python3 …`. `--permission-prompts none` denies what would prompt. `--max-turns`
  works (not in `--help`), `--max-budget-usd` ends a run with `error_max_budget_usd`, `--session-id <uuid>` names a
  new session, `--resume <unknown>` fails with "No conversation found with session ID". `--bare` never uses the plan
  login. SessionStart, UserPromptSubmit, Stop and SessionEnd hooks run in `-p`.
- A rejected 429 (`anthropic-ratelimit-unified-status: rejected`) is not retried; the stream-json process exits 1. A
  plan's limit comes as `rate_limit_event` with `rate_limit_info.status: "rejected"` and `resetsAt`
  ([SDK types](https://code.claude.com/docs/en/agent-sdk/typescript); `errorCode: "credits_required"` when the included
  usage is gone and no credits are left). Live events also carry `rateLimitType` and `isUsingOverage`, which the types
  don't list: past the limit, a user with extra usage is billed instead of rejected (and the cache TTL drops to 5
  minutes).

*Codex 0.157.0* (npm; source at `rust-v0.157.0`; a mock Responses API provider)
- `codex exec --json -s workspace-write [-m M] [-c model_reasoning_effort=E] [resume <id>] -`: the prompt on stdin
  (read to its end first; closing stdin can't interrupt). `-s` and `-C` must come before `resume`. Outside a git
  repository `--skip-git-repo-check` is required. Events: `thread.started{thread_id}`, `turn.started`,
  `item.completed` (`agent_message`, `command_execution`, ...; type `error` items are warnings), `turn.completed{usage}`
  or `turn.failed`, and non-fatal `error` events ("Reconnecting... 1/5"). `usage` (`input_tokens` with
  `cached_input_tokens` among them, `output_tokens`, `reasoning_output_tokens`) is **the thread's running total, across
  processes**. The prompt prefix is byte-stable across processes and `prompt_cache_key` is the thread id.
- A usage limit: one request, `error` then `turn.failed`, exit 1, nothing on stderr; the texts are "You’ve hit your
  usage limit…", "Your workspace is out of credits", "You hit your spend cap", "To use Codex with your ChatGPT plan,
  upgrade…", "Quota exceeded…" and, mid-stream, "The usage limit has been reached". Rate limits never reach stdout
  (only the session file). An unknown thread id: exit 1 "no rollout found for thread id …"; two resumes of one thread
  at once: "already has an active writer". SIGINT: exit 1; kill the process group (the npm launcher's SIGKILL orphans
  the native binary). `codex app-server` exists but is labelled experimental.
- MCP per run works through `-c mcp_servers…`; `board` runs unasked, `ask` needs an approval rule. `exec` runs hooks
  only when trusted. Startup: 0.29-0.37 s, 151-206 MiB.

*agy 1.2.11* (the official manifest; API-key mode against a mock; no Google login)
- `agy --input-format stream-json --output-format stream-json --disable-slash-commands --mode accept-edits
  [--conversation <id>]`; **no `-p`** (it would take the next argument as its prompt, exit 2). Input
  `{"event":"user","message":{"content":"…"}}`, one turn per line; `init{conversation_id}`, `step_update`s, then
  `result{status, response, usage, num_turns, denied_actions}`. `usage` is the conversation's running total, across
  processes (`input_tokens` excludes the cached ones). `--conversation <unknown>` starts a new conversation with a
  warning. Two processes on one conversation corrupt it (no lock). The working folder is the workspace (no
  `--add-dir` needed).
- A 429 or dropped connection is retried ~150 s; `QUOTA_EXHAUSTED` or a long RetryInfo once; then exit 3,
  `status: "ERROR"` and an `AGY_ERROR: {…}` line on stderr ("Your quota will reset after 2h3m4s."). After an error it
  recovered from, **every later turn reports `status: "ERROR"`** with exit 0 and a good response. SIGINT/SIGTERM end
  the turn at once (`error: "interrupted"`, exit 1); every case resumes.
- Headless, an MCP tool without a rule is refused (`denied_actions: [{"action":"mcp"}]`, SUCCESS, empty response):
  `"permissions": {"allow": ["mcp(agon/*)"]}` in `~/.gemini/antigravity-cli/settings.json` allows Agon's tools. The
  Stop hook runs after every turn, before its `result`. Idle 166 MB, peak 220 MB, start → first request 0.26 s; a
  fresh home adds a background updater (`AGY_CLI_DISABLE_AUTO_UPDATE=true` stops it).

*Policies* (read 2026-09-25; Anthropic's and OpenAI's pages again 2026-09-26)
- Anthropic: the Consumer Terms forbid access "through automated or non-human means" except with an API key "or where
  we otherwise explicitly permit it", and Claude Code's docs explicitly permit scripted and scheduled runs on a plan:
  "For CI pipelines, scripts, or other environments where interactive browser login isn't available, generate a
  one-year OAuth token with `claude setup-token`", which "authenticates with your Claude subscription"
  ([Authentication](https://code.claude.com/docs/en/authentication)); the GitHub Action runs in automation mode on
  any event, a cron schedule included, and "If you authenticate with an OAuth token, runs use your Claude
  subscription instead of API billing" ([GitHub Actions](https://code.claude.com/docs/en/github-actions)). The
  [legal page](https://code.claude.com/docs/en/legal-and-compliance) lets "an end user" sign in "to the unmodified
  Claude Code binary with their own Claude subscription"; it forbids third parties to "route requests through Free,
  Pro, or Max plan credentials on behalf of their users" and to "collect, store, or intermediate Claude.ai credentials
  or session tokens", and says Pro and Max limits "assume ordinary, individual usage of Claude Code and the Agent
  SDK". The Help Center (updated June 16, 2026) says `claude -p`, the Agent SDK and third-party apps "still draw from
  your subscription's usage limits". (The research concluded that no vendor explicitly permits unattended runs on a
  plan: it missed the authentication and GitHub Actions pages.) The Agent SDK reference documents how an app that
  "runs prompts on its own schedule" declares each run (`CLAUDE_CODE_HOST_SCHEDULED_RUN=1`, a `scheduled-trigger`
  origin); Agon doesn't, for now.
- OpenAI: the pricing page lists "Codex SDK, codex exec, and scriptable workflows" for Plus and Pro, and OpenAI
  documents running Codex as your own account in automation
  ([Maintain Codex account auth in CI/CD](https://developers.openai.com/codex/auth/ci-cd-auth)): "an advanced workflow
  for enterprise and other trusted private automation", while "The right way to authenticate automation is with an
  API key" ("Do not use this workflow for public or open-source repositories", about runners that hold `auth.json`).
  The [Terms of Use](https://openai.com/policies/row-terms-of-use/) forbid circumventing "any rate limits or
  restrictions".
- Google: the Antigravity FAQ and Additional Terms (item 6) call third-party software on an Antigravity login a
  violation that can end the account, and the FAQ recommends a Gemini Enterprise or AI Studio API key; agy's API-key
  mode (`"modelProvider": "gemini"`, `GEMINI_API_KEY`) never creates an account session. The terms stop applying only
  with "a Gemini Enterprise API Key" (or an Enterprise or Workspace account), and item 6 also bars "using the Service
  in connection with products not provided by us".

*Agon's autopilot* (Linux, Python 3.11): idle 30 MB RSS and ~0.1% of a core (it polls `PRAGMA data_version` every
0.2 s).

**Phase 6 additions (checked 2026-09-26 to 2026-09-30; hands-on with Python 3.11, Chromium via Playwright 1.56, git
2.43 and Claude Code 2.1.283 on Linux, unless marked)**

- Server-Sent Events on `http.server.ThreadingHTTPServer`: a stream that ends makes Chromium reconnect after `retry`
  with `Last-Event-ID`. Chromium opens at most six connections to one host across a profile's tabs: with six arena
  tabs holding a stream, a seventh tab's load (and a POST, STOP included) hangs until one closes. A closed tab is
  noticed at the next write (BrokenPipeError; on Windows WinError 10053/10054). One idle stream costs ~0.1% of a core
  (polling `PRAGMA data_version` every 0.2 s).
- CPython sets SO_REUSEADDR whenever `allow_reuse_address` is true, on every platform, and `HTTPServer` sets it. On
  Windows a second socket with SO_REUSEADDR binds a port another one listens on, and which one gets a connection is
  undefined ([Microsoft](https://learn.microsoft.com/windows/win32/winsock/using-so-reuseaddr-and-so-exclusiveaddruse),
  CPython gh-85307). Checked by the user on Windows with Python 3.12 and 3.14: a second ThreadingHTTPServer binds the
  same port; with `allow_reuse_address` off, a second bind is refused whether it sets SO_REUSEADDR or not.
- Claude Code's status line ([docs](https://code.claude.com/docs/en/statusline)): the command gets JSON on stdin with
  `rate_limits.five_hour` and `seven_day` (`used_percentage` 0-100, `resets_at` in Unix seconds) only for Pro and Max
  subscribers, after the session's first API response (`spend_limit` behind a Claude apps gateway, v2.1.251+), and the
  transcript's path, the folders and the cost too. On Windows it runs through Git Bash, or PowerShell when Git Bash is
  absent: paths take forward slashes. A plugin can set only `agent` and `subagentStatusLine`, not the main status line
  ([plugins reference](https://code.claude.com/docs/en/plugins-reference)).
- Codex reports its limits through `codex app-server` (`account/rateLimits/read`); the command is experimental, and a
  long-lived process can spoil the refresh token that every Codex client shares *(from its source and issues; not
  used)*. agy documents no usage source.
- Tailscale Serve (`tailscale serve --bg 8765`, from its source) passes its own `*.ts.net` name as the Host; VS Code's
  port forwarding rewrites it to localhost *(from its source; not tried)*. `ssh -L` keeps `127.0.0.1:8765`.
- git 2.43: three threads making worktrees, committing and removing them on one repository at once: no error. A
  gemini review copy (`git clone --mirror --shared`) of a linked worktree works: HEAD is the worktree's branch.
- A new worktree has only what git tracks. Claude Code's `claude -p --worktree NAME` makes
  `<repo>/.claude/worktrees/NAME` (where a project's own test runner may find it); Agon's go to the temporary folder.
- With a `src/` layout installed by `pip install -e`, Python started in a worktree imports the main folder's package.
- An HTML file opened as `file://` with a `<meta http-equiv="Content-Security-Policy">` first in `<head>`: an external
  stylesheet, image, `fetch()` and an image beacon are all refused, and no request reaches the network. Data in a
  `<script type="application/json">` with `<`, `>`, `&`, U+2028 and U+2029 escaped parses back exactly; unescaped, a
  `</script>` in it ends the element early. The arena's download (a Blob URL on an `<a download>`) works under its CSP.
- Terminals: Python enables no VT processing in a Windows console (Agon calls `SetConsoleMode`); printing an emoji to a
  redirected stdout fails without UTF-8; PowerShell 5.1 drops the double quotes inside an argument to a native program,
  and so does any call through `agon.cmd` in PowerShell 7 *(Windows facts from Microsoft's docs; not tried here)*.
- `http.server.HTTPServer.server_bind` looks up the address's name (`socket.getfqdn`, a reverse DNS lookup). For
  `127.0.0.1` it took 35 s in each new process on GitHub's macOS runners, 0.01 s on the Linux and Windows ones *(CI,
  2026-09-30)*. The arena binds without it and listens within about 0.1 s.
- Windows paths *(the maintainer on Windows 11, and CI)*: `%TEMP%` is inside the home folder, in the 8.3 short form of
  a long user name (`C:\Users\RUNNER~1\AppData\Local\Temp` on GitHub's runner); git spells the same folder long, with
  `/`. Git Bash, and so Claude Code's Bash tool, writes the home folder as `/c/Users/me`. A child's `print()` into a
  pipe ends its lines with `\r\n`.

**Phase 7 additions (checked 2026-09-30 to 2026-10-01; hands-on with uv 0.8.17, Python 3.11, flit_core 4, Claude
Code 2.1.285 and codex-cli 0.159.3 on Linux)**
- Packaging: `flit_core` (>=4) builds one module from `agon.py`, with the version from `__version__` and the summary
  from the docstring's first line, Metadata 2.5 with a PEP 639 `license = "MIT"` and no `Author-email`. hatchling and setuptools build it
  too; `uv_build` wants a package folder (`agon/__init__.py`). An sdist that leaves out the tests stays small.
- `uvx agon-arena` needs a script named like the package (`agon-arena`), else uv says to use `uvx --from agon-arena
  agon`. uvx keeps its environments in uv's cache (`archive-v0`, `environments-v2`): `uv cache clean` deletes them
  (`uv cache prune` kept them here, though uv's docs say it may), so setup prints no path into it. `uv tool install` keeps the tool in `~/.local/share/uv/tools`
  (Windows `%APPDATA%\uv\data\tools`) with the command in `~/.local/bin`. uvx and `uv tool` download a Python when
  none fits (`UV_PYTHON_DOWNLOADS=never` stops it); pip and pipx use the Python they run on.
- uv's and pip's `agon.exe` on Windows is a real launcher program (uv's trampoline, distlib's launcher) that starts
  Python in a job object and passes stdio through *(from their sources)*. But `uvx.exe` itself starts `uv.exe`, which
  starts `agon-arena.exe`: ending `uvx.exe` (TerminateProcess) leaves `uv.exe`, the launcher and Python running while
  Agon's stdin stays open, and they end as soon as it closes, as it does when the app closes or dies. On Linux and
  macOS, ending uvx (SIGTERM) ends Agon at once *(CI, `scripts/check_package.py uvx-kill`, 2026-10-01)*.
- Updating a plugin: Claude Code `claude plugin marketplace update agon`, then `claude plugin update agon@agon`, and a
  restart; Codex `codex plugin marketplace upgrade agon`, then `codex plugin add agon@agon` *(both hands-on with a
  local marketplace)*. Each update installs the new copy in a new folder; the old one stays behind.
- MCP Registry: `server.json` (schema 2025-12-11), `registryType: "pypi"`, `runtimeHint: "uvx"`; the registry checks
  that the package's description contains `mcp-name: io.github.giliandar5-lab/agon` (an HTML comment in the README
  does it), the namespace is case-sensitive, a version is immutable once published, and `mcp-publisher login
  github-oidc` logs a workflow in without a secret.
- PyPI: Trusted Publishing from a GitHub environment (`id-token: write`, `pypa/gh-action-pypi-publish`, Linux only,
  attestations by default); a new project starts from a pending publisher. The project page shows the maintainers'
  user names, not the uploader, and an `Author-email` as a mailto link (so the package has none). PyPI's README
  renderer breaks relative links, keeps `#anchors`, and strips video.
- The claude.ai directory's policy wants a `title` and every applicable hint on each tool, a privacy policy, tool
  descriptions that match what the tools do, and no instructions that make Claude call other software unasked; its
  plugin checklist holds files over 256 KiB (`agon.py`, `test_agon.py`) for a reviewer.
- Brands: the apps are named as they are (Claude Code, OpenAI Codex, Antigravity), never "GPT" as a product, with "not
  affiliated with Anthropic, OpenAI or Google"; `gpt` stays an agent's name in commands.

**CI (GitHub Actions)** *(checked 2026-09-24 in the actions' repositories)*
- Current majors: `actions/checkout@v7`, `actions/setup-python@v7` (node24). `ubuntu-latest` is Ubuntu 24.04,
  `windows-latest` Windows Server 2025, `macos-latest` macOS 26 on arm64.
- Python 3.10 is source-only now: setup-python has 3.10.21 for Linux, but only 3.10.11 for Windows and macOS arm64.
  `python-version: "3.x"` means the newest stable release (3.14 today).
