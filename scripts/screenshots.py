"""Screenshots of the arena with demo data, for the README and the listings (a maintainer's tool; not part of Agon).

python scripts/screenshots.py OUT_FOLDER

It fills a new database with a made-up team (no app or model runs), opens the arena on it, and saves PNG files through
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


def demo(db):
    """A made-up team building a Snake game: messages, board tasks in each state, an agent out of quota."""
    os.environ["AGON_DB"] = db
    sys.path.insert(0, str(HERE))
    import agon

    apps = {"claude": "claude-code", "gpt": "codex-mcp-client", "gemini": "antigravity-client"}
    team = {name: agon.Session(name, apps[name]) for name in apps}

    def board(name, **args):
        agon.touch(name, apps[name])
        return agon.call_tool(team[name], {"name": "board", "arguments": args})[0]["content"][0]["text"]

    agon.post("human", "all", "Build a Snake game in Python. claude, you lead: one board task per part.")
    board("claude", action="add", title="Game logic", spec="Grid, snake, food, collisions.", files=["snake/game.py"])
    board("claude", action="add", title="Graphics and menus", spec="pygame window, score, pause.",
          files=["snake/ui.py"], after=[1])
    board("claude", action="add", title="Tests and README", spec="pytest for the game logic.",
          files=["tests/test_game.py", "README.md"], after=[1])
    agon.post("claude", "all", "Plan is up: 3 tasks. gpt takes game logic, gemini the UI once it lands, I write tests.")
    board("gpt", action="claim", id=1)
    agon.post("gpt", "all", "On #1. Grid is 20x20; the snake wraps at the edges unless you say otherwise.")
    agon.post("human", "all", "No wrapping: hitting a wall ends the game.")
    agon.post("gpt", "human", "Got it: walls end the game. Collision tests cover all four.")
    board("claude", action="claim", id=3)
    agon.post("gemini", "all", "Waiting for #1; sketching the menu layout meanwhile.")
    agon.post("claude", "gpt", "Found an off-by-one in food spawning: it can land on the tail. Test attached in #3.")
    agon.post("gpt", "claude", "Fixed: food now picks from free cells only.")
    agon.touch("gemini", apps["gemini"])
    board("gpt", action="done", id=1, note="Grid, snake, food from free cells, walls end the game.")
    board("claude", action="review", id=1, verdict="approve",
          evidence="Read game.py in full; collision and food tests cover the four walls and the tail.")
    board("gemini", action="claim", id=2)
    agon.post("gemini", "all", "#1 is in: on #2 now, the pygame window and the pause menu.")


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main(out):
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    db = str(Path(tempfile.mkdtemp(), "demo.db"))
    subprocess.run([sys.executable, __file__, "--fill", db], check=True)
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
    if len(sys.argv) == 3 and sys.argv[1] == "--fill":
        demo(sys.argv[2])
    elif len(sys.argv) == 2:
        main(sys.argv[1])
    else:
        sys.exit(__doc__)
