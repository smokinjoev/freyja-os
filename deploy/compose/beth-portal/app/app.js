const modes = {
  benedict: {
    model: "agent/benedict",
    user: "beth",
    title: "Benedict",
    placeholder: "Ask Benedict...",
    welcome: "Benedict is ready.",
  },
  paralegal: {
    model: "agent/benedict-paralegal",
    user: "paralegal",
    title: "Benedict Paralegal",
    placeholder: "Ask the local-only paralegal...",
    welcome: "Paralegal mode is local-only.",
  },
};

const state = {
  mode: localStorage.getItem("bethPortalMode") || "benedict",
  messages: JSON.parse(localStorage.getItem("bethPortalMessages") || "[]"),
  files: [],
};

const messagesEl = document.querySelector("#messages");
const promptEl = document.querySelector("#prompt");
const composerEl = document.querySelector("#composer");
const sendEl = document.querySelector("#send");
const fileInputEl = document.querySelector("#file-input");
const attachmentsEl = document.querySelector("#attachments");
const titleEl = document.querySelector("h1");
const modeButtons = {
  benedict: document.querySelector("#mode-benedict"),
  paralegal: document.querySelector("#mode-paralegal"),
};

function persist() {
  localStorage.setItem("bethPortalMode", state.mode);
  localStorage.setItem("bethPortalMessages", JSON.stringify(state.messages.slice(-80)));
}

function renderModes() {
  const config = modes[state.mode];
  document.body.classList.toggle("paralegal", state.mode === "paralegal");
  titleEl.textContent = config.title;
  promptEl.placeholder = config.placeholder;
  for (const [name, button] of Object.entries(modeButtons)) {
    const active = name === state.mode;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  }
}

function renderMessages() {
  messagesEl.innerHTML = "";
  if (!state.messages.length) {
    const intro = document.createElement("div");
    intro.className = "message system";
    intro.textContent = modes[state.mode].welcome;
    messagesEl.append(intro);
    return;
  }
  for (const message of state.messages) {
    const el = document.createElement("div");
    el.className = `message ${message.role}`;
    el.textContent = message.content;
    messagesEl.append(el);
  }
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function renderAttachments() {
  attachmentsEl.innerHTML = "";
  for (const file of state.files) {
    const chip = document.createElement("span");
    chip.className = "chip";
    chip.textContent = file.name;
    attachmentsEl.append(chip);
  }
}

function setMode(mode) {
  state.mode = mode;
  persist();
  renderModes();
  renderMessages();
}

function addMessage(role, content) {
  state.messages.push({ role, content, at: new Date().toISOString(), mode: state.mode });
  persist();
  renderMessages();
}

async function encodeFile(file) {
  const dataUrl = await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
  if (file.type.startsWith("image/")) {
    return { type: "image_url", image_url: { url: dataUrl } };
  }
  return { type: "file", file: { filename: file.name, file_data: dataUrl } };
}

async function buildContent(text) {
  if (!state.files.length) {
    return text;
  }
  return [{ type: "text", text }, ...(await Promise.all(state.files.map(encodeFile)))];
}

async function sendMessage(text) {
  const config = modes[state.mode];
  addMessage("user", text);
  sendEl.disabled = true;
  promptEl.disabled = true;
  try {
    const response = await fetch("/v1/chat/completions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model: config.model,
        user: config.user,
        stream: false,
        messages: [{ role: "user", content: await buildContent(text) }],
      }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload?.error?.message || payload?.detail || `Request failed: ${response.status}`);
    }
    const content = payload?.choices?.[0]?.message?.content || "No response text returned.";
    addMessage("assistant", content);
    state.files = [];
    fileInputEl.value = "";
    renderAttachments();
  } catch (error) {
    addMessage("system", error.message || "Benedict could not answer right now.");
  } finally {
    sendEl.disabled = false;
    promptEl.disabled = false;
    promptEl.focus();
  }
}

for (const [mode, button] of Object.entries(modeButtons)) {
  button.addEventListener("click", () => setMode(mode));
}

fileInputEl.addEventListener("change", () => {
  state.files = Array.from(fileInputEl.files || []);
  renderAttachments();
});

promptEl.addEventListener("input", () => {
  promptEl.style.height = "auto";
  promptEl.style.height = `${promptEl.scrollHeight}px`;
});

promptEl.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    composerEl.requestSubmit();
  }
});

composerEl.addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = promptEl.value.trim();
  if (!text || sendEl.disabled) {
    return;
  }
  promptEl.value = "";
  promptEl.style.height = "auto";
  await sendMessage(text);
});

renderModes();
renderMessages();
renderAttachments();
