# Controller Client Auto-Detect & Auto-Start Improvements

This document outlines improvements for the **controller client** to auto-detect Meshtastic devices, start automatically when the agent (Pi) comes online, and recover when no serial device is initially available.

## Current Behavior (Summary)
- CLI (`controller/send_and_listen.py`) requires a fixed `--port` argument.
- Web UI (`webui/app.py`) can select a port by scanning available serial devices but does not actively re-scan once a request is in progress.
- No automatic startup coordination between controller and agent.

## Improvements to Implement

### 1) Auto-Detect Meshtastic Device (Controller CLI + Web UI)
- **Scan serial ports on startup** using the same logic as `webui/app.py` (e.g. `usbmodem|usbserial|ttyACM|ttyUSB`).
- **Port priority order**:
  1. Last known good port (persisted locally).
  2. Explicit config override (env or config file).
  3. Preferred regex match.
  4. Any available port as fallback.
- **Device validation**:
  - Open serial interface and request node info (e.g., via Meshtastic API) to confirm the port is a valid Meshtastic device.
  - If validation fails, close and continue scanning.

### 2) Continuous Port Re-Scan When No Device Found
- **Retry loop** with exponential backoff (e.g., 1s → 2s → 4s → max 30s).
- **Hot-plug support**: detect device connect/disconnect and auto-reconnect without restarting the client.
- **Clear error messages**: show available ports + last failure reason.

### 3) Auto-Start Controller When Agent (Pi) Comes Online
- **Controller-side watchdog**:
  - Start controller service at boot (LaunchAgent on macOS).
  - Periodically send a lightweight `ping` command or heartbeat request.
  - If the agent responds, mark connection active and allow command execution.
- **Agent heartbeat broadcast**:
  - Agent sends a periodic `AGENT-ONLINE` message with node ID + timestamp.
  - Controller listens for it and transitions into “ready” state.

### 4) Connection Lifecycle Handling
- **Connection state machine**:
  - `DISCONNECTED → SCANNING → CONNECTED → READY`
- **Recover on failure**:
  - If no ACK from agent within timeout, drop back to `SCANNING` and re-open serial port.

### 5) Config + Persistence
- **Persist last working port** (e.g., `~/.meshc2/controller.json`).
- **Optional “preferred node ID”** to avoid connecting to the wrong radio.
- **Override via env or CLI**: `MESH_PORT`, `MESH_NODE_ID`.

### 6) Observability & Debugging
- **Live device status** in CLI/Web UI:
  - port, node ID, last heartbeat, reconnect attempts.
- **Verbose logging** for port scanning, validation, and reconnect cycles.

## Suggested Implementation Tasks (By File)

### `controller/send_and_listen.py`
- Add `--port` as optional; if not provided, auto-detect.
- Implement `find_meshtastic_port()` using the same serial scan logic as Web UI.
- Validate port by attempting a short Meshtastic handshake before sending commands.

### `webui/app.py`
- Reuse the same `find_meshtastic_port()` logic (single shared helper).
- Add a background re-scan if the device disappears.

### `webui/run_webui.sh` or LaunchAgent
- Ensure controller/web UI restarts automatically on macOS boot.

## Optional Enhancements
- **Bluetooth fallback** if no serial device found.
- **Multi-device selection** with a small UI prompt or config priority.
- **Version/compat check** between controller and agent at connect time.

---

If you want, I can convert this into a concrete implementation plan with code changes and tests.
