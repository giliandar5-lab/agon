# Contributing to Agon

Thanks for helping! Agon stays small on purpose, so a few rules:

- **One file.** All of Agon is `agon.py`, with no build step while you work on it: edit it and run it
  (`python agon.py`). The plugin manifests and the two launchers (`agon`, `agon.cmd`) only start it. The PyPI package
  `agon-arena` is that same file, built at release time by `.github/workflows/release.yml` (`flit_core` is needed only
  for that build, never to run Agon). The version is `__version__` in `agon.py` and `version` in the two plugin
  manifests: change them together.
- **Zero dependencies.** Python 3.10+ standard library only, on Windows, macOS and Linux.
- **Tests are required.** Every change in behavior comes with an assert-based check in `test_agon.py`.
  Run `python test_agon.py` before you open a pull request: it must print `ok`. CI runs it on all three systems.
- **Stay compatible.** Existing tools keep their names and parameters, and old `agon.db` files keep working:
  to change the database, add a step at the end of `SCHEMA`, never edit an old one. Every step stays backward
  compatible (a new table, or a new column with a default; never a new meaning for an old column): each app keeps its
  own copy of Agon, all copies share one database, and an older copy must keep working on it.
- **English** for code, comments, docs and commit messages (`README.ru.md` is the Russian translation of `README.md`).
- **Nothing over the network.** Agon makes no network requests and its pages load nothing from the internet;
  [PRIVACY.md](PRIVACY.md) lists what it keeps. Keep it that way, and update that list with a new table.
- **Check the official docs** before relying on a CLI flag, hook schema or plugin manifest: these tools change monthly.

Security problems: report them privately, see [SECURITY.md](SECURITY.md).

Where Agon is headed and why: [ROADMAP.md](ROADMAP.md).
