const authSection = document.querySelector("#auth");
const appSection = document.querySelector("#app");
const authForm = document.querySelector("#auth-form");
const tokenInput = document.querySelector("#token");
const lockButton = document.querySelector("#lock");
const repoInput = document.querySelector("#repo");
const createFolderButton = document.querySelector("#create-folder");
const connectButton = document.querySelector("#connect");
const connection = document.querySelector("#connection");
const terminal = document.querySelector("#terminal");
const inputForm = document.querySelector("#input-form");
const terminalInput = document.querySelector("#terminal-input");
const ctrlCButton = document.querySelector("#ctrl-c");

let token = sessionStorage.getItem("agentSmithToken") || "";
let socket = null;
const screen = {
  rows: [""],
  row: 0,
  col: 0,
};

function append(text) {
  writeTerminal(text);
  terminal.scrollTop = terminal.scrollHeight;
}

function ensureRow(index) {
  while (screen.rows.length <= index) {
    screen.rows.push("");
  }
}

function putChar(char) {
  ensureRow(screen.row);
  const line = screen.rows[screen.row];
  screen.rows[screen.row] = line.padEnd(screen.col, " ").slice(0, screen.col) + char + line.slice(screen.col + 1);
  screen.col += 1;
}

function eraseLine(mode) {
  ensureRow(screen.row);
  const line = screen.rows[screen.row];
  if (mode === 1) {
    screen.rows[screen.row] = line.slice(screen.col);
  } else if (mode === 2) {
    screen.rows[screen.row] = "";
    screen.col = 0;
  } else {
    screen.rows[screen.row] = line.slice(0, screen.col);
  }
}

function eraseDisplay(mode) {
  if (mode === 2 || mode === 3) {
    screen.rows = [""];
    screen.row = 0;
    screen.col = 0;
  }
}

function handleCsi(params, command) {
  const values = params.split(";").filter(Boolean).map((value) => Number.parseInt(value, 10) || 0);
  const first = values[0] || 1;
  if (command === "A") screen.row = Math.max(0, screen.row - first);
  if (command === "B") screen.row += first;
  if (command === "C") screen.col += first;
  if (command === "D") screen.col = Math.max(0, screen.col - first);
  if (command === "G") screen.col = Math.max(0, first - 1);
  if (command === "H" || command === "f") {
    screen.row = Math.max(0, (values[0] || 1) - 1);
    screen.col = Math.max(0, (values[1] || 1) - 1);
  }
  if (command === "J") eraseDisplay(values[0] || 0);
  if (command === "K") eraseLine(values[0] || 0);
}

function writeTerminal(text) {
  let index = 0;
  while (index < text.length) {
    const char = text[index];
    if (char === "\u001b") {
      const csi = text.slice(index).match(/^\u001b\[([0-9;?]*)([@-~])/);
      if (csi) {
        handleCsi(csi[1].replaceAll("?", ""), csi[2]);
        index += csi[0].length;
        continue;
      }
      const osc = text.slice(index).match(/^\u001b\][^\u0007]*(\u0007|\u001b\\)/);
      if (osc) {
        index += osc[0].length;
        continue;
      }
      index += 1;
      continue;
    }
    if (char === "\r") {
      screen.col = 0;
    } else if (char === "\n") {
      screen.row += 1;
      screen.col = 0;
      ensureRow(screen.row);
    } else if (char === "\b") {
      screen.col = Math.max(0, screen.col - 1);
    } else if (char >= " ") {
      putChar(char);
    }
    index += 1;
  }
  terminal.textContent = screen.rows.slice(-1000).join("\n");
}

function clearTerminal() {
  screen.rows = [""];
  screen.row = 0;
  screen.col = 0;
  terminal.textContent = "";
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      ...(options.headers || {}),
      Authorization: `Bearer ${token}`,
    },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error || `Request failed: ${response.status}`);
  }
  return payload;
}

async function loadStatus() {
  const status = await api("/status");
  if (!repoInput.value && status.repos?.length) {
    repoInput.value = status.repos[0];
  }
  const tokenState = status.nexus?.token_present ? "token present" : "token missing";
  connection.textContent = status.qwen_available ? `Ready: Qwen on Iris, Vulcan Nexus, ${tokenState}` : "Qwen missing on Iris";
}

function renderAuth() {
  const authed = Boolean(token);
  authSection.classList.toggle("hidden", authed);
  appSection.classList.toggle("hidden", !authed);
}

function disconnect() {
  if (socket) {
    socket.close();
    socket = null;
  }
}

function connectTerminal() {
  disconnect();
  clearTerminal();
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const repo = encodeURIComponent(repoInput.value.trim());
  const wsToken = encodeURIComponent(token);
  socket = new WebSocket(`${protocol}//${window.location.host}/terminal?repo=${repo}&token=${wsToken}`);
  socket.addEventListener("open", () => {
    connection.textContent = "Connected";
    terminalInput.focus();
  });
  socket.addEventListener("message", (event) => append(event.data));
  socket.addEventListener("close", () => {
    connection.textContent = "Disconnected";
    socket = null;
  });
  socket.addEventListener("error", () => {
    append("\r\n[connection error]\r\n");
  });
}

authForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  token = tokenInput.value.trim();
  try {
    await loadStatus();
    sessionStorage.setItem("agentSmithToken", token);
    renderAuth();
  } catch (error) {
    token = "";
    sessionStorage.removeItem("agentSmithToken");
    tokenInput.value = "";
    tokenInput.placeholder = error.message;
  }
});

lockButton.addEventListener("click", () => {
  disconnect();
  token = "";
  sessionStorage.removeItem("agentSmithToken");
  renderAuth();
});

createFolderButton.addEventListener("click", async () => {
  try {
    const payload = await api("/api/folder", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ repo: repoInput.value.trim() }),
    });
    repoInput.value = payload.repo;
    append(`[created ${payload.repo}]\r\n`);
  } catch (error) {
    append(`[create failed: ${error.message}]\r\n`);
  }
});

connectButton.addEventListener("click", connectTerminal);

ctrlCButton.addEventListener("click", () => {
  if (!socket || socket.readyState !== WebSocket.OPEN) {
    append("[not connected]\r\n");
    return;
  }
  socket.send("\u0003");
});

inputForm.addEventListener("submit", (event) => {
  event.preventDefault();
  if (!socket || socket.readyState !== WebSocket.OPEN) {
    append("[not connected]\r\n");
    return;
  }
  socket.send(terminalInput.value + "\r");
  terminalInput.value = "";
});

terminalInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    inputForm.requestSubmit();
  }
});

if (token) {
  loadStatus().catch(() => {
    token = "";
    sessionStorage.removeItem("agentSmithToken");
  }).finally(renderAuth);
} else {
  renderAuth();
}
