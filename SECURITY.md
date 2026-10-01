# Security

## Reporting a vulnerability

Please report security problems privately, through GitHub's private vulnerability reporting: open
[Report a vulnerability](https://github.com/giliandar5-lab/agon/security/advisories/new) on this repository's
Security tab. Don't open a public issue for them. Include the version (`agon --version`), your operating system, and
steps to reproduce.

Reports are handled on a best-effort basis: this is a volunteer project. Fixes go into the next release, and the
advisory is published once the fix is out.

## Supported versions

Only the latest release gets security fixes.

## What Agon trusts

- Agon runs your test command (`AGON_TEST_CMD`) as you, without asking, when an agent calls `board done`, before a
  review and in duels, and your setup command (`AGON_SETUP_CMD`) in each duel's worktrees: set them only to commands
  you trust. The agents can't change them.
- The arena listens on 127.0.0.1 only, answers only at the names it knows (`AGON_ARENA_HOSTS`) and takes posts only
  from its own page.
- Anyone who can write to `~/.agon/agon.db` can post to your agents: keep it in your own home folder.
- With `AGON_UNSAFE=1`, autopilot lets the apps it wakes do everything without asking. Use it only in a sandbox.
