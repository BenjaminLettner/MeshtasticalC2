# MeshC2 LoRa Protocol vs TCP: Gap Analysis & Implementation Checklist

This document compares the current Meshtastic text-message flow to TCP-style reliability and lists the protocol features we should implement to achieve TCP-like behavior.

## Current Communication (LoRa/Meshtastic)

Observed in:
- Controller CLI: `controller/send_and_listen.py`
- Web UI backend: `webui/app.py`
- Agent: `app/agent.py`

**Current flow (simplified):**
1. Controller sends a command with `sendText()`.
2. Agent receives the command, executes it, and replies with:
   - `MSG-ID:<id>\nHost:<host>\nCmd received: <command>` (ACK)
   - One or more `Output` chunks in separate messages.
3. If there are multiple chunks, controller may send a `more <msg-id>` request once.

**Characteristics:**
- Unordered, best-effort delivery (LoRa broadcast).
- Single “more” request (no continuous paging).
- No guaranteed retransmission or delivery confirmation.
- No congestion/flow control or sliding window.

## TCP Features Missing & Required Additions

### 1) Connection/Session Management
- [ ] **Connection handshake**: introduce `SYN`, `SYN-ACK`, `ACK` equivalents to establish a session ID before commands.
- [ ] **Session IDs**: include a stable `session_id` in every message (command, ACK, chunk, error).
- [ ] **Session teardown**: explicit `FIN/ACK` or idle timeout logic.
- [ ] **Keepalive/heartbeat**: optional ping messages to detect dead peers.

### 2) Sequencing & Ordering
- [ ] **Monotonic sequence numbers** per session for *every* message.
- [ ] **Chunk sequence**: per-command chunk index (`chunk_index`, `chunk_total`).
- [ ] **Out-of-order buffer**: hold and reorder chunks before presenting output.
- [ ] **Duplicate detection**: drop duplicates based on `(session_id, seq)` or `(cmd_id, chunk_index)`.

### 3) Reliable Delivery (ACK/NAK)
- [ ] **ACK for every data segment** (or cumulative ACKs).
- [ ] **Selective ACK (SACK)** for missing chunk indices.
- [ ] **Negative ACK (NAK)** for quick resend of missing segments.
- [ ] **Retransmission timer** with exponential backoff.
- [ ] **Max retry policy** + error reporting to user.

### 4) Flow Control (Receiver-Driven)
- [ ] **Window size** advertised by receiver (how many chunks can be in-flight).
- [ ] **Receiver buffer limits** to avoid memory growth.
- [ ] **Pause/Resume**: receiver can throttle sending (`WINDOW=0` style).

### 5) Congestion Control (Network-Driven)
- [ ] **Rate limiting** for LoRa airtime (token bucket).
- [ ] **Adaptive send rate** based on loss/timeout rates.
- [ ] **Backoff on failure** to reduce network collisions.

### 6) Message Integrity
- [ ] **Checksum/CRC** at the protocol layer (payload hash).
- [ ] **Integrity verification** on receipt; reject corrupted frames.
- [ ] **Optional MAC/signature** for authenticity.

### 7) Fragmentation & Reassembly
- [ ] **Fragment headers** in every chunk: `{cmd_id, chunk_index, chunk_total, payload_len}`.
- [ ] **Reassembly timeout** for incomplete payloads.
- [ ] **Reassembly completion ACK** to confirm delivery.

### 8) Error Handling & Recovery
- [ ] **Explicit error frames** (e.g., `ERR: timeout`, `ERR: bad seq`).
- [ ] **Resync messages** (reset sequence, flush buffers).
- [ ] **Abort command** mechanism if paging fails or a new command supersedes the old.

### 9) Idempotency & Replay Protection
- [ ] **Command nonce** to prevent replayed commands.
- [ ] **Idempotent execution markers** to avoid re-running commands after retransmission.
- [ ] **Client-side retry safety**: re-send safe messages only.

### 10) Observability
- [ ] **Wire logs** for every send/receive with seq/ack/window info.
- [ ] **Metrics**: loss rate, retransmits, RTT estimate, window size.
- [ ] **Diagnostics mode** to surface lost chunks and retries.

## Proposed Message Schema (Baseline)

```
TYPE=<CMD|ACK|DATA|NAK|FIN|PING>
SESSION=<uuid>
SEQ=<uint>
ACK=<uint>            # cumulative ACK
SACK=<list>           # optional missing seq/chunks
CMD_ID=<uint>         # command-level ID
CHUNK=<index>/<total>
LEN=<bytes>
CRC=<hash>
PAYLOAD=<...>
```

## Immediate Gaps in Current Code

- Controller waits for only **one** `more` request and does not do sequential paging (CLI & Web UI). (`controller/send_and_listen.py`, `webui/app.py`)
- Agent sends initial ACK and the first chunk, but there is no sequence/ACK for every chunk. (`app/agent.py`)
- No session or sequence numbers are used beyond the `MSG-ID` timestamp.

## Implementation Phases (Suggested)

1. **Phase 1 — Deterministic chunk paging**
   - Offset/indexed `more` requests and chunk_index/total.
   - ACK for each chunk (or at least every N).

2. **Phase 2 — Reliable retransmission**
   - Per-chunk timers, retries, and duplicate detection.

3. **Phase 3 — Flow + congestion control**
   - Receiver window + sender pacing.

4. **Phase 4 — Session management + integrity**
   - Session handshake, CRC, and replay protection.

---

If you want, I can translate this into a step-by-step implementation plan with code-level tasks for the controller/agent/webui.
