#!/usr/bin/env python3
import argparse
import os
import queue
import re
import sys
import time
from typing import List, Optional

import meshtastic.serial_interface
from pubsub import pub
from serial.tools import list_ports


PORT_PATTERN = re.compile(r"usbmodem|usbserial|ttyACM|ttyUSB", re.IGNORECASE)


class Listener:
    def __init__(self) -> None:
        self.messages = queue.Queue()

    def on_receive(self, packet, interface) -> None:
        decoded = packet.get("decoded", {})
        if decoded.get("portnum") != "TEXT_MESSAGE_APP":
            return
        text = decoded.get("text")
        if not text and "payload" in decoded:
            text = decoded["payload"].decode("utf-8", errors="ignore")
        if text:
            self.messages.put(text)


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
    listener = Listener()
    pub.subscribe(listener.on_receive, "meshtastic.receive")
    pub.subscribe(listener.on_receive, "meshtastic.receive.text")

    port = _resolve_port(args)
    print(f"[controller] connecting to {port}...", flush=True)
    interface = meshtastic.serial_interface.SerialInterface(port)
    if args.wait_config:
        wait_for_config = getattr(interface, "waitForConfig", None)
        if callable(wait_for_config):
            wait_for_config()
    while not listener.messages.empty():
        try:
            listener.messages.get_nowait()
        except queue.Empty:
            break

    print(f"[controller] sending: {args.command}", flush=True)
    interface.sendText(args.command, channelIndex=args.channel)

    deadline = time.monotonic() + args.timeout
    last_cmd_id: Optional[str] = None
    active_cmd_id: Optional[str] = None
    output_seen = False
    done_seen = False
    ack_seen = False
    last_more_at = 0.0
    more_attempts = 0
    max_more_attempts = 200
    next_index = 0
    awaiting_chunk = False

    while time.monotonic() < deadline:
        remaining = max(0.0, deadline - time.monotonic())
        try:
            text = listener.messages.get(timeout=min(1.0, remaining))
        except queue.Empty:
            if last_cmd_id and not done_seen and more_attempts < max_more_attempts:
                if time.monotonic() - last_more_at >= args.more_delay:
                    if (output_seen or ack_seen) and not awaiting_chunk:
                        interface.sendText(
                            f"more {last_cmd_id} {next_index}",
                            channelIndex=args.channel,
                        )
                        last_more_at = time.monotonic()
                        more_attempts += 1
                        awaiting_chunk = True
            continue

        if text.strip().startswith("more "):
            continue

        print(f"\n[TEXT]\n{text}\n", flush=True)
        if text.startswith("MSG-ID:"):
            first_line = text.splitlines()[0]
            msg_id = first_line.replace("MSG-ID:", "").strip()
            if active_cmd_id is None:
                active_cmd_id = msg_id
            if msg_id != active_cmd_id:
                continue
            last_cmd_id = msg_id
            if "\nDone" in text:
                done_seen = True
        if "Cmd received" in text:
            ack_seen = True
        if text.startswith("MSG-ID:"):
            lines = text.splitlines()
            chunk_line = next((line for line in lines if line.startswith("CHUNK:")), None)
            if chunk_line:
                try:
                    index = int(chunk_line.split(":", 1)[1].split("/", 1)[0])
                except (ValueError, IndexError):
                    index = None
                if index is not None:
                    output_seen = True
                    awaiting_chunk = False
                    if index == next_index:
                        next_index += 1
            elif "Output:" in text or ("Cmd received" not in text and len(lines) > 1):
                output_seen = True
                awaiting_chunk = False
        if done_seen:
            break
    if not output_seen:
        if done_seen:
            print("[controller] completed without Output", flush=True)
        else:
            print(f"[controller] max wait {args.timeout}s reached; no Output received", flush=True)
    interface.close()
    return 0 if output_seen else 1


if __name__ == "__main__":
    sys.exit(main())
