#!/usr/bin/env python3
import os
import queue
import threading
import time
from typing import List, Optional

from flask import Flask, jsonify, request, send_from_directory
import meshtastic.serial_interface
from pubsub import pub

APP_ROOT = os.path.dirname(os.path.abspath(__file__))

PORT = os.getenv("MINIC2_CLIENT_PORT", "/dev/cu.usbmodem1101")
CHANNEL = int(os.getenv("MINIC2_CLIENT_CHANNEL", "1"))
TIMEOUT = int(os.getenv("MINIC2_CLIENT_TIMEOUT", "60"))
MORE_DELAY = int(os.getenv("MINIC2_CLIENT_MORE_DELAY", "3"))
WAIT_CONFIG = os.getenv("MINIC2_CLIENT_WAIT_CONFIG", "false").lower() == "true"
WEBUI_HOST = os.getenv("MINIC2_WEBUI_HOST", "0.0.0.0")
WEBUI_PORT = int(os.getenv("MINIC2_WEBUI_PORT", "5000"))

COMMAND_LOCK = threading.Lock()

app = Flask(__name__, static_folder="static")


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


@app.route("/")
def index() -> object:
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/command", methods=["POST"])
def run_command() -> object:
    payload = request.get_json(silent=True) or {}
    command = (payload.get("command") or "").strip()
    if not command:
        return jsonify({"error": "Command is required"}), 400

    port = (payload.get("port") or "").strip() or PORT
    channel = payload.get("channel") if payload.get("channel") is not None else CHANNEL
    timeout = payload.get("timeout") if payload.get("timeout") is not None else TIMEOUT

    try:
        channel = int(channel)
        timeout = int(timeout)
    except ValueError:
        return jsonify({"error": "Invalid channel or timeout"}), 400

    with COMMAND_LOCK:
        result = _send_and_listen(command, port=port, channel=channel, timeout=timeout)

    return jsonify(result)


def _send_and_listen(command: str, port: str, channel: int, timeout: int) -> dict:
    listener = Listener()
    pub.subscribe(listener.on_receive, "meshtastic.receive")
    pub.subscribe(listener.on_receive, "meshtastic.receive.text")

    interface = meshtastic.serial_interface.SerialInterface(port)
    try:
        if WAIT_CONFIG:
            wait_for_config = getattr(interface, "waitForConfig", None)
            if callable(wait_for_config):
                wait_for_config()

        interface.sendText(command, channelIndex=channel)

        deadline = time.monotonic() + timeout
        start = time.monotonic()
        last_cmd_id: Optional[str] = None
        outputs: List[str] = []
        raw_messages: List[str] = []
        output_seen = False
        more_sent = False

        while time.monotonic() < deadline:
            remaining = max(0.0, deadline - time.monotonic())
            try:
                text = listener.messages.get(timeout=min(1.0, remaining))
            except queue.Empty:
                if last_cmd_id and not output_seen and not more_sent:
                    if time.monotonic() - start >= MORE_DELAY:
                        interface.sendText(f"more {last_cmd_id}", channelIndex=channel)
                        more_sent = True
                continue

            raw_messages.append(text)
            if text.startswith("MSG-ID:"):
                first_line = text.splitlines()[0]
                last_cmd_id = first_line.replace("MSG-ID:", "").strip()

            if "Output:" in text:
                output_seen = True
                output_text = text.split("Output:", 1)[1].lstrip()
                if output_text:
                    outputs.append(output_text)

            if "No more output" in text:
                break

        unique_outputs: List[str] = []
        for output in outputs:
            if output not in unique_outputs:
                unique_outputs.append(output)

        output_text = "\n".join(unique_outputs).strip()
        duration = round(time.monotonic() - start, 2)

        return {
            "command": command,
            "output": output_text,
            "raw": raw_messages,
            "received": output_seen,
            "duration": duration,
        }
    finally:
        pub.unsubscribe(listener.on_receive, "meshtastic.receive")
        pub.unsubscribe(listener.on_receive, "meshtastic.receive.text")
        interface.close()


if __name__ == "__main__":
    app.run(host=WEBUI_HOST, port=WEBUI_PORT, debug=False)
