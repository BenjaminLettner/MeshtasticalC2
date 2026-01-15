const form = document.getElementById("command-form");
const commandInput = document.getElementById("command");
const outputEl = document.getElementById("output");
const rawEl = document.getElementById("raw");
const statusEl = document.getElementById("status");
const timeoutInput = document.getElementById("timeout");
const portInput = document.getElementById("port");
const channelInput = document.getElementById("channel");

const setStatus = (text, variant = "idle") => {
  statusEl.textContent = text;
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

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const command = commandInput.value.trim();
  if (!command) return;

  setStatus("Transmitting...", "busy");
  renderOutput("");
  renderRaw([]);

  const payload = {
    command,
    timeout: Number(timeoutInput.value || 60),
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
    setStatus(data.received ? `Done in ${data.duration}s` : "No output", data.received ? "ok" : "warn");
  } catch (error) {
    renderOutput("");
    renderRaw([]);
    setStatus(error.message || "Error", "error");
  }
});

setStatus("Idle", "idle");
renderRaw([]);
