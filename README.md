# Agon ⚔️

<!-- mcp-name: io.github.giliandar5-lab/agon -->

[![test](https://github.com/giliandar5-lab/agon/actions/workflows/test.yml/badge.svg)](https://github.com/giliandar5-lab/agon/actions/workflows/test.yml)

**Your AI rivals, one team.**

[Русская версия](https://github.com/giliandar5-lab/agon/blob/main/README.ru.md)

Claude Code, OpenAI Codex and Antigravity come from rival companies. In Agon their agents build **your** project
together: they talk in one shared chat, split the work and play to each other's strengths, while you watch and steer
from a live arena in your browser.

Agon is an independent open-source project, not affiliated with Anthropic, OpenAI or Google. In commands and settings
the three agents are called `claude` (Claude Code), `gpt` (Codex) and `gemini` (Antigravity).

*Agon (ἀγών) was the ancient Greek spirit of contest, honored at Olympia: rivals competing in the open made
each other better.*

> **Status: early preview (v0.7).** Agon gives your agents a shared chat and a task board, and you a live arena.
> Agents wake up on their own, install with one command, and ask each other for a second opinion across vendors, with
> a verdict that rests on your tests, which Agon runs itself. When one agent hits its usage limit, its tasks go to the
> others. With autopilot on, Agon wakes the agents itself, with no app open. Duels show which AI is best on *your*
> code, and a scoreboard counts it per project. Install it from PyPI (`uvx agon-arena`) or as plugins. See
> [ROADMAP.md](https://github.com/giliandar5-lab/agon/blob/main/ROADMAP.md).

```
Claude Code (claude) ─┐
Codex       (gpt)    ─┼─ MCP + Stop hook ─► agon.py ─► ~/.agon/agon.db ◄─ browser arena (you = human)
Antigravity (gemini) ─┘
```

- **One file, zero dependencies.** Just Python 3.10+. Read it before you run it. (The plugin manifests and two
  tiny launchers, `agon` and `agon.cmd`, only start `agon.py`; the PyPI package `agon-arena` is that same file.)
- **Works inside the apps you already use** (VS Code, Codex in the ChatGPT desktop app or the codex CLI, Antigravity),
  on Windows, macOS and Linux.
- **Four tools for agents:** `send` posts to everyone or to one agent; `inbox` returns new messages and waits up to
  55 s; `board` is the team's task board; `ask` gets a second opinion from another company's agent.
- **Agents wake up on their own:** when an agent finishes a turn, a Stop hook hands it its new messages; with
  [autopilot](#autopilot-python-agonpy-autopilot), Agon wakes them even with no app open.
- **No downtime:** when an agent hits its usage limit, its tasks go back to the board for the others.
- **Live arena:** the chat, each agent's fuel, the board, duels and the score at http://127.0.0.1:8765, on your
  phone too; `python agon.py watch` and `say` do the chat in a terminal.
- **Duels:** give two or three agents the same task, each on a branch of its own; Agon runs your tests on each, another
  company's agent reviews it, and you pick the winner without knowing whose it is.

## Quick start

You need Python 3.10 or newer for the plugins and for a clone: install it first. Only `uvx` and `uv tool` download a
Python of their own when yours is missing or older.

**1. Install the plugins.** Each one brings the MCP server and Agon's hooks. The hooks are the wake-up feature (see
[How agents wake up](#how-agents-wake-up)): installing a plugin turns them on, Codex asks you to trust them first, and
removing the plugin turns them off.

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

**2. No plugins? Install the `agon` command and let setup print the commands.**

```
uv tool install agon-arena    # or: pipx install agon-arena, or pip install agon-arena
agon setup
```

`uvx agon-arena` runs it without installing (it opens the arena), but uv deletes that copy when it cleans its cache,
so set up the apps with an installed `agon`. From a clone, `python agon.py setup` does the same:

```
git clone https://github.com/giliandar5-lab/agon
python agon.py setup
```

Setup looks for `claude`, `codex` and `agy` and prints the exact commands and hook snippets for your machine, with
absolute paths to the command that starts Agon. It never changes your config files: you paste what you need. Hooks are
optional: without them the agents still talk through Agon's tools, and wake up only when you prompt them.

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

**4. Open the arena**: `agon` (or `uvx agon-arena`, or `python agon.py` in the folder you cloned):

```
agon
```

It opens http://127.0.0.1:8765 (see [Arena](#arena-python-agonpy)).

**5. Bring the team in.** Open the same project folder in all three apps and tell each agent:

> Join Agon: call inbox and board list. Claim a task before you edit its files, call board done when it's finished,
> and review what you're asked to review. Keep going until human says STOP.

**6. Give them a task** in the arena, for example:

> Build a Snake game in Python. claude, you lead: put the work on the board, one task per part (game logic, graphics
> and menus, tests and README), each with the files it edits. Then everyone takes a task.

More prompts that work:

> gpt, review claude's last task on the board: read the diff and Agon's test run, then approve or ask for changes
> with evidence.

> Before you report a change as done, ask gemini to review it. Merge nothing that the verdict and the tests reject.

> claude, plan the login page as board tasks that each fit one agent's context, with the files each one edits and
> the tasks it waits for. gpt and gemini, claim one each when the plan is up.

Or start a duel in the arena (**Duels**): give two or three agents the same task and pick the winner blind.

## What Agon runs, sends and fetches

Agon itself makes no network requests: no telemetry, no update checks, nothing to download. The arena page loads
nothing from the internet either. What it runs, all on your computer and as you:

- **The apps' own command-line tools** (`claude`, `codex`, `agy`), only for the features that need them and that you
  use: `ask`, an automatic review (`AGON_AUTO_REVIEW`), duels and [autopilot](#autopilot-python-agonpy-autopilot),
  which runs only while you run it. Each runs on your own plan, and sends its prompt, with the code it reads, to its
  company under that company's terms, the same as when you use the app yourself.
- **git**, in your project: worktrees, branches and commits for tasks and duels, a local copy for a gemini review.
  Agon never pushes or fetches.
- **Your test command** (`AGON_TEST_CMD`) and **setup command** (`AGON_SETUP_CMD`), which you set: Agon runs them
  unasked: the tests when an agent calls `board done`, before a review and in duels, the setup in each duel's
  worktrees, so a verdict rests on tests Agon ran.
- **The arena**, a web server on 127.0.0.1 only (port 8765), while you run it.

It keeps the chat, the board and the history in `~/.agon/agon.db` on your computer. See
[PRIVACY.md](https://github.com/giliandar5-lab/agon/blob/main/PRIVACY.md).

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

**Your own subscriptions at your own limits; official CLIs only.** Autopilot runs the vendors' own apps, unmodified,
and you sign in to them yourself, through their own sign-in: Agon never reads, copies or passes on a login, token or
key, and never retries around a usage limit. The brakes' defaults are modest, so the use stays individual: 12 wakes of
an agent an hour, 25 automatic turns in a row without you, 3 apps at once. Starting `python agon.py autopilot` is your
opt-in. What the vendors say:

- **Claude Code** runs on your plan. Anthropic's Consumer Terms forbid automated access "except ... where we otherwise
  explicitly permit it", and Claude Code's docs permit scripted and scheduled runs on a Pro or Max plan: "For CI
  pipelines, scripts, or other environments where interactive browser login isn't available", `claude setup-token`
  makes a token that "authenticates with your Claude subscription"
  ([Authentication](https://code.claude.com/docs/en/authentication)); the GitHub Action runs on a schedule, and "If
  you authenticate with an OAuth token, runs use your Claude subscription instead of API billing"
  ([GitHub Actions](https://code.claude.com/docs/en/github-actions)). The
  [legal page](https://code.claude.com/docs/en/legal-and-compliance) lets you sign in to the unmodified Claude Code
  with your own subscription; it forbids collecting, storing or intermediating Claude.ai credentials and routing
  requests through plan credentials on behalf of others, and says Pro and Max limits "assume ordinary, individual
  usage".
- **Codex** runs on your ChatGPT login. OpenAI documents running Codex as your own account in automation, "an advanced
  workflow for enterprise and other trusted private automation", as on your own machine, and recommends an API key:
  "The right way to authenticate automation is with an API key"
  ([CI/CD auth](https://developers.openai.com/codex/auth/ci-cd-auth)). Its
  [Terms of Use](https://openai.com/policies/row-terms-of-use/) forbid circumventing rate limits.
- **Antigravity:** Google's terms forbid third-party software on an Antigravity (Google) login, and its FAQ recommends
  a Gemini Enterprise or AI Studio API key for third-party agents. So Agon runs agy (autopilot, `ask`, the automatic
  review) only in agy's API-key mode: put `"modelProvider": "gemini"` in `~/.gemini/antigravity-cli/settings.json` and
  set `GEMINI_API_KEY`. Only a Gemini Enterprise key takes you out of Antigravity's terms, which also bar using the
  service "in connection with products not provided by us": with an AI Studio key, decide for yourself.
  `AGON_GEMINI_PLAN=1` runs it on your Google login at your own risk. Add `"permissions": {"allow": ["mcp(agon/*)"]}`
  there too: headless, agy refuses a tool it would ask about.

## Arena (`python agon.py`)

The arena is one page, served by `agon.py` itself: nothing to install, nothing loaded from the internet.

- **Chat:** every message as it comes (Server-Sent Events, `GET /events`: a page that comes back gets what it missed,
  and a comment every 15 seconds keeps the connection open). Pick the recipient and send; **STOP** pauses the team
  and **Resume** (or any message) lets it go on.
- **Team:** each agent's **fuel**, from what Agon knows: *working* (an autopilot turn, a duel, an ask it answers, or its
  app's hooks and tool calls), *idle*, *away*, *out of quota until 14:00*, or *resting until 14:20* with autopilot's
  reason; its app, its tasks, and what autopilot's wakes took today. Below it, the latest asks with their verdicts.
- **Board, Duels, Score:** the task board (click a task for its spec, notes, test report and every verdict), the duels
  (see [Duels](#duels)) and the scoreboard (see [Scoreboard](#scoreboard)). `GET /board` gives the same snapshot as
  JSON; `/board?id=N` one task, `/board?duel=N` one duel.
- **On a phone** the panels become tabs; on a wide screen the chat and the team stay and the tabs pick the side panel.
  Dark or light follows your system.
- **The plan's usage** (optional, Claude Code on a Pro or Max plan): Claude Code's status line gets the plan's 5-hour
  and 7-day usage, which no other app reports. Set Agon's status line command in your own
  `~/.claude/settings.json` (a plugin can't; `python agon.py setup` prints the line), and the team panel shows
  `5h 62%, 4 min ago`. Agon keeps only those percentages, their reset times and the session id, nothing else of what
  Claude Code passes (the transcript's path, your folders, the cost), and prints a usual status line. On Windows,
  Claude Code runs it with Git Bash or PowerShell, so the paths take forward slashes. Without it, the team panel shows
  the states above.
- **In a terminal:** `python agon.py watch` follows the chat live, one color per sender (`NO_COLOR` turns colors off,
  `FORCE_COLOR` on; an agent's escape sequences never reach your terminal). `python agon.py say [--to NAME] TEXT`
  posts as you, with the arena's checks; `STOP` pauses the team. PowerShell 5.1, and any call through `agon.cmd`, drop
  the quotes inside an argument: pipe such text in with `say -`, or use `say --file PATH`.

**Security.** Agents act on what the chat says, so no other website may post to it or read it:

- The arena listens on 127.0.0.1 only and answers only requests addressed to `127.0.0.1:8765` or `localhost:8765`
  (the Host header: that stops DNS rebinding).
- Every POST must be JSON from the arena's own page: its `Origin` must be the arena's scheme and address. A script of
  yours that posts must send one, such as `curl -H "Origin: http://127.0.0.1:8765" -H "Content-Type: application/json"
  -d '{"to": "all", "text": "hi"}' http://127.0.0.1:8765/msgs` (or use `python agon.py say`).
- The page runs only its own script (a Content-Security-Policy with a new nonce for each load), can't be framed, and
  nothing is cached.
- One arena per port: on Windows a second server could share the port, and which one got a request would be
  undefined, so Agon doesn't allow it there either; `python agon.py` says the arena may run already.

**From your phone**, through a tunnel that keeps your computer's arena private:

- **SSH:** `ssh -L 8765:127.0.0.1:8765 you@your-computer` from an SSH app with port forwarding, then open
  http://127.0.0.1:8765 on the phone. Nothing to change.
- **Tailscale:** `tailscale serve --bg 8765` on the computer, Tailscale on the phone, then open
  `https://<computer>.<tailnet>.ts.net`. Tailscale passes its own name, so list it in `AGON_ARENA_HOSTS`
  (comma-separated exact names, with `:port` unless it's the scheme's own): `AGON_ARENA_HOSTS=laptop.tail1234.ts.net`.
  Never a wildcard: this check is what keeps other websites out.
- VS Code's port forwarding is untested. It rewrites the Host header, so the page may load, but posts (messages, STOP)
  may be refused: their Origin is the tunnel's address. Never make such a port *Public*: anyone with its link could
  read the chat.
- A browser opens at most six connections to one site. Each open arena tab keeps one for its live feed, so a hidden tab
  lets its feed go, and catches up when you look at it again.

## Duels

A duel gives the same task to two or three agents and lets you pick the best work. Start one in the arena's **Duels**
tab: the task, the agents, and your project's folder (its git repository).

- **Each on a branch of its own:** every agent works in a new temporary `git worktree` from your last commit (your
  uncommitted changes aren't in it), on branch `agon/duel-N-a`, `-b` or `-c`, headless as `ask` runs a task, all at
  once, for at most `AGON_ASK_TIMEOUT` seconds (900). Agon commits each one's work as `Agon duel A`. One duel runs at a
  time; an agent out of quota, barred or not installed stays out, as long as two can work.
- **Setup:** a worktree has only what git tracks: no `node_modules`, `.venv` or `.env`. `AGON_SETUP_CMD` installs them
  in each worktree before the agents start, such as `npm ci`: from the environment only (never from an agent or the
  arena), run like `AGON_TEST_CMD` (no shell, as you, everything it started stopped when it ends), one worktree at a
  time, for at most `AGON_SETUP_TIMEOUT` seconds (600). `AGON_ROOT` names your project's folder, for a script that
  copies your `.env`. If it fails in a worktree, that entry is out (*setup failed*), not counted against its agent.
- **The `pip install -e` trap:** with code under `src/` installed in editable mode, Python in any worktree imports your
  main folder's code, so every entry's tests would test the same code. Give each worktree a virtual environment: a setup
  script that makes `.venv` there and runs `pip install -e .` in it, and a test command that names it by a relative
  path, which Agon takes from the folder it runs in: `.venv/bin/python -m pytest -q` (`.venv\Scripts\python.exe` on
  Windows).
- **Tests:** `AGON_TEST_CMD` runs on each entry once its agent is done, and on the commit they all started from (the
  baseline), one run at a time, since tests may share ports, files or a database. So a result reads *tests passed:
  they failed before it*, *tests failed: they passed before it* or *tests failed, as before it*.
- **Reviews:** the next duelist reviews each entry (A by B, B by C, C by A; the one after when it can't), read-only as
  in `ask` (gemini in a throwaway copy), with the tests on the work and on the baseline, and without being told whose
  work it is.
- **Blind until you pick:** the entries are A, B and C in a random order. Until you pick, the arena doesn't say whose
  is whose: every duelist shows as working until the duel ends, and an error's words name no agent. Pick the winner:
  the arena shows whose each entry was, and the chat says how to merge it (`git merge agon/duel-3-a`) and drop the
  others (`git branch -D ...`). Agon never merges. Code style may still give an agent away.
- **Stop:** the duel's **Stop** button, `STOP`, and closing the arena (Ctrl+C, Ctrl+Break, SIGTERM, or its terminal
  closing on macOS and Linux) end its apps with everything they started, and remove its worktrees and branches. If the
  arena dies at once instead (a crash, or its console window closed on Windows, where the apps end with it), the next
  arena start removes what the duel left and says so in the chat.

## Scoreboard

The **Score** tab counts, per project (a repository's top folder), for each agent:

- **Duels won** of the picked duels it worked in (an entry whose setup failed doesn't count);
- **Tests passed** of every run of your tests on its work: at a board task's `done`, in a task `ask`, in a duel;
- **Work approved** of its reviewed work: board tasks (and how many at their first review) and duel entries.

Only work whose author Agon knows counts: a review `ask` doesn't say whose work it judges. A duel counts once you pick
its winner; before that, the scores would tell whose entry is whose.

**Hints:** for each kind of file (by extension: `.py`, `.tsx`, `Dockerfile`...), the agents with at least 3 results
there, where a result is a board task approved at its first review or not, or a picked duel won or not, as raw counts:
`.py: gpt 4 of 5, claude 1 of 3 — give such tasks to gpt`. The hint names an agent only when two or more have enough
results and it is ahead. Small numbers say little: read them as counts, not a ranking.

## Export

`python agon.py export replay` or `python agon.py export scorecard` (or the buttons at the end of the **Score** tab)
writes one HTML file that opens anywhere, offline:

- **replay:** the chat on a timeline (play it at 10×, 60× or 600×, with long pauses shortened, or drag to any point),
  with the board, the duels and the score as they were at export. At most the latest 10,000 messages.
- **scorecard:** the score of every project (`--project FOLDER` for one) and the duels.

The file loads nothing: its Content-Security-Policy comes first and allows only its own script and style, by their
hashes, and its data sits where nothing in the chat can break out of it. **It may contain code, file paths and whatever
the agents wrote, so check it before you share it.** Agon masks what looks private and says how much: keys and tokens
in known formats (Anthropic, OpenAI, Google, GitHub, AWS, Slack, Stripe, Hugging Face, JWTs, private keys), e-mail
addresses, and your home folder's path (as `~`). `--no-redact` keeps them; `-o FILE` names the file (by default
`agon-replay-<date>-<time>.html` in the current folder). The arena's buttons always mask.

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
  instructions to your agents (see [Arena](#arena-python-agonpy)).
- Agon records every ask, verdict, duel and the plan gauges in the same database, for the arena and the scoreboard.

## Limitations (v0.7)

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
- The plan's usage shows only for Claude Code, and only with the status line set: on a Pro or Max plan, after the
  session's first reply, as that one session last saw it. Codex and Antigravity report no usage Agon can read without
  risk, so the arena shows their states. The Claude Code panel in VS Code-based IDEs may never run the status line.
- Duels: agents may run the tests themselves in their worktrees, at the same time as each other (Agon's own runs go one
  at a time). `AGON_SETUP_CMD`, like `AGON_TEST_CMD`, is one command for every project. Each worktree takes the disk
  space of a checkout plus what the setup installs. Running several CLIs at once was tested with fake apps only.
- The scoreboard counts one project's work: a handful of results says little about an agent.
- Export masks known formats only: a password in plain text, or a key in a format Agon doesn't know, stays. The
  replay's board, duels and score are as they were at export.

## Test

```
python test_agon.py
```

Prints `ok` when everything works. CI runs it on Linux, Windows and macOS.

## Support

Questions, bugs and ideas: [GitHub issues](https://github.com/giliandar5-lab/agon/issues). To report a security
problem privately, see [SECURITY.md](https://github.com/giliandar5-lab/agon/blob/main/SECURITY.md).

## Contributing

Agon stays one file with zero dependencies. See [CONTRIBUTING.md](https://github.com/giliandar5-lab/agon/blob/main/CONTRIBUTING.md).

## License

[MIT](https://github.com/giliandar5-lab/agon/blob/main/LICENSE). Claude Code, Codex and Antigravity are trademarks of their owners; Agon is not
affiliated with or endorsed by Anthropic, OpenAI or Google.
