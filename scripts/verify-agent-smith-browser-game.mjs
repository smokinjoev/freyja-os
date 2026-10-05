#!/usr/bin/env node
import { mkdtemp, rm, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { spawn } from "node:child_process";

const [, , htmlArg, ...flags] = process.argv;
const browserEnabled = flags.includes("--browser");
const chromePathFlag = flags.find((item) => item.startsWith("--chrome="));
const chromePath = chromePathFlag
  ? chromePathFlag.slice("--chrome=".length)
  : process.env.CHROME_PATH || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";

if (!htmlArg) {
  console.error("usage: node scripts/verify-agent-smith-browser-game.mjs <index.html> [--browser] [--chrome=/path/to/chrome]");
  process.exit(2);
}

const htmlPath = resolve(htmlArg);
const html = await readFile(htmlPath, "utf8");
const evidence = {
  ok: false,
  file: htmlPath,
  static: [],
  browser: [],
};

function assertEvidence(condition, label, detail = "") {
  const entry = { label, ok: Boolean(condition), detail };
  evidence.static.push(entry);
  if (!condition) throw new Error(`${label}${detail ? `: ${detail}` : ""}`);
}

function assertBrowser(condition, label, detail = "") {
  const entry = { label, ok: Boolean(condition), detail };
  evidence.browser.push(entry);
  if (!condition) throw new Error(`${label}${detail ? `: ${detail}` : ""}`);
}

async function runBrowserChecks() {
  const userDataDir = await mkdtemp(join(tmpdir(), "agent-smith-game-chrome-"));
  const chrome = spawn(
    chromePath,
    [
      "--headless=new",
      "--disable-gpu",
      "--no-first-run",
      "--no-default-browser-check",
      `--user-data-dir=${userDataDir}`,
      "--remote-debugging-port=0",
      pathToFileURL(htmlPath).href,
    ],
    { stdio: ["ignore", "ignore", "pipe"] },
  );
  let stderr = "";
  try {
    const browserWs = await new Promise((resolveWs, rejectWs) => {
      const timeout = setTimeout(() => rejectWs(new Error("Chrome did not expose a DevTools endpoint within 10s.")), 10000);
      chrome.stderr.on("data", (chunk) => {
        stderr += chunk.toString();
        const match = stderr.match(/DevTools listening on (ws:\/\/[^\s]+)/);
        if (match) {
          clearTimeout(timeout);
          resolveWs(match[1]);
        }
      });
      chrome.once("error", (error) => {
        clearTimeout(timeout);
        rejectWs(error);
      });
      chrome.once("exit", (code) => {
        if (!stderr.includes("DevTools listening on")) {
          clearTimeout(timeout);
          rejectWs(new Error(`Chrome exited before DevTools was ready: ${code}`));
        }
      });
    });
    const endpoint = new URL(browserWs);
    const listUrl = `http://${endpoint.host}/json/list`;
    const targets = await waitForTargets(listUrl);
    const page = targets.find((target) => target.type === "page" && String(target.url || "").startsWith("file:"));
    assertBrowser(Boolean(page?.webSocketDebuggerUrl), "browser page opened", page?.url || "");
    const cdp = await CdpClient.connect(page.webSocketDebuggerUrl);
    try {
      await cdp.send("Runtime.enable");
      await waitForExpression(cdp, "document.readyState === 'complete' && !!window.agentSmithGameTest");
      const initial = await evaluate(cdp, "window.agentSmithGameTest.state()");
      assertBrowser(initial && typeof initial === "object", "test harness returned state");
      await evaluate(cdp, "window.agentSmithGameTest.start()");
      const started = await evaluate(cdp, "window.agentSmithGameTest.state()");
      assertBrowser(started.phase === "playing", "start begins play", JSON.stringify(started));
      const beforeX = Number(started.playerX);
      await evaluate(cdp, "window.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight' }))");
      await sleep(120);
      const moved = await evaluate(cdp, "window.agentSmithGameTest.state()");
      assertBrowser(Number(moved.playerX) !== beforeX, "keyboard control moves player", JSON.stringify({ beforeX, afterX: moved.playerX }));
      const beforeScore = Number(moved.score);
      await evaluate(cdp, "window.agentSmithGameTest.forceCollect()");
      await sleep(80);
      const scored = await evaluate(cdp, "window.agentSmithGameTest.state()");
      assertBrowser(Number(scored.score) > beforeScore, "scoring increases", JSON.stringify({ beforeScore, afterScore: scored.score }));
      await evaluate(cdp, "window.agentSmithGameTest.forceGameOver()");
      const over = await evaluate(cdp, "window.agentSmithGameTest.state()");
      assertBrowser(over.phase === "gameover", "game-over state reached", JSON.stringify(over));
      await evaluate(cdp, "window.agentSmithGameTest.restart()");
      const restarted = await evaluate(cdp, "window.agentSmithGameTest.state()");
      assertBrowser(restarted.phase === "ready" && Number(restarted.score) === 0, "restart resets game", JSON.stringify(restarted));
    } finally {
      cdp.close();
    }
  } finally {
    chrome.kill("SIGTERM");
    try {
      await rm(userDataDir, { recursive: true, force: true, maxRetries: 3, retryDelay: 100 });
    } catch {
      // Chrome may keep cache handles open briefly after SIGTERM. Cleanup is
      // useful hygiene, but it is not part of game acceptance evidence.
    }
  }
}

async function waitForTargets(url) {
  const deadline = Date.now() + 10000;
  while (Date.now() < deadline) {
    const response = await fetch(url);
    const targets = await response.json();
    if (Array.isArray(targets) && targets.length) return targets;
    await sleep(100);
  }
  throw new Error("Chrome did not report any page targets.");
}

async function waitForExpression(cdp, expression) {
  const deadline = Date.now() + 10000;
  while (Date.now() < deadline) {
    const value = await evaluate(cdp, expression);
    if (value) return value;
    await sleep(100);
  }
  throw new Error(`Timed out waiting for expression: ${expression}`);
}

async function evaluate(cdp, expression) {
  const result = await cdp.send("Runtime.evaluate", {
    expression,
    awaitPromise: true,
    returnByValue: true,
  });
  if (result.exceptionDetails) {
    throw new Error(result.exceptionDetails.text || "Runtime.evaluate failed");
  }
  return result.result?.value;
}

function sleep(ms) {
  return new Promise((resolveSleep) => setTimeout(resolveSleep, ms));
}

class CdpClient {
  constructor(socket) {
    this.socket = socket;
    this.nextId = 1;
    this.pending = new Map();
    socket.addEventListener("message", (event) => {
      const message = JSON.parse(event.data);
      if (!message.id || !this.pending.has(message.id)) return;
      const { resolve: resolvePending, reject } = this.pending.get(message.id);
      this.pending.delete(message.id);
      if (message.error) reject(new Error(message.error.message || JSON.stringify(message.error)));
      else resolvePending(message.result || {});
    });
  }

  static connect(url) {
    return new Promise((resolveConnect, rejectConnect) => {
      const socket = new WebSocket(url);
      socket.addEventListener("open", () => resolveConnect(new CdpClient(socket)));
      socket.addEventListener("error", () => rejectConnect(new Error("Unable to connect to Chrome DevTools WebSocket.")));
    });
  }

  send(method, params = {}) {
    const id = this.nextId++;
    const payload = JSON.stringify({ id, method, params });
    return new Promise((resolveSend, rejectSend) => {
      this.pending.set(id, { resolve: resolveSend, reject: rejectSend });
      this.socket.send(payload);
    });
  }

  close() {
    this.socket.close();
  }
}

async function main() {
  try {
    assertEvidence(/<(canvas|svg)\b|class=["'][^"']*(arena|game|playfield)/i.test(html), "play surface exists");
    assertEvidence(/start/i.test(html), "start control exists");
    assertEvidence(/restart/i.test(html), "restart control exists");
    assertEvidence(/score/i.test(html), "score display exists");
    assertEvidence(/lives|health/i.test(html), "lives or health display exists");
    assertEvidence(/game[- ]?over|gameOver|game_over/i.test(html), "game-over state exists");
    assertEvidence(/ArrowLeft|KeyA|keydown/i.test(html) && /ArrowRight|KeyD|keydown/i.test(html), "keyboard controls exist");
    assertEvidence(/agentSmithGameTest/i.test(html), "test harness hook exists");

    if (browserEnabled) {
      await runBrowserChecks();
    }

    evidence.ok = true;
    console.log(JSON.stringify(evidence, null, 2));
  } catch (error) {
    evidence.ok = false;
    evidence.error = error instanceof Error ? error.message : String(error);
    console.error(JSON.stringify(evidence, null, 2));
    process.exit(1);
  }
}

await main();
