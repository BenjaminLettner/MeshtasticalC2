const form = document.getElementById("command-form");
const commandInput = document.getElementById("command");
const outputEl = document.getElementById("output");
const rawEl = document.getElementById("raw");
const statusEl = document.getElementById("status");
const statusTextEl = document.getElementById("status-text");
const portInput = document.getElementById("port");
const channelInput = document.getElementById("channel");
const refreshPortsButton = document.getElementById("refresh-ports");
const historyEl = document.getElementById("history");

const HISTORY_KEY = "meshtasticalc2-history";

const setStatus = (text, variant = "idle") => {
  statusTextEl.textContent = text;
  statusEl.dataset.variant = variant;
};

const renderRaw = (messages) => {
  rawEl.innerHTML = "";
  if (!messages || messages.length === 0) {
    rawEl.innerHTML = '<div class="raw-item">No messages yet.</div>';
    return;
  }
  messages.forEach((message) => {
    const div = document.createElement("div");
    div.className = "raw-item";
    div.textContent = message;
    rawEl.appendChild(div);
  });
};

const renderOutput = (text) => {
  outputEl.textContent = text || "";
};

const loadHistory = () => {
  try {
    return JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]");
  } catch (error) {
    console.error(error);
    return [];
  }
};

const saveHistory = (items) => {
  localStorage.setItem(HISTORY_KEY, JSON.stringify(items));
};

const renderHistory = (items) => {
  historyEl.innerHTML = "";
  if (!items.length) {
    historyEl.innerHTML = '<div class="history-item">No history yet.</div>';
    return;
  }
  items.forEach((item) => {
    const div = document.createElement("div");
    div.className = "history-item";
    div.innerHTML = `<strong>${item.command}</strong>${item.summary}`;
    historyEl.appendChild(div);
  });
};

const addHistoryEntry = (entry) => {
  const items = loadHistory();
  items.unshift(entry);
  const trimmed = items.slice(0, 20);
  saveHistory(trimmed);
  renderHistory(trimmed);
};

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const command = commandInput.value.trim();
  if (!command) return;

  setStatus("Transmitting...", "busy");
  renderOutput("");
  renderRaw([]);

  const payload = {
    command,
    port: portInput.value.trim(),
    channel: Number(channelInput.value || 1),
  };

  try {
    const response = await fetch("/api/command", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Request failed");
    }

    renderOutput(data.output || "<no output>");
    renderRaw(data.raw);
    const statusText = data.received ? `Done in ${data.duration}s` : "No output";
    setStatus(statusText, data.received ? "ok" : "warn");
    addHistoryEntry({
      command,
      summary: `${statusText} · ${new Date().toLocaleTimeString()}`,
    });
  } catch (error) {
    renderOutput("");
    renderRaw([]);
    const message = error.message || "Error";
    setStatus(message, "error");
    addHistoryEntry({
      command,
      summary: `Error · ${message}`,
    });
  }
});

setStatus("Idle", "idle");
renderRaw([]);
renderHistory(loadHistory());

const loadPorts = async () => {
  try {
    const response = await fetch("/api/ports");
    const data = await response.json();
    const ports = data.ports || [];
    portInput.innerHTML = "";
    if (ports.length === 0) {
      const option = document.createElement("option");
      option.value = "";
      option.textContent = "No devices found";
      portInput.appendChild(option);
      return;
    }
    ports.forEach((port) => {
      const option = document.createElement("option");
      option.value = port;
      option.textContent = port;
      portInput.appendChild(option);
    });
    if (ports.length === 1) {
      portInput.value = ports[0];
    }
  } catch (error) {
    console.error(error);
  }
};

refreshPortsButton.addEventListener("click", loadPorts);
loadPorts();
