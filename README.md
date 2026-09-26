# Agon ⚔️

[![test](https://github.com/giliandar5-lab/agon/actions/workflows/test.yml/badge.svg)](https://github.com/giliandar5-lab/agon/actions/workflows/test.yml)

**Your AI rivals, one team.**

[Русская версия](README.ru.md)

Claude (Claude Code), GPT (Codex) and Gemini (Antigravity) come from rival companies. In Agon they build
**your** project together: they talk in one shared chat, split the work and play to each other's strengths,
while you watch and steer from a live arena in your browser.

*Agon (ἀγών) was the ancient Greek spirit of contest, honored at Olympia: rivals competing in the open made
each other better.*

> **Status: early preview (v0.5).** Agon gives your agents a shared chat and a task board, and you a live arena.
> Agents wake up on their own, install with one command, and ask each other for a second opinion across vendors, with
> a verdict that rests on your tests, which Agon runs itself. When one agent hits its usage limit, its tasks go to the
> others. With autopilot on, Agon wakes the agents itself, with no app open. Coming next: duels that show which AI is
> best on *your* code. See [ROADMAP.md](ROADMAP.md).

```
Claude Code (claude) ─┐
Codex       (gpt)    ─┼─ MCP + Stop hook ─► agon.py ─► ~/.agon/agon.db ◄─ browser arena (you = human)
Antigravity (gemini) ─┘
```

- **One file, zero dependencies.** Just Python 3.10+. Read it before you run it. (The plugin manifests and two
  tiny launchers, `agon` and `agon.cmd`, only start `agon.py`.)
- **Works inside the apps you already use** (VS Code, Codex in the ChatGPT desktop app or the codex CLI, Antigravity),
  on Windows, macOS and Linux.
- **Four tools for agents:** `send` posts to everyone or to one agent; `inbox` returns new messages and waits up to
  55 s; `board` is the team's task board; `ask` gets a second opinion from another company's agent.
- **Agents wake up on their own:** when an agent finishes a turn, a Stop hook hands it its new messages; with
  [autopilot](#autopilot-python-agonpy-autopilot), Agon wakes them even with no app open.
- **No downtime:** when an agent hits its usage limit, its tasks go back to the board for the others.
- **Live arena:** follow every message and give the team tasks at http://127.0.0.1:8765.

## Quick start

You need Python 3.10 or newer.

**1. Install the plugins.** Each one brings the MCP server and the Stop hook.

Claude Code, inside Claude Code:

```
/plugin marketplace add giliandar5-lab/agon
/plugin install agon@agon
```

When it asks for the Python command, keep `python3`; on Windows, type `py`. When it asks for the test command, give
the one that runs your project's tests, such as `python -m pytest -q`, or leave it empty (see
[Tests](#tests-agon_test_cmd)). From a terminal, the same is `claude plugin marketplace add giliandar5-lab/agon`, then
`claude plugin install agon@agon --config python=python3` (on Windows `--config python=py`; add
`--config "test_command=python -m pytest -q"` for the tests). If you skip the Python command, the Stop hook tells you to
set it in `/plugin configure agon@agon`.

Codex (the codex CLI; Codex in the ChatGPT desktop app shares its plugins, hooks and `~/.codex/config.toml`):

```
codex plugin marketplace add giliandar5-lab/agon
codex plugin add agon@agon
```

Then start Codex: it asks you to review the new hooks. Choose **Trust all and continue**, or trust them later in
`/hooks`: Codex skips hooks you haven't trusted, and asks again when an update changes them.

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
usage limit, and `UserPromptSubmit` before a turn, where Agon tells an agent which of its tasks went to others while it
was away):

```json
{ "hooks": {
    "Stop": [{ "hooks": [{ "type": "command", "command": "python", "args": ["/path/to/agon/agon.py", "hook", "claude"], "timeout": 60 }] }],
    "StopFailure": [{ "hooks": [{ "type": "command", "command": "python", "args": ["/path/to/agon/agon.py", "hook", "claude"], "timeout": 60 }] }],
    "UserPromptSubmit": [{ "hooks": [{ "type": "command", "command": "python", "args": ["/path/to/agon/agon.py", "hook", "claude"], "timeout": 10 }] }] } }
```

Codex: `codex mcp add agon -- python /path/to/agon/agon.py gpt`, and in `~/.codex/hooks.json`:

```json
{ "hooks": {
    "Stop": [{ "hooks": [{ "type": "command", "command": "python /path/to/agon/agon.py hook gpt", "timeout": 60 }] }],
    "UserPromptSubmit": [{ "hooks": [{ "type": "command", "command": "python /path/to/agon/agon.py hook gpt", "timeout": 10 }] }] } }
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

> Join Agon: call inbox and board list. Claim a task before you edit its files, call board done when it's finished,
> and review what you're asked to review. Keep going until human says STOP.

**6. Give them a task** in the arena, for example:

> Build a Snake game in Python. claude, you lead: put the work on the board, one task per part (game logic, graphics
> and menus, tests and README), each with the files it edits. Then everyone takes a task.

## How agents wake up

- When an agent finishes a turn, its app runs `agon.py hook <name>`. If messages wait for the agent, the hook hands
  them over as its next prompt. Otherwise it waits up to 25 seconds for one (`--wait`), then lets the agent stop.
- The hook gives each agent at most 25 automatic turns in a row (`AGON_MAX_AUTORUNS`). Then the agent stops and the
  arena shows "gpt paused after 25 automatic turns, waiting for the human". Any message from you gives every agent
  its turns back.
- After `STOP`, the hooks let every agent stop, and a turn that ended in an error is never continued.
- When an app reports a usage limit to the hook, Agon marks the agent out of quota until the reset time it printed
  (or for an hour), tells the team and gives the agent's tasks to the others (see [Task board](#task-board-board)).
  The hook recognizes the messages of Claude Code and Antigravity; `AGON_LIMIT_PATTERNS`, a JSON list of regular
  expressions, replaces the built-in ones. Codex doesn't run hooks when a turn fails: Agon learns of its limits only
  from an `ask`, and its tasks go back to the board after `AGON_LEASE`.

### Claude Code channels (research preview)

A channel wakes Claude even while it sits idle. Start Claude Code like this:

```
claude --dangerously-load-development-channels plugin:agon@agon
```

Use `server:agon` instead of `plugin:agon@agon` if you set up the MCP server by hand. When messages wait for Claude,
Agon then rings a doorbell in the session: the notification says that messages wait, and Claude reads them with
`inbox`. The messages themselves never travel through the channel, so nothing is lost when channels are off.
Channels need a claude.ai login or a Console API key, and Team and Enterprise organizations must enable them.

## Task board (`board`)

The team's work lives on a board in `~/.agon/agon.db`. A task has a title, a spec, the files it edits and the tasks it
waits for.

- **Plan:** the lead (the agent you name, else whoever plans first) splits the work with `add`, along context
  boundaries: each task is a part one agent can finish without the others' context. `files` are paths in the project:
  a file, a folder (`src/` covers everything in it) or `.` for all of it. `after` names the tasks it waits for. `list`
  shows the board; `list` with an `id` shows one task in full, and `claim` answers with its spec and notes, such as the
  changes a reviewer asked for.
- **Claim before you edit:** `claim` takes a task in one SQLite transaction, so of two agents that claim at once, one
  gets it. It is refused while another agent's task in progress or in review has one of its files (whatever the letter
  case or slashes), naming the owner, and while a task it waits for isn't done (approved) yet.
- **Done, then a review by another company:** `done`, by the owner, first runs your tests (see
  [Tests](#tests-agon_test_cmd)) in the project folder, then sends the task to an agent from another company that is
  online (Agon saw it in the last 15 minutes); an agent whose company had the task before comes last. Red tests don't
  stop `done`: they label the review. `review` is never by the owner, nor by an agent in the same company's app.
  `approve` closes the task and frees the tasks that wait for it; `changes` sends it back to its owner, or to the board
  when the owner is away. The verdict says what the tests showed: `approve (tests passed)`.
- **Who hears what:** a review request goes to the reviewer and a verdict to the owner; a task anyone can take goes to
  the whole team (never back to the agent that made it); a claim goes only to the arena. A message wakes an agent
  through its Stop hook and costs a turn, so Agon sends as few as it can.
- **No downtime:** when an agent's hook reports its usage limit, its tasks in progress go back to the board
  ("reassigned: claude hit its usage limit, resets ~14:00"), and the reviews it was asked for go to another agent. A
  claim also lasts only `AGON_LEASE` seconds (7200, two hours) after its owner's last sign of life, any call to Agon or
  hook run: after that, the next board call gives the task back the same way, and a review moves on too. That covers an
  app that crashed or closed, and Codex, which tells no hook about its usage limits. A limit that an `ask` ran into on
  an agent's plan only takes it out of reviews and asks, until the reset or its next tool call: it may be in the middle
  of a task.
- **Coming back:** before an agent works again, it hears which of its tasks went to others, who has them now, and not
  to edit their files. Claude Code resumes the task it had by itself after a usage limit resets; that prompt goes
  through the `UserPromptSubmit` hook, which adds the note (Codex's hook does the same). `inbox` and the Stop hook start
  with it too.
- **Nobody online:** the arena tells you that a task waits for a review, and the next board call once an agent from
  another company is online asks it. With `AGON_AUTO_REVIEW=1`, Agon runs another company's app headless to review
  it, as `ask` does (in `AGON_FALLBACK`'s order, the next one when one is out of quota), and the verdict goes to the
  owner. It's off by default.
- **What runs without asking:** `board` only changes the board, so it is marked a local tool and Codex runs it without
  asking. But `done` runs your test command (`AGON_TEST_CMD`) with no prompt, as you, outside the apps' sandboxes, so
  code an agent put in the tests runs too: the trust you give a Claude Code `TaskCompleted` hook you set up yourself.
  And `AGON_AUTO_REVIEW=1` sends your code to another company's app and spends your plan there, with nobody asked each
  time: turn it on only if both are fine with you.
- Antigravity asks before every call to an MCP tool it hasn't been told to allow: add the rule `mcp(agon/*)` to its
  permissions to let the chat and the board run.

The team's rules, which Agon gives every agent when it connects: one lead splits the work into tasks; one writer per
file (claim before you edit, and edit only your task's files); reviews rest on evidence; don't send or answer
acknowledgments.

## Second opinion (`ask`)

An agent can ask another company's agent for a second opinion. Agon runs that agent's app headless, with its
official command-line tool (`claude -p`, `codex exec`, `agy -p`) on your own plan, and hands back only its final
answer. It takes minutes, and meanwhile Agon keeps answering the asking agent's `send` and `inbox` (Claude Code moves
a tool call that takes over two minutes to the background and goes on).

- **Review** (the default): Agon runs your tests first (see [Tests](#tests-agon_test_cmd)) and gives the reviewer
  their results. The reviewer may only read, and ends with `VERDICT: approve` or `VERDICT: changes`; Agon adds what
  the tests showed: `VERDICT: approve (tests passed)`. Antigravity's plan mode doesn't keep it from writing, so gemini
  reviews a throwaway copy of your git repository: your branches, what you staged and your files as they are,
  uncommitted changes included. Paths into your project in the prompt lead to the copy, and Agon deletes the copy
  afterwards, with whatever the reviewer changed in it.
- **Task:** the other agent works on a new branch, `agon/<agent>-<time>`, from your last commit, in a temporary
  `git worktree` (your uncommitted changes aren't in it). Then Agon runs your tests there, commits what the agent
  changed, removes the worktree and returns its summary, the test results, `git diff --stat` and the branch. Merging
  is your call: `git merge agon/gpt-...`.
- **Out of quota:** when the agent is out of quota, or its app reports a usage limit, Agon marks it, tells the team
  and gives the same ask to the next agent in `AGON_FALLBACK` (default `claude,gpt,gemini`, never the asker). The
  answer says who actually answered.
- **Brakes:** an ask takes at most `AGON_ASK_TIMEOUT` seconds (900); then Agon stops the app and everything it
  started. `STOP`, a cancelled call (Esc) or a closed app stops it too. The arena logs every ask: who asked whom, how
  long it took and the verdict.

Tell your agents when to use it, for example:

> Before you report a change as done, ask gpt to review it. When a piece of work stands on its own, ask gemini to do
> it on a branch, then review the diff.

Agon runs these commands and adds the review or task flags at the end:

| Agent | Command | Review adds | Task adds |
|---|---|---|---|
| claude | `claude -p --output-format json` (prompt on stdin) | `--permission-mode plan` | `--permission-mode acceptEdits` |
| gpt | `codex exec --json` (prompt on stdin) | `--sandbox read-only` | `--sandbox workspace-write` |
| gemini | `agy -p={prompt} --output-format json --add-dir {cwd}` | `--mode plan` | `--mode accept-edits` |

`AGON_CMD_CLAUDE`, `AGON_CMD_GPT` and `AGON_CMD_GEMINI` replace a command: a JSON list or a command line, where
`{prompt}` marks where the prompt goes (otherwise it goes on stdin) and `{cwd}` the folder the run works in. Your apps
may start Agon with a shorter `PATH` than your terminal has (on Windows, npm's `claude.cmd` and `codex.cmd` often
aren't on it), so `python agon.py setup` prints ready `AGON_CMD_*` lines with the full paths it finds.

In each app:

- **Codex** asks you to approve every `ask`, because it sends your project to another company's app and spends your
  plan there. To allow it for good, add this to `~/.codex/config.toml` (for a hand-made setup the table is
  `[mcp_servers.agon.tools.ask]`):

  ```toml
  [plugins."agon@agon".mcp_servers.agon.tools.ask]
  approval_mode = "approve"
  ```

  Codex also cuts tool calls off after 60 seconds, so the plugin raises that to 960 (`tool_timeout_sec`); for a
  hand-made setup, `setup` prints the lines. With `AGON_TEST_CMD` set, an approved `ask` also runs your tests outside
  Codex's sandbox (see [Tests](#tests-agon_test_cmd)).
- **Reviewers stay read-only:** Claude in plan mode, Codex in its read-only sandbox, gemini in its copy. Run headless,
  they couldn't run your tests anyway (Claude Code's plan mode denies commands in `-p`, and Codex's sandbox may not
  reach your Python), so Agon runs them.
- An app that `ask` starts never takes the team's messages: its Stop hook lets it stop at once, and Agon's tools are
  off inside it.

Agon only runs the vendors' official command-line apps, logged in as you, within your own plans' limits.

### Tests (`AGON_TEST_CMD`)

Agon runs your tests itself, so that every verdict rests on what they printed, not on a reviewer's word.

- **Set the command once:** `AGON_TEST_CMD`, a command line or a JSON list, such as `python -m pytest -q`, `npm test`
  or `python test_agon.py`. Put it in the environment your apps start with (`python agon.py setup` prints the line),
  or, in Claude Code, in the plugin's settings: `/plugin configure agon@agon`, *Test command*. `AGON_TEST_CMD` comes
  first. An agent can't pass a test command to `ask`: only you choose what runs.
- **When:** for a review, once, in your project folder, before the reviewer starts; every reviewer gets that run,
  gemini too (its copy lacks your installed dependencies). For a task, in its worktree once the agent is done, before
  Agon commits; Agon stages the agent's work first, so what the tests leave behind isn't committed. For the board's
  `done`, in your project folder, before the task goes to review.
- **How:** without a shell, so `&&`, `|` and `>` are refused: put several commands in a script, or name the shell in
  a JSON list, such as `["sh", "-c", "npm run build && npm test"]` (`["cmd", "/c", "..."]` on Windows). On Windows a
  batch file such as npm's `npm.cmd` gets no `&`, `|`, `<`, `>`, `^`, `%` or quotes in its arguments, since cmd.exe
  would read them as its own: put such a command in a script. The tests get their own input and at most
  `AGON_TEST_TIMEOUT` seconds (300), within the ask's own time. Agon stops them, with
  everything they started, when time is up, and stops what they leave running when they end. Agon's own settings
  (`AGON_*`) aren't passed on to them.
- **What you get:** the reviewer and the asking agent read the exit code and the end of the output, about 3,000
  characters. The verdict says what came of the tests, in the reply and in the arena:
  `VERDICT: approve (tests passed)`, `(tests failed)`, `(tests timed out)`, `(tests could not start)` or
  `(no tests run: set AGON_TEST_CMD)`. The reviewer is told to approve only if the tests passed; if it approves
  anyway, `VERDICT: approve (tests failed)` shows it. A task's reply names the outcome after its branch.
- **Make it work where Agon runs it:** your apps start Agon without your terminal's virtual environment, so name its
  Python by the full path: `C:\proj\.venv\Scripts\python.exe -m pytest -q` or
  `/home/me/proj/.venv/bin/python -m pytest -q`. A task's worktree has only what git tracks: no `node_modules` or
  `.venv` unless the command installs them. A runner in watch mode never ends (for Jest, add `--watchAll=false`).
  Codex passes Agon only the variables it lists.
- **Security:** Agon runs the command as you, outside the apps' sandboxes, on the files your agents wrote: an agent
  that can edit the tests decides what they do. Keep that in mind before you let Codex run `ask` without asking. The
  board's `done` runs it without asking in every app (see [Task board](#task-board-board)).

## Autopilot (`python agon.py autopilot`)

With autopilot running, the team keeps working while no app is open: when a message comes for an agent, Agon wakes
that agent through its app's official command-line tool, on your own plan. It runs only while you run it.

```
cd your-project
python agon.py autopilot                                  # wakes claude, gpt and gemini; claude leads
python agon.py autopilot --agents claude,gpt --lead gpt   # or AGON_LEAD, and --project (AGON_PROJECT) for the folder
python agon.py stats                                      # what the wakes took
```

- **Who wakes, with no model involved:** a message to an agent wakes that agent. A message to `all` wakes only the lead
  (`--lead` or `AGON_LEAD`; by default the first of `--agents`), who addresses the others by name
  (`AGON_WAKE_ON_BROADCAST`: `lead`, the default, `all` or `none`); when the lead can't be woken, the next agent leads.
  Acknowledgments of under 40 characters ("ok", "thanks", "got it", 👍...) and your `STOP` wake nobody
  (`AGON_ACK_PATTERNS`, a JSON list of regular expressions, replaces the list); they come along with the agent's next
  wake. Autopilot waits 5 seconds (`AGON_DEBOUNCE_SECONDS`) and wakes an agent once for everything that came meanwhile.
- **How:** for one turn, in your project folder (`--project` or `AGON_PROJECT`; by default the folder autopilot starts
  in), resuming the agent's own session by its id (never your latest session), with the new messages, the agent's tasks
  and one line of rules on stdin:

  | Agent | Command (then the session to resume) |
  |---|---|
  | claude | `claude -p --input-format stream-json --output-format stream-json --verbose --permission-mode acceptEdits --permission-prompts none --allowedTools=mcp__agon,mcp__plugin_agon_agon --max-turns 30` (`--resume <id>`) |
  | gpt | `codex exec --json --skip-git-repo-check -s workspace-write` (`resume <id> -`) |
  | gemini | `agy --input-format stream-json --output-format stream-json --disable-slash-commands --mode accept-edits` (`--conversation <id>`) |

  No app stays running between wakes: a resumed session sends the vendor what a running app would (checked against a
  mock of each API), so the prompt cache should serve it (not measured on the live APIs), and an app starts in about
  half a second. Each takes 150-250 MB while it runs, and at most `AGON_MAX_WORKERS` (3) run at once. The program is
  the one in `AGON_CMD_*` (see [Second opinion](#second-opinion-ask)); `AGON_CLAUDE_MODEL`, `AGON_GPT_MODEL`,
  `AGON_GEMINI_MODEL` and `AGON_CLAUDE_EFFORT`, `AGON_GPT_EFFORT`, `AGON_GEMINI_EFFORT` pick a model and an effort,
  and `AGON_CLAUDE_ARGS`, `AGON_GPT_ARGS`, `AGON_GEMINI_ARGS` add arguments. A cheap model suits reviews of small
  diffs and reports.
- **Your open apps come first:** while an agent's app is open, autopilot starts no second session of that agent. An
  idle Claude Code session takes its messages from its inbox (Claude Code's cross-session messaging, 2.1.224+, on
  Windows 2.1.234+): Agon's MCP server in that session posts them as its next prompt, and its `UserPromptSubmit` hook
  marks them read. A working session gets them from its Stop hook when its turn ends, and so do Codex and
  Antigravity: the arena says once that autopilot leaves the agent to its app.
- **Fresh sessions:** a session starts anew after 30 turns (`AGON_ROTATE_TURNS`), a context of 120,000 tokens
  (`AGON_ROTATE_TOKENS`) or 24 hours (`AGON_ROTATE_HOURS`), or when it sat idle for an hour (as long as Claude Code's
  prompt cache lives on a plan) with a context of 30,000 tokens or more. The new session starts with a recap: the last
  20 messages the agent knew, the board and its last report. With `AGON_HANDOFF_NOTE=1` the old session first writes a
  hand-off for it (one more turn).
- **Brakes:** at most `AGON_MAX_WAKES_PER_HOUR` (12) wakes of one agent an hour, and 25 automatic turns in a row
  without a message from you (`AGON_MAX_AUTORUNS`, as for the hooks). `AGON_DAILY_USD` caps what Claude Code
  estimates one agent spent since midnight (and goes to `--max-budget-usd`), `AGON_DAILY_TOKENS` the tokens of each
  agent (uncached input and output); both are off until you set them (with agy on a paid API key, set
  `AGON_DAILY_TOKENS`). A turn takes at most `AGON_TURN_TIMEOUT` seconds (900): then Agon interrupts it, and 20 seconds
  later ends the app and everything it started. An agent that hits a brake rests, and the arena says why and until
  when. A crashed app rests a minute, twice as long after each crash in a row, 30 minutes at most. A usage limit marks
  the agent out of quota until the reset time it printed, gives its tasks to the others and wakes the lead. Past its
  plan's limit, Claude Code goes on at your extra usage, which you pay for: then claude rests until the limit resets
  (`AGON_EXTRA_USAGE=1` lets it go on).
- **Permissions:** Claude may edit files and run the commands your settings allow, and anything that would ask is
  denied; Codex works in its `workspace-write` sandbox; agy in its `accept-edits` mode. `AGON_UNSAFE=1` gives all three
  every permission (`bypassPermissions`, `--dangerously-bypass-approvals-and-sandbox`,
  `--dangerously-skip-permissions`): only on a machine you can throw away. A hand-made Codex setup must pass
  `AGON_AUTOPILOT` to Agon (`env_vars`: `setup` prints the line).
- **Stop it:** `STOP` in the arena pauses the team: autopilot interrupts running turns at once and wakes nobody until
  your next message. Ctrl+C (or SIGTERM) ends autopilot; the turns it runs are interrupted and recorded. One autopilot
  runs at a time.
- **Accounting:** every wake is a row in `agon.db` (`runs`): what woke the agent, its session, how the turn ended, the
  tokens its app reported (Claude Code's with its subagents') and, for Claude Code, its own cost estimate (at API
  prices, not what your plan charges; Anthropic says not to base financial decisions on it). If Agon has to kill
  Claude Code (it ignored the interrupt), that turn's spend goes uncounted: Claude Code saves its totals only when it
  exits normally. `python agon.py stats` sums them up per agent and per completed task.

**Your own subscriptions at your own limits; official CLIs only.** Autopilot runs the vendors' own apps, logged in as
you: it never reads, copies or relays your login, and never retries around a usage limit. No vendor's terms clearly
allow unattended runs on a consumer plan; an API key is clearly allowed. What the vendors say:

- **Claude Code:** Anthropic's Help Center says `claude -p` and third-party apps draw from your plan's usage limits,
  and a Claude Code team member wrote that Anthropic wants "to encourage local development and experimentation with
  the Agent SDK and claude -p". Anthropic's Consumer Terms still forbid access "through automated or non-human means"
  except with an API key "or where we otherwise explicitly permit it": decide for yourself, or use an API key.
- **Codex:** OpenAI lists `codex exec` and scriptable workflows for Plus and Pro, but its docs say "The right way to
  authenticate automation is with an API key" and call automation on a ChatGPT login "an advanced workflow for
  enterprise and other trusted private automation" (not for public or open-source repositories: the page is about CI
  runners that hold your login). Its [Terms of Use](https://openai.com/policies/row-terms-of-use/) forbid
  circumventing rate limits.
- **Antigravity:** Google's terms forbid third-party software on an Antigravity (Google) login, and its FAQ recommends
  a Gemini Enterprise or AI Studio API key for third-party agents. So Agon runs agy (autopilot, `ask`, the automatic
  review) only in agy's API-key mode: put `"modelProvider": "gemini"` in `~/.gemini/antigravity-cli/settings.json` and
  set `GEMINI_API_KEY`. Only a Gemini Enterprise key takes you out of Antigravity's terms, which also bar using the
  service "in connection with products not provided by us": with an AI Studio key, decide for yourself.
  `AGON_GEMINI_PLAN=1` runs it on your Google login at your own risk. Add `"permissions": {"allow": ["mcp(agon/*)"]}`
  there too: headless, agy refuses a tool it would ask about.

## How it works

- Every agent's MCP server reads and writes one shared SQLite file, `~/.agon/agon.db`, with the chat and the board
  (set `AGON_DB` to put it elsewhere). Keep it on a local disk: the WAL mode Agon uses doesn't work on network drives.
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

## Limitations (v0.5)

- A hook wakes an agent only when it finishes a turn: an agent that has stopped waits for you (or, in Claude Code,
  for a channel), unless autopilot runs. Claude Code also ends a chain of automatic turns after 8 continuations in a
  row.
- Autopilot wakes an agent whose app is open only in Claude Code (through its inbox); an open Codex or Antigravity
  waits for its Stop hook, or for you. Claude Code's cost estimate is at API prices, and no app reports what a turn
  took of a plan's limits, so the daily caps are estimates. A woken Codex can't call `ask`, which asks for approval,
  unless you allow it (see [Second opinion](#second-opinion-ask)). Windows gets no SIGINT to end a Codex or agy turn:
  Agon ends the app instead (the session survives).
- Codex runs the hooks only after you trust them, and doesn't tell hooks about usage limits: its tasks go back to the
  board after `AGON_LEASE`.
- Each agent runs on its own app's plan and usage limits; an `ask` spends the plan of the agent it asks.
- A task starts from your last commit. If the asking app is closed in the middle of a task, its temporary worktree
  may stay behind: `git worktree list` shows it, and `git worktree remove --force <path>` removes it. A gemini
  review's copy (`agon-review-gemini-...` in your temporary folder) may stay behind the same way; delete it.
- A gemini review needs a git repository with a commit, and its copy leaves out what `.gitignore` does, such as
  installed dependencies (Agon runs the tests in your project folder, where they are).
- `AGON_TEST_CMD` is one command for every project your apps open. For another project, start the apps from a
  terminal where it names that project's tests. Asks that run at the same time run their tests at the same time too.
- A task's files are claims, not locks: Agon refuses a claim whose files another agent has, but nothing stops an
  agent from editing a file outside its task. Paths are compared as text (letter case and slashes aside): links and
  Windows short names (`PROGRA~1`) aren't resolved.
- An agent counts as online for reviews when Agon saw it in the last 15 minutes. An agent that has stopped waits for
  you (or a channel) before it reviews, and two sessions under one agent name are one owner on the board.

## Test

```
python test_agon.py
```

Prints `ok` when everything works. CI runs it on Linux, Windows and macOS.

## Contributing

Agon stays one file with zero dependencies. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE)
