# Contributing to Agon

Thanks for helping! Agon stays small on purpose, so a few rules:

- **One file.** All of Agon is `agon.py`: no packages, no build step.
- **Zero dependencies.** Python 3.10+ standard library only, on Windows, macOS and Linux.
- **Tests are required.** Every change in behavior comes with an assert-based check in `test_agon.py`.
  Run `python test_agon.py` before you open a pull request: it must print `ok`. CI runs it on all three systems.
- **Stay compatible.** Existing tools keep their names and parameters, and old `agon.db` files keep working:
  to change the database, add a step at the end of `SCHEMA`, never edit an old one.
- **English** for code, comments, docs and commit messages (`README.ru.md` is the Russian translation of `README.md`).
- **Check the official docs** before relying on a CLI flag, hook schema or plugin manifest: these tools change monthly.

Where Agon is headed and why: [ROADMAP.md](ROADMAP.md).
