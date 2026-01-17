# MeshC2 Compact Header Specification (200-byte LoRa Payload)

This document defines a compact header format for MeshC2 messages to maximize payload space while supporting TCP-like reliability features.

## Goals
- Fit within ~200 bytes per Meshtastic text payload.
- Keep headers <= ~16 bytes (binary) or <= ~60 bytes (text).
- Support sequencing, ACK/NAK, chunk indexing, and session tracking.

---

## Compact Binary Header (Required)

### Fixed Layout (12–16 bytes total)
| Byte(s) | Field | Size | Notes |
|---|---|---|---|
| 0 | Type/Flags | 1 | 4-bit type + 4-bit flags |
| 1–2 | Session ID | 2 | uint16 mapped from handshake |
| 3–4 | Sequence | 2 | uint16 sequence number |
| 5–6 | Ack | 2 | uint16 cumulative ACK |
| 7–8 | Command ID | 2 | uint16 command ID |
| 9 | Chunk index | 1 | 0–255 |
| 10 | Chunk total | 1 | 1–255 |
| 11 | Payload length | 1 | 0–255 |
| 12–13 | CRC16 (opt) | 2 | Optional integrity |

**Total**: 12–14 bytes (without CRC) or 14–16 bytes (with CRC).

---

## Type Codes
- `0x1` = CMD
- `0x2` = DATA
- `0x3` = ACK
- `0x4` = NAK
- `0x5` = FIN
- `0x6` = PING

## Flags (4 bits)
- `0x1` = Retransmission
- `0x2` = SACK present
- `0x4` = CRC present
- `0x8` = Reserved

---

## Payload Budget Examples
- **Binary header (14 bytes)** → ~186 bytes payload.

---

## Notes
- For multi-chunk output, keep `Command ID` constant across chunks.

---

If you want, I can also add parser/serializer helper code to the controller and agent to enforce this layout.
