# Phase 5 — Autopilot (full specification)

This is Phase 5 of [ROADMAP.md](../ROADMAP.md). Researched 2026-09-24; re-verify the platform facts before coding.


## Goal

With only `python agon.py autopilot` running, the team keeps working: when a message or task appears for an
agent, Agon wakes that agent through its vendor's **official CLI** on the user's own subscription. Idle
costs nothing (no model calls, ~0% CPU, ~20 MB RAM). Every wake-up is rule-triggered, batched, budgeted and
logged. Opt-in only.

## Verified facts this phase relies on (checked 2026-09-24; re-verify)

- **Policies.** Google staff: launching the official `agy` binary as a local child process in headless mode
  on cached credentials "is a supported workflow" and consumes the same entitlements as interactive use
  (discuss.ai.google.dev/t/183051). Anthropic Help Center (June 15, 2026): `claude -p`, the Agent SDK and
  third-party apps "still draw from your subscription's usage limits"; the separate Agent SDK credit is paused.
  Extracting OAuth tokens or calling vendor endpoints directly is forbidden by all three vendors — Agon only
  ever runs the official binaries. OpenAI recommends API keys for CI but does not forbid `codex exec` on a
  ChatGPT plan; document this as "allowed today, at your own plan's limits".
- **Claude Code inbox socket.** Every interactive or `-p` session (not `--bare`) binds an inbox: Unix socket on
  macOS/Linux, named pipe `\\.\pipe\LOCAL\cc-msg-<hex>` on Windows. Hooks receive its path and token as
  `CLAUDE_CODE_MESSAGING_SOCKET` and `CLAUDE_CODE_MESSAGING_TOKEN`. "When the receiving session is idle, Claude
  Code starts a new turn with the message." Windows requires the auth line first. Wire format seen in the wild
  (verify against CLI 2.1.281): line 1 `{"type":"auth","token":"…"}`, line 2
  `{"type":"user","message":{"role":"user","content":"…"},"priority":"now"}`. A session in `acceptEdits`/`auto`
  mode delivers such a message; a `bypassPermissions` session holds it for approval. Loops are throttled by
  Claude Code itself (repeat drop, 50-message queue). Requires v2.1.234+ on Windows.
- **Claude headless.** `claude -p --input-format stream-json --output-format stream-json --verbose
  --replay-user-messages` keeps one process alive across turns; stdin line
  `{"type":"user","message":{"role":"user","content":"…"}}`; each turn ends with a `result` event carrying
  `session_id`, `total_cost_usd`, `usage` (`cache_read_input_tokens` …), `is_error`, `permission_denials`.
  Second turn in the same process paid 60 cache-creation tokens instead of 11,931 (measured by a third party).
  Flags: `--resume <id>` (works from any directory), `--max-turns`, `--max-budget-usd`, `--permission-mode
  acceptEdits|auto|dontAsk`, `--permission-prompts none` (v2.1.259+), `--allowedTools`, `--append-system-prompt`,
  `--model`. `--bare` does not use the subscription login (API key only) — do not use it. SIGTERM exits 143 and
  leaves the turn unfinished; SIGINT ends the turn. Retryable API errors appear as `system/api_retry` events
  with `error` in {`rate_limit`, `overloaded`, `billing_error`, …}. Subscription cache TTL: reported 1 h for
  the main conversation, 5 min for subagents (verify).
- **Codex headless.** No persistent stdin mode; one process per turn: `codex exec --json -` (prompt on stdin),
  continue with `codex exec resume <SESSION_ID> --json -`; `-o <file>` writes the final message; `-m <model>`
  and `-c model_reasoning_effort=low|medium|high|xhigh`; `--sandbox read-only|workspace-write`;
  `--ephemeral` disables session files (incompatible with resume). `turn.completed.usage` is **cumulative for
  the session** (`input_tokens`, `cached_input_tokens`, `output_tokens`, `reasoning_output_tokens`) — diff
  it per turn. Transient `error` events "Reconnecting… n/5" are not fatal. Codex hooks are not invoked when a
  usage limit ends the turn; detect limits from the JSON/exit code instead.
- **Antigravity headless.** `agy -p --input-format stream-json --output-format stream-json --add-dir <project>
  --disable-slash-commands --mode accept-edits [--conversation <id>]` keeps one process alive; a turn per stdin
  line; result JSON has `status` in {SUCCESS, ERROR, CANCELED, INTERRUPTED, INVALID, WAITING, RUNNING} and
  `denied_actions`; structured `AGY_ERROR: {...}` line on stderr with a retryability flag (exit code 3).
  `--conversation <id>` with an unknown id silently starts a new conversation (idempotent). Conversations are
  scoped to the working directory. Quota text in the binary: "You have exhausted your quota on this model."
  Model ids encode effort (`--effort` exists on some versions). Startup takes several seconds.
- **Memory.** Reported footprints per process: Claude Code ~390–560 MB, `agy` ~444 MB, Codex unknown (Rust,
  smaller). Therefore no worker stays alive while idle.
- **Research.** Cache reads still count against subscription limits, only less (Anthropic Help Center). Long
  contexts degrade all 18 tested frontier models ("Context Rot", Chroma 2025); practitioners rotate sessions via
  structured hand-offs instead of relying on auto-compaction. Cheap-first routing/cascades keep quality at a
  fraction of cost (FrugalGPT: up to 98% cost cut; RouteLLM: 85% cut at 95% quality). Multi-agent chatter is
  mostly redundant: pruning cut tokens 28–73% (AgentPrune, ICLR 2025); an LLM-free runtime filter cut 29.7%
  (SupervisorAgent, ICLR 2026); "acknowledgment" messages are the first thing to drop.

## Design

**1. Wake-up ladder (cheapest first, per agent)**
1. **Live session inbox** (Claude Code only): if the agent's Stop/SessionStart hook has registered an inbox
   socket, post the wake-up there — no new process, warm context and cache. Hook payload lets Agon store
   `{socket, token, pid, cwd, registered_at}` in `agents`. Liveness = successful connect; stale entries are
   dropped. Message = the same text `inbox` would return (Agon prefix + messages), so no extra tool call.
2. **Warm worker**: a headless process kept alive `AGON_WARM_SECONDS` (default 90) after its last turn, then
   exited to free memory. Claude and agy use their persistent stdin modes; Codex has none, so Codex always uses
   step 3 with `resume`.
3. **Cold start**: spawn the CLI resuming the agent's saved session (`--resume`, `codex exec resume`,
   `--conversation`), or a fresh session with Agon's recap when rotation is due.

**2. Rule-based triage — zero tokens**
- Wake agent X only when: a message is addressed to X; a task becomes claimable for X or is assigned/returned
  to X; a review is requested from X.
- Broadcasts (`all`) wake only the lead (`AGON_LEAD`); the lead addresses others explicitly. Override with
  `AGON_WAKE_ON_BROADCAST=lead|all|none`.
- Never wake for acknowledgments: messages under 40 characters matching `^(ok|okay|thanks|thank you|got it|👍|
  ack|noted|done)[.!]?$` (case-insensitive, configurable `AGON_ACK_PATTERNS`).
- Debounce: collect events per agent for `AGON_DEBOUNCE_SECONDS` (default 5), then one wake with everything
  pending in a single prompt. Prefer waking while the vendor cache is still warm.

**3. Budgets and brakes (hard, per agent)**
- `AGON_MAX_WAKES_PER_HOUR` (default 12). Exceeded → agent parked, human notified in the arena.
- Daily caps: `AGON_DAILY_USD` for Claude (from `total_cost_usd`, plus `--max-budget-usd` per run) and
  `AGON_DAILY_TOKENS` for Codex/agy (from their usage fields). Exceeded → parked until local midnight.
- Per-turn: `--max-turns` (Claude, default 30), `AGON_TURN_TIMEOUT` (default 900 s): SIGINT/turn end → 20 s →
  SIGTERM/`taskkill /T` on Windows.
- Existing brakes still apply: STOP pauses autopilot immediately (no new wakes, running turns interrupted),
  `AGON_MAX_AUTORUNS` continuation budget, out-of-quota parking with reset time.

**4. Session hygiene (against context rot)**
- Reuse the agent's session across wakes (cache-cheap) but rotate when any of: context estimate >
  `AGON_ROTATE_TOKENS` (default 120k, from usage fields), turns > `AGON_ROTATE_TURNS` (30), age >
  `AGON_ROTATE_HOURS` (24). Rotation = fresh session started with Agon's recap (last 20 messages + board
  state + the agent's own last report). Optional `AGON_HANDOFF_NOTE=1` asks the old session for a ≤ 300-word
  hand-off first (one extra turn).
- The prompt for each wake stays small: pending messages, the agent's open tasks, and one line of rules.

**5. Model and effort per role (cheap-first)**
- Per-agent model/effort knobs: `AGON_CLAUDE_MODEL`, `AGON_GPT_MODEL`, `AGON_GEMINI_MODEL`,
  `AGON_*_EFFORT` mapped to `--model`, `-m/-c model_reasoning_effort`, agy model ids. Defaults: each vendor's
  default. Documented recipe: cheap models for reviews of small diffs and for reports, strong models for
  implementation. No automatic escalation in this phase (measure first).

**6. Permissions and safety**
- Defaults: Claude `--permission-mode acceptEdits --permission-prompts none`, Codex `--sandbox
  workspace-write`, agy `--mode accept-edits`. `bypassPermissions`/`danger-full-access`/
  `--dangerously-skip-permissions` only when the user sets `AGON_UNSAFE=1`. Extra CLI args via
  `AGON_CLAUDE_ARGS`, `AGON_GPT_ARGS`, `AGON_GEMINI_ARGS`.
- Workers run in the project directory (`AGON_PROJECT`), the same folder the team shares; never in worktrees
  except duels.
- Agent messages remain untrusted text; autopilot only forwards Agon's own inbox format.
- One worker per agent at a time; global cap `AGON_MAX_WORKERS` (default 2) to bound RAM.

**7. Supervision and accounting**
- `python agon.py autopilot [--lead claude] [--agents claude,gpt,gemini]` runs one supervisor thread that
  sleeps on `wait_for_change()` (≈0% CPU) and a queue per agent. Crash → agent offline, exponential backoff
  1→30 min. Limit detection from outputs (Claude `api_retry`/result text, Codex `turn.failed`/exit code, agy
  `AGY_ERROR`/status) → `out_of_quota_until` + task reassignment (Phase 4) + wake fallback agents.
- Every wake logs: trigger, agent, session id, duration, tokens (in/cached/out), estimated USD, result status,
  into a `runs` table; `python agon.py stats` prints per-agent totals and cost per completed task; the arena
  (next phase) shows them.
- Windows: process trees are killed with `taskkill /F /T`; stdin/stdout are binary UTF-8; no `python3`
  assumption (use `sys.executable`).

**8. Non-goals**
- No "sleep-time compute" (agents thinking while idle) — it burns limits with no user demand.
- No always-on workers, no OS service/daemon installer, no token extraction, no custom API clients.

## Research first (do this before coding, list results in the PR)

1. Claude Code inbox socket: confirm the wire format (auth line + user message line) against CLI 2.1.281 on
   Linux, and the named-pipe variant on Windows from the binary; confirm that an idle interactive session and a
   `-p` stream-json session both start a new turn on such a message; confirm which env vars the Stop hook and
   the MCP server child receive (`CLAUDE_CODE_MESSAGING_SOCKET`, `CLAUDE_CODE_MESSAGING_TOKEN`).
2. Claude `-p` stream-json: exact `result` fields for cost/usage, `is_error` text on usage limits, behavior of
   `--max-budget-usd` on subscription auth, whether Stop hooks and the project's `.mcp.json` load in `-p`.
3. Codex: exact `turn.failed`/`error` payloads and exit codes on usage limits and on network loss; whether
   `resume` keeps the prompt cache; `-c model_reasoning_effort` accepted values on 0.156+.
4. agy: `AGY_ERROR` schema, `status` values, quota text, `--effort` availability, memory of one stream-json
   process at idle and during a turn.
5. Measure RSS (idle, during a turn) and turn latency for each CLI on Linux; record in ROADMAP.
6. Cache TTL per vendor for subscription auth (Claude 1 h vs 5 min; Codex `cached_input_tokens` behavior; agy
   unknown) → choose `AGON_WARM_SECONDS` and debounce defaults from data.
7. Look at how `hydra`, `unsnooze`, `cephalopod-ai/tagteam` and `salimfadhley/agent-inbox` drive these CLIs and
   detect limits; reuse only what is verified.

## Tests (fake CLIs via `AGON_CMD_*`, fake inbox socket server)

Wake on addressed message; no wake on acknowledgment; broadcast wakes only the lead; debounce merges three
messages into one wake; warm worker serves two turns in one process; cold start resumes the saved session;
rotation after N turns starts a fresh session with a recap; wakes-per-hour and daily caps park the agent and
post a notice; STOP interrupts a running turn; crash → backoff; limit output → out-of-quota + reassignment +
fallback wake; usage/cost recorded in `runs`; inbox-socket wake delivered to a mock server (auth line first);
Windows process-tree kill (skipped on Linux CI).

## Done means

All of the above tested, `python test_agon.py` prints `ok`, measurements recorded, README section
"Autopilot" with the exact commands, budgets, policy notes ("uses your own subscriptions at your own limits;
official CLIs only") and how to stop everything (STOP or Ctrl+C).
