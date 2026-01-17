# MeshC2 Updates Log

Track notable changes to MeshC2 here (features, fixes, ops changes).

## 2026-01-17
- Added controller auto-detect for Meshtastic serial ports (CLI now accepts `--port` as optional and scans ports).
- Added protocol gap analysis and client autodetect improvement docs.
- Updated Pi service configuration to run `app/agent.py` under `meshc2.service` (systemd unit on Pi).
