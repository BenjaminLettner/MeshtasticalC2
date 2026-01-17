#!/usr/bin/env python3
import argparse
import os
import re
import sys
import time
from pathlib import Path
from typing import List

from serial.tools import list_ports

sys.path.append(str(Path(__file__).resolve().parents[1]))

from mesh_tcp import send_and_listen


PORT_PATTERN = re.compile(r"usbmodem|usbserial|ttyACM|ttyUSB", re.IGNORECASE)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MeshtasticalC2 controller send+listen")
    parser.add_argument("--port")
    parser.add_argument("--channel", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--command", required=True)
    parser.add_argument("--more-delay", type=int, default=1)
    parser.add_argument("--wait-config", action="store_true")
    parser.add_argument(
        "--port-wait",
        type=int,
        default=30,
        help="Seconds to wait for a Meshtastic device if no port is provided",
    )
    return parser.parse_args()


def _list_candidate_ports() -> List[str]:
    ports = [port.device for port in list_ports.comports()]
    if not ports:
        return []
    preferred = [port for port in ports if PORT_PATTERN.search(port)]
    return preferred or ports


def _resolve_port(args: argparse.Namespace) -> str:
    if args.port:
        return args.port
    env_port = os.getenv("MESH_PORT") or os.getenv("MESHTASTIC_PORT")
    if env_port:
        return env_port

    deadline = time.monotonic() + max(0, args.port_wait)
    delay = 1.0
    while True:
        candidates = _list_candidate_ports()
        if candidates:
            return candidates[0]
        if time.monotonic() >= deadline:
            break
        time.sleep(delay)
        delay = min(10.0, delay * 1.5)

    raise RuntimeError(
        "No serial devices detected. Provide --port or attach a Meshtastic device."
    )


def main() -> int:
    args = parse_args()
    port = _resolve_port(args)
    print(f"[controller] connecting to {port}...", flush=True)

    def handle_message(message: str) -> None:
        if message.startswith("[controller]"):
            print(message, flush=True)
        else:
            print(f"\n[TEXT]\n{message}\n", flush=True)

    result = send_and_listen(
        command=args.command,
        port=port,
        channel=args.channel,
        timeout=args.timeout,
        more_delay=args.more_delay,
        wait_config=args.wait_config,
        on_message=handle_message,
    )

    if not result["received"]:
        print(f"[controller] max wait {args.timeout}s reached; no Output received", flush=True)
        return 1
    if not result["output"]:
        print("[controller] completed without Output", flush=True)
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
