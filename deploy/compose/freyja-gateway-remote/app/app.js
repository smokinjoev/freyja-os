const authSection = document.querySelector("#auth");
const chatSection = document.querySelector("#chat");
const authForm = document.querySelector("#auth-form");
const tokenInput = document.querySelector("#token");
const lockButton = document.querySelector("#lock");
const agentSelect = document.querySelector("#agent");
const agentTitle = document.querySelector("#agent-title");
const messages = document.querySelector("#messages");
const composer = document.querySelector("#composer");
const messageInput = document.querySelector("#message");
const sendButton = document.querySelector("#send");

const labels = {
  freyja: "Freyja",
  benedict: "Benedict",
  "benedict-paralegal": "Benedict Paralegal",
  "agent-44": "Agent 44",
  jenna: "Jenna",
  cloyd: "Cloyd",
};

let token = sessionStorage.getItem("freyjaGatewayToken") || "";
let history = JSON.parse(localStorage.getItem("freyjaGatewayHistory") || "[]");

async function loadStatus() {
  const response = await fetch("/status", { headers: { Authorization: `Bearer ${token}` } });
  if (!response.ok) {
    throw new Error("Authentication failed.");
  }
  const status = await response.json();
  agentSelect.innerHTML = "";
  for (const [key, info] of Object.entries(status.agents || {})) {
    const option = document.createElement("option");
    option.value = key;
    option.textContent = info.label;
    agentSelect.append(option);
  }
  agentTitle.textContent = labels[agentSelect.value] || "Freyja";
}

function persist() {
  localStorage.setItem("freyjaGatewayHistory", JSON.stringify(history.slice(-100)));
}

function renderAuth() {
  const authed = Boolean(token);
  authSection.classList.toggle("hidden", authed);
  chatSection.classList.toggle("hidden", !authed);
  if (authed) {
    messageInput.focus();
  }
}

function renderMessages() {
  messages.innerHTML = "";
  const agent = agentSelect.value;
  for (const item of history.filter((entry) => entry.agent === agent)) {
    const node = document.createElement("div");
    node.className = `message ${item.role}`;
    node.textContent = item.content;
    messages.append(node);
  }
  messages.scrollTop = messages.scrollHeight;
}

function addMessage(role, content) {
  history.push({ agent: agentSelect.value, role, content, at: new Date().toISOString() });
  persist();
  renderMessages();
}

authForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  token = tokenInput.value.trim();
  try {
    await loadStatus();
    sessionStorage.setItem("freyjaGatewayToken", token);
    renderAuth();
    renderMessages();
  } catch (error) {
    token = "";
    sessionStorage.removeItem("freyjaGatewayToken");
    tokenInput.value = "";
    tokenInput.placeholder = error.message;
  }
});

lockButton.addEventListener("click", () => {
  token = "";
  sessionStorage.removeItem("freyjaGatewayToken");
  renderAuth();
});

agentSelect.addEventListener("change", () => {
  agentTitle.textContent = labels[agentSelect.value];
  renderMessages();
});

messageInput.addEventListener("input", () => {
  messageInput.style.height = "auto";
  messageInput.style.height = `${messageInput.scrollHeight}px`;
});

messageInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    composer.requestSubmit();
  }
});

composer.addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = messageInput.value.trim();
  if (!text || sendButton.disabled) {
    return;
  }
  messageInput.value = "";
  messageInput.style.height = "auto";
  addMessage("user", text);
  sendButton.disabled = true;
  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ agent: agentSelect.value, message: text }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.detail || payload.error || `Request failed: ${response.status}`);
    }
    const content = payload?.choices?.[0]?.message?.content || "No response text returned.";
    addMessage("assistant", content);
  } catch (error) {
    addMessage("system", error.message || "Request failed.");
  } finally {
    sendButton.disabled = false;
    messageInput.focus();
  }
});

if (token) {
  loadStatus().catch(() => {
    token = "";
    sessionStorage.removeItem("freyjaGatewayToken");
  }).finally(() => {
    renderAuth();
    renderMessages();
  });
} else {
  renderAuth();
  renderMessages();
}
