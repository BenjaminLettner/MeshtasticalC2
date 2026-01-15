#!/usr/bin/env bash
set -euo pipefail

PORT="/dev/cu.usbmodem1101"
PYTHON_BIN="/Users/benjaminlettner/meshtastic_venv/bin/python"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLIENT_SCRIPT="${SCRIPT_DIR}/send_and_listen.py"
TIMEOUT_SECONDS=45
CHANNEL_INDEX=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --port)
      PORT="${2:-$PORT}"
      shift 2
      ;;
    --timeout)
      TIMEOUT_SECONDS="${2:-$TIMEOUT_SECONDS}"
      shift 2
      ;;
    --channel)
      CHANNEL_INDEX="${2:-$CHANNEL_INDEX}"
      shift 2
      ;;
    --help|-h)
      echo "Usage: $0 [--port PORT] [--timeout SECONDS] [--channel INDEX] [COMMAND]"
      exit 0
      ;;
    *)
      COMMAND="$1"
      shift
      ;;
  esac
done

if [ -z "${COMMAND:-}" ]; then
  read -r -p "Command to send (e.g. whoami): " COMMAND
fi

if [ -z "${COMMAND}" ]; then
  echo "No command entered. Exiting."
  exit 1
fi

"${PYTHON_BIN}" "${CLIENT_SCRIPT}" \
  --port "${PORT}" \
  --channel "${CHANNEL_INDEX}" \
  --timeout "${TIMEOUT_SECONDS}" \
  --command "${COMMAND}"
