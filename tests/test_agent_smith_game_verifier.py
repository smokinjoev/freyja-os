from __future__ import annotations

import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VERIFIER = REPO_ROOT / "scripts" / "verify-agent-smith-browser-game.mjs"


GOOD_GAME = """<!doctype html>
<html>
<body>
  <button id="start">Start</button>
  <button id="restart">Restart</button>
  <main class="game arena">
    <canvas></canvas>
    <p>Score: <span id="score">0</span></p>
    <p>Lives: <span id="lives">3</span></p>
    <p id="gameOver">Game Over</p>
  </main>
  <script>
    let state = { phase: 'ready', score: 0, lives: 3, playerX: 0 };
    window.addEventListener('keydown', event => {
      if (event.key === 'ArrowRight') state.playerX += 1;
      if (event.key === 'ArrowLeft') state.playerX -= 1;
    });
    window.agentSmithGameTest = {
      state: () => ({ ...state }),
      start: () => { state.phase = 'playing'; },
      forceCollect: () => { state.score += 10; },
      forceGameOver: () => { state.phase = 'gameover'; },
      restart: () => { state = { phase: 'ready', score: 0, lives: 3, playerX: 0 }; },
    };
  </script>
</body>
</html>
"""


def test_agent_smith_game_verifier_accepts_static_contract(tmp_path: Path) -> None:
    game = tmp_path / "index.html"
    game.write_text(GOOD_GAME, encoding="utf-8")

    result = subprocess.run(
        ["node", str(VERIFIER), str(game)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert '"ok": true' in result.stdout
    assert "test harness hook exists" in result.stdout


def test_agent_smith_game_verifier_rejects_missing_restart_and_hook(tmp_path: Path) -> None:
    game = tmp_path / "index.html"
    game.write_text("<html><body><button>Start</button><p>Score 0</p><script>window.addEventListener('keydown', () => {})</script></body></html>", encoding="utf-8")

    result = subprocess.run(
        ["node", str(VERIFIER), str(game)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert '"ok": false' in result.stderr
    assert "play surface exists" in result.stderr
