#!/usr/bin/env python3
import argparse
import queue
import sys
import time
from typing import Optional

import meshtastic.serial_interface
from pubsub import pub


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
    parser = argparse.ArgumentParser(description="MeshtasticalC2 client send+listen")
    parser.add_argument("--port", required=True)
    parser.add_argument("--channel", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--command", required=True)
    parser.add_argument("--more-delay", type=int, default=1)
    parser.add_argument("--wait-config", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    listener = Listener()
    pub.subscribe(listener.on_receive, "meshtastic.receive")
    pub.subscribe(listener.on_receive, "meshtastic.receive.text")

    print(f"[client] connecting to {args.port}...", flush=True)
    interface = meshtastic.serial_interface.SerialInterface(args.port)
    if args.wait_config:
        wait_for_config = getattr(interface, "waitForConfig", None)
        if callable(wait_for_config):
            wait_for_config()
    print(f"[client] sending: {args.command}", flush=True)
    interface.sendText(args.command, channelIndex=args.channel)

    deadline = time.monotonic() + args.timeout
    last_cmd_id: Optional[str] = None
    output_seen = False
    more_sent = False
    done_seen = False

    while time.monotonic() < deadline:
        remaining = max(0.0, deadline - time.monotonic())
        try:
            text = listener.messages.get(timeout=min(1.0, remaining))
        except queue.Empty:
            if last_cmd_id and not done_seen and not more_sent:
                if time.monotonic() - (deadline - args.timeout) >= args.more_delay:
                    interface.sendText(f"more {last_cmd_id}", channelIndex=args.channel)
                    more_sent = True
            continue

        print(f"\n[TEXT]\n{text}\n", flush=True)
        if text.startswith("MSG-ID:"):
            first_line = text.splitlines()[0]
            last_cmd_id = first_line.replace("MSG-ID:", "").strip()
            if "\nDone" in text:
                done_seen = True
        if "Output:" in text:
            output_seen = True
        if done_seen:
            break
    if not output_seen:
        if done_seen:
            print("[client] completed without Output", flush=True)
        else:
            print(f"[client] max wait {args.timeout}s reached; no Output received", flush=True)
    interface.close()
    return 0 if output_seen else 1


if __name__ == "__main__":
    sys.exit(main())
