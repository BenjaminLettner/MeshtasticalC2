#!/usr/bin/env python3
import os
import re
import queue
import threading
import time
from typing import List, Optional

from flask import Flask, jsonify, request, send_from_directory
import meshtastic.serial_interface
from pubsub import pub
from serial.tools import list_ports

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


@app.route("/api/ports", methods=["GET"])
def list_serial_ports() -> object:
    ports = [port.device for port in list_ports.comports()]
    preferred = [p for p in ports if re.search(r"usbmodem|usbserial|ttyACM|ttyUSB", p, re.IGNORECASE)]
    return jsonify({"ports": preferred or ports})


@app.route("/api/command", methods=["POST"])
def run_command() -> object:
    payload = request.get_json(silent=True) or {}
    command = (payload.get("command") or "").strip()
    if not command:
        return jsonify({"error": "Command is required"}), 400

    port = (payload.get("port") or "").strip()
    channel = payload.get("channel") if payload.get("channel") is not None else CHANNEL

    try:
        channel = int(channel)
    except ValueError:
        return jsonify({"error": "Invalid channel or timeout"}), 400

    if not port:
        available_ports = [p.device for p in list_ports.comports()]
        if not available_ports:
            return jsonify({"error": "No serial devices detected"}), 400
        port = available_ports[0]

    try:
        with COMMAND_LOCK:
            result = _send_and_listen(command, port=port, channel=channel, timeout=TIMEOUT)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 503

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
        done_seen = False

        while time.monotonic() < deadline:
            remaining = max(0.0, deadline - time.monotonic())
            try:
                text = listener.messages.get(timeout=min(1.0, remaining))
            except queue.Empty:
                if last_cmd_id and not done_seen and not more_sent:
                    if time.monotonic() - start >= MORE_DELAY:
                        interface.sendText(f"more {last_cmd_id}", channelIndex=channel)
                        more_sent = True
                continue

            raw_messages.append(text)
            if text.startswith("MSG-ID:"):
                first_line = text.splitlines()[0]
                last_cmd_id = first_line.replace("MSG-ID:", "").strip()
                if "\nDone" in text or text.rstrip().endswith("Done"):
                    done_seen = True

            if "Output:" in text:
                output_seen = True
                output_text = text.split("Output:", 1)[1].lstrip()
                output_lines = output_text.splitlines()
                if output_lines and output_lines[-1].strip() == "Done":
                    output_text = "\n".join(output_lines[:-1]).rstrip()
                if output_text:
                    outputs.append(output_text)
            elif text.startswith("MSG-ID:") and "Cmd received" not in text:
                lines = text.splitlines()[1:]
                if lines and lines[-1].strip() == "Done":
                    lines = lines[:-1]
                output_text = "\n".join(lines).strip()
                if output_text:
                    output_seen = True
                    outputs.append(output_text)

            if "No more output" in text:
                break

            if done_seen:
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
