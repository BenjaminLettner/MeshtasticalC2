# MeshtasticalC2

Minimal Meshtastic-based C2 service that executes incoming text commands and sends output back over the mesh.

## Requirements
- Meshtastic device on the host (`/dev/ttyACM0` by default)
- Docker & Docker Compose on the target machine

## Run (Docker)
```bash
docker compose up -d --build
```

## Env
- `MINIC2_PORT` (default: `/dev/ttyACM0`)
- `MINIC2_CHANNEL` (default: `1`)
- `MINIC2_TIMEOUT` (default: `20`)

## Notes
- Replies are chunked to fit Meshtastic message limits.
- Use `more <MSG-ID>` to fetch additional output.
