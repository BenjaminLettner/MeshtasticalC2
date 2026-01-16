const form = document.getElementById("command-form");
const commandInput = document.getElementById("command");
const outputEl = document.getElementById("output");
const rawEl = document.getElementById("raw");
const statusEl = document.getElementById("status");
const statusTextEl = document.getElementById("status-text");
const historyEl = document.getElementById("history");
const activePortEl = document.getElementById("active-port");
const activeChannelEl = document.getElementById("active-channel");
const activeTimeoutEl = document.getElementById("active-timeout");

const configForm = document.getElementById("config-form");
const configPortSelect = document.getElementById("config-port");
const configChannelInput = document.getElementById("config-channel");
const configTimeoutInput = document.getElementById("config-timeout");
const configRefreshButton = document.getElementById("config-refresh-ports");
const configResetButton = document.getElementById("config-reset");
const configStatusEl = document.getElementById("config-status");

const HISTORY_KEY = "meshtasticalc2-history";

const setStatus = (text, variant = "idle") => {
  if (!statusTextEl || !statusEl) return;
  statusTextEl.textContent = text;
  statusEl.dataset.variant = variant;
};

const renderRaw = (messages) => {
  if (!rawEl) return;
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
  if (!historyEl) return;
  historyEl.innerHTML = "";
  if (!items.length) {
    historyEl.innerHTML = '<div class="history-item">No history yet.</div>';
    return;
  }
  items.forEach((item, index) => {
    const div = document.createElement("div");
    div.className = "history-item";
    div.dataset.index = index;
    div.innerHTML = `
      <div class="history-command">${item.command}</div>
      <span class="history-summary">${item.summary}</span>
      <button class="history-view" type="button">Load</button>
    `;
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

const appendOutputBlock = (command, output, meta, variant) => {
  if (!outputEl) return null;
  const block = document.createElement("div");
  block.className = "terminal-block";

  const line = document.createElement("div");
  line.className = "terminal-line";
  const prompt = document.createElement("span");
  prompt.className = "prompt";
  prompt.textContent = "mesh>";
  const cmd = document.createElement("span");
  cmd.className = "command-text";
  cmd.textContent = ` ${command}`;
  line.append(prompt, cmd);

  const response = document.createElement("pre");
  response.className = `terminal-response ${variant || ""}`.trim();
  response.textContent = output || "";

  const metaLine = document.createElement("div");
  metaLine.className = "terminal-meta-line";
  metaLine.textContent = meta || "";

  block.append(line, response, metaLine);
  outputEl.appendChild(block);
  outputEl.scrollTop = outputEl.scrollHeight;
  return block;
};

const applyHistoryEntry = (entry) => {
  if (outputEl) {
    outputEl.innerHTML = "";
  }
  appendOutputBlock(entry.command, entry.output || "<no output>", entry.summary, "ok");
  renderRaw(entry.raw || []);
  setStatus(`Loaded ${entry.command}`, "idle");
};

const CONFIG_KEY = "meshtasticalc2-config";
const DEFAULT_CONFIG = {
  port: "",
  channel: 1,
  timeout: 180,
};

const loadConfig = () => {
  try {
    const stored = JSON.parse(localStorage.getItem(CONFIG_KEY) || "{}");
    return { ...DEFAULT_CONFIG, ...stored };
  } catch (error) {
    console.error(error);
    return { ...DEFAULT_CONFIG };
  }
};

const saveConfig = (config) => {
  localStorage.setItem(CONFIG_KEY, JSON.stringify(config));
};

const setActiveConfig = (config) => {
  if (activePortEl) activePortEl.textContent = config.port || "Auto";
  if (activeChannelEl) activeChannelEl.textContent = String(config.channel || 1);
  if (activeTimeoutEl) activeTimeoutEl.textContent = String(config.timeout || 180);
};

if (form && commandInput) {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const command = commandInput.value.trim();
    if (!command) return;

    const config = loadConfig();
    setActiveConfig(config);

    if (command === "help" || command === "?") {
      const helpText = [
        "Local commands:",
        "  help      show this help",
        "  status    show active config",
        "  config    open configuration page",
        "  clear     clear console",
        "",
        "Remote session commands:",
        "  session start   start or resume a session",
        "  session status  show session status",
        "  session end     end the current session",
      ].join("\n");
      appendOutputBlock(command, helpText, "Local help", "ok");
      addHistoryEntry({
        command,
        summary: `Local help · ${new Date().toLocaleTimeString()}`,
        output: helpText,
        raw: [],
      });
      return;
    }

    if (command === "clear") {
      if (outputEl) outputEl.innerHTML = "";
      setStatus("Console cleared", "idle");
      addHistoryEntry({
        command,
        summary: `Cleared · ${new Date().toLocaleTimeString()}`,
        output: "",
        raw: [],
      });
      return;
    }

    if (command === "config") {
      window.location.href = "/config";
      return;
    }

    if (command === "status") {
      const statusText = `Port: ${config.port || "Auto"}\nChannel: ${config.channel}\nTimeout: ${config.timeout}s`;
      appendOutputBlock(command, statusText, "Local status", "ok");
      addHistoryEntry({
        command,
        summary: `Status · ${new Date().toLocaleTimeString()}`,
        output: statusText,
        raw: [],
      });
      return;
    }

    setStatus("Transmitting...", "busy");
    renderRaw([]);
    const block = appendOutputBlock(command, "", "Awaiting response...", "pending");
    const responseEl = block ? block.querySelector(".terminal-response") : null;
    const metaEl = block ? block.querySelector(".terminal-meta-line") : null;

    const payload = {
      command,
      port: config.port || "",
      channel: Number(config.channel || 1),
      timeout: Number(config.timeout || 180),
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

      const outputText = data.output || "<no output>";
      if (responseEl) responseEl.textContent = outputText;
      renderRaw(data.raw);
      const statusText = data.received ? `Done in ${data.duration}s` : "No output";
      if (metaEl) metaEl.textContent = statusText;
      if (responseEl) responseEl.classList.add(data.received ? "ok" : "warn");
      setStatus(statusText, data.received ? "ok" : "warn");
      addHistoryEntry({
        command,
        summary: `${statusText} · ${new Date().toLocaleTimeString()}`,
        output: outputText,
        raw: data.raw || [],
      });
    } catch (error) {
      const message = error.message || "Error";
      if (responseEl) responseEl.textContent = message;
      if (metaEl) metaEl.textContent = "Request failed";
      if (responseEl) responseEl.classList.add("error");
      setStatus(message, "error");
      addHistoryEntry({
        command,
        summary: `Error · ${message}`,
        output: "",
        raw: [],
      });
    }
  });
}

if (historyEl) {
  renderHistory(loadHistory());
  historyEl.addEventListener("click", (event) => {
    const button = event.target.closest(".history-view");
    if (!button) return;
    const itemEl = button.closest(".history-item");
    if (!itemEl) return;
    const index = Number(itemEl.dataset.index);
    const items = loadHistory();
    const entry = items[index];
    if (entry) {
      applyHistoryEntry(entry);
    }
  });
}

const loadPorts = async (selectEl) => {
  if (!selectEl) return;
  try {
    const response = await fetch("/api/ports");
    const data = await response.json();
    const ports = data.ports || [];
    selectEl.innerHTML = "";
    const emptyOption = document.createElement("option");
    emptyOption.value = "";
    emptyOption.textContent = "Auto-select";
    selectEl.appendChild(emptyOption);
    if (ports.length === 0) {
      return;
    }
    ports.forEach((port) => {
      const option = document.createElement("option");
      option.value = port;
      option.textContent = port;
      selectEl.appendChild(option);
    });
  } catch (error) {
    console.error(error);
  }
};

const initialConfig = loadConfig();
setActiveConfig(initialConfig);
renderRaw([]);
setStatus("Idle", "idle");

if (configForm && configPortSelect && configChannelInput && configTimeoutInput) {
  loadPorts(configPortSelect);
  configPortSelect.value = initialConfig.port || "";
  configChannelInput.value = initialConfig.channel;
  configTimeoutInput.value = initialConfig.timeout;

  configForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const nextConfig = {
      port: configPortSelect.value.trim(),
      channel: Number(configChannelInput.value || 1),
      timeout: Number(configTimeoutInput.value || 180),
    };
    saveConfig(nextConfig);
    setActiveConfig(nextConfig);
    if (configStatusEl) {
      configStatusEl.textContent = "Saved. Return to Console to use the new config.";
    }
  });

  if (configResetButton) {
    configResetButton.addEventListener("click", () => {
      saveConfig({ ...DEFAULT_CONFIG });
      configPortSelect.value = "";
      configChannelInput.value = DEFAULT_CONFIG.channel;
      configTimeoutInput.value = DEFAULT_CONFIG.timeout;
      setActiveConfig(DEFAULT_CONFIG);
      if (configStatusEl) {
        configStatusEl.textContent = "Reset to defaults.";
      }
    });
  }

  if (configRefreshButton) {
    configRefreshButton.addEventListener("click", () => loadPorts(configPortSelect));
  }
}
