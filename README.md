# MeshtasticalC2

Minimal Meshtastic-based C2 service that executes incoming text commands and sends output back over the mesh.

## Requirements
- Meshtastic device on the host (`/dev/ttyACM0` by default)

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
/Users/benjaminlettner/meshtastic_venv/bin/python client/send_and_listen.py \
  --port /dev/cu.usbmodem1101 \
  --command whoami
```

## Web UI (Mac)
```bash
MINIC2_WEBUI_PORT=5050 \
MINIC2_CLIENT_PORT=/dev/cu.usbmodem1101 \
MINIC2_CLIENT_CHANNEL=1 \
MINIC2_CLIENT_TIMEOUT=60 \
python webui/app.py
```
Open http://localhost:5050

### Run Web UI permanently (launchd)
```bash
cp webui/meshtasticalc2.webui.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/meshtasticalc2.webui.plist
```
Stop it with:
```bash
launchctl unload ~/Library/LaunchAgents/meshtasticalc2.webui.plist
```

## Notes
- Replies are chunked to fit Meshtastic message limits.
- Use `more <MSG-ID>` to fetch additional output.
