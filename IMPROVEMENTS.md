# Improvement Plan (Step-by-Step)

This document lists targeted improvements and how to implement them later. Each step is scoped to be incremental and testable.

## 1) Add message correlation + filtering on the server
**Goal:** Prevent stale/duplicate `Done` packets from being re-sent and mixed into new output.

**Steps:**
1. Track `active_cmd_id` and `completed_cmd_ids` in `app/agent.py`.
2. Ignore `more <id>` requests for unknown or completed IDs.
3. Store last N command IDs with timestamps to reject late repeats.

**Test:**
- Run `ls` twice quickly; ensure second command output is clean and no old `Done` is re-sent.

---

## 2) Add explicit end-of-output metadata
**Goal:** Make completion unambiguous even if messages arrive out of order.

**Steps:**
1. Append `DONE:<id>:<chunk_count>` in the final chunk.
2. Update controller/web UI to detect `DONE:` tokens and stop waiting.

**Test:**
- Simulate packet loss; confirm controller stops only when `DONE:` arrives.

---

## 3) Reliable chunk paging protocol
**Goal:** Only send additional chunks when explicitly requested by the controller.

**Steps:**
1. On server, buffer chunks per `cmd_id` (e.g. list of chunks).
2. Send chunk 1 immediately, then wait for `more <id> <offset>` to send the next chunk.
3. Add `offset`/`page` in the `more` command.

**Test:**
- Large `ls` output: controller requests 1 page at a time.

---

## 4) Single-client lock for serial ports
**Goal:** Prevent serial disconnects from double-opening the port.

**Steps:**
1. In `webui/app.py`, create a lock file (e.g. `/tmp/minic2-webui.lock`) when opening the port.
2. If lock exists, return a clear JSON error to UI.
3. Document “only one controller at a time” in the Web UI.

**Test:**
- Start controller CLI while Web UI runs; Web UI should show a “Port busy” error.

---

## 5) Add a health endpoint + status widget
**Goal:** Make it obvious when the Pi service is up.

**Steps:**
1. Add `/health` endpoint to `webui/app.py` that returns `{ "status": "ok" }`.
2. Add a status badge in the UI that pings `/health` on load.

**Test:**
- Stop Pi service; UI should show “Disconnected”.

---

## 6) Improve logging + timing
**Goal:** Pinpoint slow points and improve diagnosis.

**Steps:**
1. Add timing metrics for: command receive, execution, chunking, send durations.
2. Write structured logs (JSON lines) to `minic2.log`.

**Test:**
- Verify logs include `cmd_id`, `exec_ms`, `send_ms` per chunk.

---

## 7) Add retry/backoff policy
**Goal:** Improve reliability without spamming the mesh.

**Steps:**
1. On controller, add exponential backoff for `more` retries.
2. Cap to `max_more_attempts` and report partial output.

**Test:**
- Force dropped packets and verify the controller stops after max attempts with a warning.

---

## 8) Make config a single `.env`
**Goal:** Simplify deployment and eliminate mismatches.

**Steps:**
1. Add `.env.example` with `MINIC2_PORT`, `MINIC2_TIMEOUT`, etc.
2. Load env config in server + web UI via `python-dotenv`.

**Test:**
- Start both services with a shared `.env` file.

---

## 9) Web UI improvements
**Goal:** Make output and history clearer and more robust.

**Steps:**
1. Highlight new output chunks as they arrive.
2. Add “Copy raw output” button for history.
3. Show which `cmd_id` a history entry belongs to.

**Test:**
- Run `ls`, verify history shows full raw output with copy action.

---

## 10) Pi service as systemd unit
**Goal:** Auto-start on reboot and easy restart.

**Steps:**
1. Add `systemd/minic2.service` file.
2. Document enable/start commands in README.

**Test:**
- Reboot Pi; service should be active and responding.

---

## 11) Add lightweight tests
**Goal:** Avoid regressions in parsing and chunk logic.

**Steps:**
1. Add tests for `parse_output` and `chunk_output`.
2. Add a test fixture for `more` paging.

**Test:**
- `pytest` on CI or local should pass.

---

## 12) Security hardening (optional)
**Goal:** Avoid unsafe remote execution.

**Steps:**
1. Add allowlist for commands or a `safe` mode.
2. Block `rm -rf` or other destructive commands.

**Test:**
- Try blocked commands; ensure they are rejected with a clear error.
