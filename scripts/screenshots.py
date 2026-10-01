"""Screenshots of the arena with demo data, for the README and the listings (a maintainer's tool; not part of Agon).

python scripts/screenshots.py OUT_FOLDER

It fills a new database with a made-up team (no app or model runs) working on a small real project whose real tests
Agon runs, opens the arena on it, and saves PNG files through
Playwright for Node (npm install -g playwright; set PLAYWRIGHT_MODULE to its folder if Node can't find it). Each image
says "Screenshot with demo data" on it: none of it is a real team's work.
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
CAPTION = "Screenshot with demo data"
SHOTS = [("arena", "chat", 1280, 800), ("arena-phone", "chat", 390, 844), ("arena-phone-board", "board", 390, 844)]


GAME = """import random

SIZE = 20


def step(snake, direction):
    head = (snake[0][0] + direction[0], snake[0][1] + direction[1])
    if not (0 <= head[0] < SIZE and 0 <= head[1] < SIZE) or head in snake:
        return None  # a wall or the tail ends the game
    return [head, *snake[:-1]]


def place_food(snake, rng=random):
    {food}
"""
FOOD_BUGGY = "return (rng.randrange(SIZE), rng.randrange(SIZE))  # may land on the snake"
FOOD_FIXED = ("free = [(x, y) for x in range(SIZE) for y in range(SIZE) if (x, y) not in snake]\n"
              "    return rng.choice(free)")
TESTS = """import random
import unittest

from snake.game import SIZE, place_food, step


class Game(unittest.TestCase):
    def test_walls_end_the_game(self):
        for snake, direction in (([(0, 5)], (-1, 0)), ([(SIZE - 1, 5)], (1, 0)), ([(5, 0)], (0, -1)),
                                 ([(5, SIZE - 1)], (0, 1))):
            self.assertIsNone(step(snake, direction))

    def test_the_tail_ends_the_game(self):
        self.assertIsNone(step([(5, 5), (5, 6), (6, 6), (6, 5), (6, 4)], (0, 1)))

    def test_moving_keeps_the_length(self):
        self.assertEqual(step([(5, 5), (5, 6)], (1, 0)), [(6, 5), (5, 5)])

    def test_food_never_lands_on_the_snake(self):
        snake = [(x, y) for x in range(SIZE) for y in range(SIZE)][:-3]  # three cells left
        for seed in range(200):
            self.assertNotIn(place_food(snake, random.Random(seed)), snake)
"""


def demo(db, project):
    """A made-up team building a Snake game, in a small real project with real tests: Agon runs them at board done,
    so the verdicts on the board are real test runs. The first try fails them, the review catches it, the fix passes."""
    os.environ["AGON_DB"] = db
    os.environ["AGON_TEST_CMD"] = json.dumps([sys.executable, "-m", "unittest", "-q"])
    sys.path.insert(0, str(HERE))
    import agon

    root = Path(project)
    (root / "snake").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "snake" / "__init__.py").write_text("")
    (root / "tests" / "__init__.py").write_text("")
    (root / "tests" / "test_game.py").write_text(TESTS)
    (root / "snake" / "game.py").write_text("SIZE = 20\n")
    git = ["git", "-c", "user.name=demo", "-c", "user.email=demo@example.invalid", "-C", str(root)]
    subprocess.run([*git[:-2], "init", "-q", str(root)], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-qm", "Start"], check=True)

    apps = {"claude": "claude-code", "gpt": "codex-mcp-client", "gemini": "antigravity-client"}
    team = {name: agon.Session(name, apps[name]) for name in apps}

    def board(name, **args):
        agon.touch(name, apps[name])
        return agon.call_tool(team[name], {"name": "board", "arguments": args})[0]["content"][0]["text"]

    for name in apps:
        agon.touch(name, apps[name])
    agon.post("human", "all", "Build a Snake game in Python. claude, you lead: one board task per part.")
    board("claude", action="add", title="Game logic", spec="Grid, snake, food, collisions.", files=["snake/game.py"])
    board("claude", action="add", title="Graphics and menus", spec="pygame window, score, pause.",
          files=["snake/ui.py"], after=[1])
    board("claude", action="add", title="README", spec="How to play and run the tests.", files=["README.md"],
          after=[1])
    agon.post("claude", "all", "Plan is up: 3 tasks. gpt takes game logic, gemini the UI once it lands. Tests are in"
              " tests/; Agon runs them when a task is done.")
    board("gpt", action="claim", id=1)
    agon.post("gpt", "all", "On #1. Grid is 20x20; the snake wraps at the edges unless you say otherwise.")
    agon.post("human", "all", "No wrapping: hitting a wall ends the game.")
    agon.post("gpt", "human", "Walls end the game; the tests cover all four.")
    (root / "snake" / "game.py").write_text(GAME.format(food=FOOD_BUGGY))
    board("gpt", action="done", id=1, note="Grid, snake, walls and the tail end the game.", cwd=str(root))
    board("claude", action="review", id=1, verdict="changes", evidence="Agon's run: test_food_never_lands_on_the_snake"
          " fails. place_food picks any cell, so food can land on the snake.")
    (root / "snake" / "game.py").write_text(GAME.format(food=FOOD_FIXED))
    board("gpt", action="claim", id=1)
    board("gpt", action="done", id=1, note="Food now picks from the free cells only.", cwd=str(root))
    board("claude", action="review", id=1, verdict="approve",
          evidence="Agon's run passed; read game.py in full: walls, the tail and food on free cells only.")
    board("gemini", action="claim", id=2)
    agon.post("gemini", "all", "#1 is in: on #2 now, the pygame window and the pause menu.")


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main(out):
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp())
    db = str(work / "demo.db")
    subprocess.run([sys.executable, __file__, "--fill", db, str(work / "snake-game")], check=True)
    port = free_port()
    env = dict(os.environ, AGON_DB=db)
    arena = subprocess.Popen([sys.executable, "-c", "import sys, webbrowser; sys.path.insert(0, sys.argv[1]);"
                              " webbrowser.open = lambda url: None; import agon; agon.PORT = int(sys.argv[2]);"
                              " sys.exit(agon.arena())", str(HERE), str(port)], stdout=subprocess.PIPE, env=env)
    try:
        arena.stdout.readline()
        script = Path(tempfile.mkdtemp(), "shots.cjs")
        script.write_text(SHOOT, encoding="utf-8")
        module = os.environ.get("PLAYWRIGHT_MODULE") or subprocess.run(
            ["npm", "root", "-g"], capture_output=True, text=True, shell=os.name == "nt").stdout.strip() + "/playwright"
        subprocess.run(["node", str(script), module, f"http://127.0.0.1:{port}/", str(out), CAPTION, json.dumps(SHOTS)],
                       check=True)
    finally:
        arena.terminate()
        arena.wait(30)
    for name, *_ in SHOTS:
        print(out / f"{name}.png")


SHOOT = r"""
const [lib, url, out, caption, shots] = process.argv.slice(2);
const {chromium} = require(lib);
(async () => {
  const browser = await chromium.launch();
  for (const [name, panel, width, height] of JSON.parse(shots)) {
    const page = await browser.newPage({viewport: {width, height}, deviceScaleFactor: 2, colorScheme: 'dark'});
    await page.goto(url);
    await page.waitForSelector('#log .m');
    await page.waitForTimeout(800);
    await page.evaluate(([panel, caption]) => {
      const tab = document.querySelector('#tabs [data-panel="' + panel + '"]');
      if (tab) tab.click();
      const note = document.createElement('div');  // on the image itself, so it can't get lost
      note.textContent = caption;
      note.style.cssText = 'position:fixed;right:10px;bottom:' + (innerWidth < 600 ? 84 : 10) + 'px;z-index:99;'
        + 'padding:4px 10px;border-radius:6px;'
        + 'font:600 13px system-ui,sans-serif;background:#000c;color:#fff';
      document.body.append(note);
    }, [panel, caption]);
    await page.waitForTimeout(400);
    await page.screenshot({path: out + '/' + name + '.png'});
    await page.close();
  }
  await browser.close();
})();
"""

if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--fill":
        demo(sys.argv[2], sys.argv[3])
    elif len(sys.argv) == 2:
        main(sys.argv[1])
    else:
        sys.exit(__doc__)
