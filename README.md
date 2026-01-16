# MeshtasticalC2

Minimal Meshtastic-based C2 service that executes incoming text commands and sends output back over the mesh.

## Requirements
- Raspberry Pi with a Meshtastic radio attached (WisMesh/RAK4631)
- macOS client with Meshtastic CLI (via venv)
- Both radios joined to the same Meshtastic channel

## Deployment (Raspberry Pi)
```bash
git clone https://github.com/BenjaminLettner/MeshtasticalC2.git
cd MeshtasticalC2
python3 -m venv ~/meshtasticalc2_venv
~/meshtasticalc2_venv/bin/pip install -r requirements.txt
```

Run the service in the background:
```bash
nohup ~/meshtasticalc2_venv/bin/python ~/MeshtasticalC2/app/minic2.py \
  --port /dev/ttyACM0 \
  --channel-index 1 \
  --timeout 180 \
  > ~/minic2.log 2>&1 &
```

## Run (Python directly)
```bash
python app/minic2.py --port /dev/ttyACM0 --channel-index 1 --timeout 180
```

## Env
- `MINIC2_PORT` (default: `/dev/ttyACM0`)
- `MINIC2_CHANNEL` (default: `1`)
- `MINIC2_TIMEOUT` (default: `180`)

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
MINIC2_CLIENT_TIMEOUT=180 \
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
- The client waits for a `Done` marker or max timeout.

## Communication Flow
```text
 Mac Web UI / CLI
        |
        | 1) TEXT command: "ls"
        v
  [Meshtastic Mesh]
        |
        v
 Raspberry Pi + MiniC2
        |
        | 2) Executes command locally
        | 3) Sends output chunks as TEXT with MSG-ID
        | 4) Final chunk ends with "Done"
        v
 Mac Web UI / CLI renders output
```

1) Client sends a TEXT message command (e.g., `whoami`).
2) MiniC2 executes the command on the Pi.
3) Output is chunked into TEXT messages and sent back with `MSG-ID`.
4) The final chunk includes `Done` so the client can stop waiting.

## Troubleshooting
- **No output / timeouts:** ensure only one client is connected to the radio (Web UI or CLI, not both).
- **Serial disconnects:** close Meshtastic.app or any serial monitor.
- **WisMesh not found:** check `/dev/serial/by-id` and use `/dev/ttyACM0`.
- **Logs:** `tail -n 120 ~/minic2.log` on the Pi.
