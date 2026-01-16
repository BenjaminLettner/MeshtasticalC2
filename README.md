# MeshtasticalC2

Minimal Meshtastic-based C2 service that executes incoming text commands and sends output back over the mesh.

## Requirements
- Raspberry Pi with a Meshtastic radio attached (WisMesh/RAK4631)
- macOS client with Meshtastic CLI (via venv)
- Both radios joined to the same Meshtastic channel

## 1) Set up the Remote Channel (Both WisMesh Devices)
Use the same **secondary channel** key on both radios so the C2 traffic is private and separate from default traffic.

### Option A: Meshtastic App (recommended)
1) Open the device in Meshtastic mobile or desktop app.
2) Go to **Channels**.
3) Select **Channel 1** (or another secondary slot).
4) Set **Name** to `remote` (or your preferred label).
5) Set **PSK** to a custom value (tap “Generate” or paste a shared key).
6) Save and repeat on the second device with the **same PSK**.

### Option B: CLI (macOS)
```bash
meshtastic --port /dev/cu.usbmodem101 --setch-name 1 remote
meshtastic --port /dev/cu.usbmodem101 --setch-psk 1 <your-psk>
```
Repeat on the second device using its port. Confirm with:
```bash
meshtastic --info --port /dev/cu.usbmodem101
```

## 2) Detect Devices (Host + Pi)

### macOS (Web UI / CLI host)
```bash
ls /dev/cu.usbmodem* /dev/cu.usbserial* 2>/dev/null
```
Pick the device used for the Web UI/CLI (e.g. `/dev/cu.usbmodem101`). Verify it responds:
```bash
meshtastic --info --port /dev/cu.usbmodem101
```

### Raspberry Pi (MiniC2 host)
```bash
ls -l /dev/serial/by-id
```
Use the `usb-RAKwireless_*` link (typically `/dev/ttyACM0`) when starting MiniC2.

## 3) Install on Raspberry Pi
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

## 4) Start the Web UI (macOS)
```bash
MINIC2_WEBUI_PORT=5050 \
MINIC2_CLIENT_PORT=/dev/cu.usbmodem101 \
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

## 5) CLI Client (macOS)
```bash
/Users/benjaminlettner/meshtastic_venv/bin/python client/send_and_listen.py \
  --port /dev/cu.usbmodem101 \
  --command whoami
```

## Session Mode
MiniC2 keeps a per-sender working directory so `cd` persists.

Commands:
```
session start
session status
session end
cd /path
```

## Env
- `MINIC2_PORT` (default: `/dev/ttyACM0`)
- `MINIC2_CHANNEL` (default: `1`)
- `MINIC2_TIMEOUT` (default: `180`)

## Notes
- Replies are chunked to fit Meshtastic message limits.
- The client waits for a `Done` marker or max timeout.
- Over-the-air traffic is encrypted **only if your channel PSK is set** (default PSK is shared).

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

## Communication Scheme (TCP-style)

### States
```text
CLIENT (Web UI / CLI)                          SERVER (MiniC2)
----------------------------------            ---------------------------
IDLE                                          LISTEN
  | cmd "ls"                                      |
  |---------------------------------------------> |
  |                                               | EXEC
  |                                               |  - run command
  |                                               |
  |<--------------------------------------------- | ACK (MSG-ID + Cmd received)
  |                                               |
  |<--------------------------------------------- | OUTPUT chunk 1 (MSG-ID + Output:)
  |                                               | STORE remaining chunks
  | more <MSG-ID>                                 |
  |---------------------------------------------> |
  |<--------------------------------------------- | OUTPUT chunk N (MSG-ID)
  |                                               | ...
  |<--------------------------------------------- | DONE (MSG-ID + Done)
  v                                               v
IDLE                                          LISTEN
```

### Message Formats
```text
Client -> Server
  <command>
  more <MSG-ID>

Server -> Client
  MSG-ID:<id>\nHost:<hostname>\nCmd received: <command>
  MSG-ID:<id>\nOutput:\n<chunk>
  MSG-ID:<id>\n<chunk>
  MSG-ID:<id>\nDone
```

### Notes
- The first output chunk includes the `Output:` prefix.
- Additional chunks omit `Output:` and only include `MSG-ID` + payload.
- Clients can request more output with `more <MSG-ID>` until `Done`.

## Troubleshooting
- **No output / timeouts:** ensure only one client is connected to the radio (Web UI or CLI, not both).
- **Serial disconnects:** close Meshtastic.app or any serial monitor.
- **WisMesh not found:** check `/dev/serial/by-id` and use `/dev/ttyACM0`.
- **Logs:** `tail -n 120 ~/minic2.log` on the Pi.
