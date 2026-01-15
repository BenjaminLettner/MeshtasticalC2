# MeshtasticalC2

Minimal Meshtastic-based C2 service that executes incoming text commands and sends output back over the mesh.

## Requirements
- Meshtastic device on the host (`/dev/ttyACM0` by default)
- Docker & Docker Compose on the target machine (optional)

## Run (Docker)
```bash
docker compose up -d --build
```

## Run (Python directly)
```bash
python app/minic2.py --port /dev/ttyACM1 --channel-index 1 --timeout 60
```

## Env
- `MINIC2_PORT` (default: `/dev/ttyACM0`)
- `MINIC2_CHANNEL` (default: `1`)
- `MINIC2_TIMEOUT` (default: `20`)

## Client (Mac)
```bash
./client/send_and_listen.sh --port /dev/cu.usbmodem1101 --timeout 45 whoami
```

## Notes
- Replies are chunked to fit Meshtastic message limits.
- Use `more <MSG-ID>` to fetch additional output.
