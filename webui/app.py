#!/usr/bin/env python3
import os
import re
import threading
from pathlib import Path
from typing import List, Optional

from flask import Flask, jsonify, request, send_from_directory
from serial.tools import list_ports

import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from mesh_tcp import send_and_listen

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


@app.route("/")
def index() -> object:
    return send_from_directory(app.static_folder, "index.html")


@app.route("/config")
def config() -> object:
    return send_from_directory(app.static_folder, "config.html")


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
    timeout = payload.get("timeout") if payload.get("timeout") is not None else TIMEOUT

    try:
        channel = int(channel)
        timeout = int(timeout)
    except ValueError:
        return jsonify({"error": "Invalid channel or timeout"}), 400

    if not port:
        available_ports = [p.device for p in list_ports.comports()]
        if not available_ports:
            return jsonify({"error": "No serial devices detected"}), 400
        preferred = [
            p
            for p in available_ports
            if re.search(r"usbmodem|usbserial|ttyACM|ttyUSB", p, re.IGNORECASE)
        ]
        if PORT and PORT in available_ports:
            port = PORT
        elif preferred:
            port = preferred[0]
        else:
            port = available_ports[0]

    try:
        with COMMAND_LOCK:
            result = send_and_listen(
                command=command,
                port=port,
                channel=channel,
                timeout=timeout,
                more_delay=MORE_DELAY,
                wait_config=WAIT_CONFIG,
            )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 503

    return jsonify(result)


if __name__ == "__main__":
    app.run(host=WEBUI_HOST, port=WEBUI_PORT, debug=False)
