#!/usr/bin/env python3
import argparse
import logging
import os
import socket
import subprocess
import threading
import time
from collections import deque
from typing import Deque, Dict, List, Optional, Tuple

import meshtastic.serial_interface
from pubsub import pub

MAX_MESSAGE_LEN = 200
ACK_TEMPLATE = "MSG-ID:{cmd_id}\nHost:{host}\nCmd received: {command}"
OUTPUT_PREFIX = "MSG-ID:{cmd_id}\nCHUNK:{index}/{total}\nOutput:\n"
OUTPUT_SUFFIX = ""


class OutputBuffer:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._buffers: Dict[str, List[str]] = {}

    def store(self, cmd_id: str, chunks: List[str]) -> None:
        with self._lock:
            self._buffers[cmd_id] = chunks

    def get(self, cmd_id: str, index: int) -> Tuple[Optional[str], int]:
        with self._lock:
            chunks = self._buffers.get(cmd_id)
            if not chunks:
                return None, 0
            if index < 0 or index >= len(chunks):
                return None, len(chunks)
            return chunks[index], len(chunks)

    def finalize(self, cmd_id: str) -> None:
        with self._lock:
            self._buffers.pop(cmd_id, None)


class AgentService:
    def __init__(self, port: str, channel_index: int, timeout: int) -> None:
        self.port = port
        self.channel_index = channel_index
        self.timeout = timeout
        self.host = socket.gethostname()
        self.logger = logging.getLogger("agent")
        self.interface = meshtastic.serial_interface.SerialInterface(self.port)
        self.output_buffer = OutputBuffer()
        self._command_lock = threading.Lock()
        self._sessions: Dict[str, Dict[str, str]] = {}

        pub.subscribe(self._on_receive, "meshtastic.receive")

    def _send_text(self, text: str, destination_id: Optional[str] = None) -> None:
        try:
            if destination_id:
                self.interface.sendText(text, destinationId=destination_id, channelIndex=self.channel_index)
            else:
                self.interface.sendText(text, channelIndex=self.channel_index)
            self.logger.info("Sent: %s", text.replace("\n", " | "))
        except Exception as exc:
            self.logger.exception("Send failed: %s", exc)

    def _send_text_repeated(
        self,
        text: str,
        destination_id: Optional[str] = None,
        repeats: int = 1,
        delay: float = 0.0,
        also_broadcast: bool = False,
    ) -> None:
        for attempt in range(repeats):
            self._send_text(text, destination_id=destination_id)
            if attempt < repeats - 1:
                time.sleep(delay)

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
            parts = text.split()
            cmd_id = parts[1].strip() if len(parts) > 1 else ""
            try:
                index = int(parts[2]) if len(parts) > 2 else 0
            except ValueError:
                index = 0
            destination_id = packet.get("fromId")
            self.logger.info("Paging request: cmd=%s idx=%s from=%s", cmd_id, index, destination_id)
            self._handle_more(cmd_id, destination_id, index)
            return

        self.logger.info("Received command: %s", text)
        destination_id = packet.get("fromId")
        threading.Thread(
            target=self._execute_and_respond,
            args=(text, destination_id, time.monotonic()),
            daemon=True,
        ).start()

    def _get_session(self, sender_id: str) -> Dict[str, str]:
        session = self._sessions.get(sender_id)
        if not session:
            session = {"cwd": os.path.expanduser("~")}
            self._sessions[sender_id] = session
        return session

    def _end_session(self, sender_id: str) -> None:
        self._sessions.pop(sender_id, None)

    def _handle_session_command(self, command: str, sender_id: str) -> Optional[Tuple[str, str, int]]:
        normalized = command.strip().lower()
        if normalized.startswith("session"):
            parts = normalized.split()
            if len(parts) == 1 or parts[1] == "status":
                session = self._get_session(sender_id)
                return (f"Session active\nCWD: {session['cwd']}", "", 0)
            if parts[1] == "start":
                session = self._get_session(sender_id)
                return (f"Session started\nCWD: {session['cwd']}", "", 0)
            if parts[1] == "end":
                self._end_session(sender_id)
                return ("Session ended", "", 0)
            return ("Usage: session start | session status | session end", "", 0)

        if normalized == "cd" or normalized.startswith("cd "):
            session = self._get_session(sender_id)
            target = command.split(" ", 1)[1].strip() if " " in command else "~"
            target = os.path.expanduser(target)
            if not os.path.isabs(target):
                target = os.path.normpath(os.path.join(session["cwd"], target))
            if not os.path.isdir(target):
                return ("", f"cd: no such directory: {target}", 1)
            session["cwd"] = target
            return (f"CWD: {target}", "", 0)

        return None

    def _handle_more(self, cmd_id: str, destination_id: Optional[str], index: int) -> None:
        chunk, total = self.output_buffer.get(cmd_id, index)
        if not chunk:
            self.logger.info("No chunk available: cmd=%s idx=%s total=%s", cmd_id, index, total)
            self._send_text(f"MSG-ID:{cmd_id}\nDone", destination_id=destination_id)
            if total == 0 or index >= max(total - 1, 0):
                self.output_buffer.finalize(cmd_id)
            return
        self.logger.info("Sending chunk: cmd=%s idx=%s total=%s", cmd_id, index, total)
        self._send_text(chunk, destination_id=destination_id)
        if total and index >= total - 1:
            self.output_buffer.finalize(cmd_id)

    def _execute_and_respond(
        self,
        command: str,
        destination_id: Optional[str],
        received_at: float,
    ) -> None:
        with self._command_lock:
            cmd_id = str(int(time.time() * 1000))
            exec_start = time.monotonic()
            session_result = None
            if destination_id:
                session_result = self._handle_session_command(command, destination_id)
            if session_result:
                result = session_result
            else:
                cwd = None
                if destination_id:
                    session = self._get_session(destination_id)
                    cwd = session["cwd"]
                result = self._run_command(command, cwd=cwd)
            exec_done = time.monotonic()
            self.logger.info(
                "Command result for %s: exit=%s elapsed=%.3fs",
                cmd_id,
                result[2],
                exec_done - exec_start,
            )
            total_elapsed = exec_done - received_at
            timing_line = f"Timing: total={total_elapsed:.3f}s exec={exec_done - exec_start:.3f}s"
            chunks = self._format_output(cmd_id, result, timing_line)

            if not chunks:
                self._send_text(
                    f"MSG-ID:{cmd_id}\nOutput:\n<no output>\n{timing_line}",
                    destination_id=destination_id,
                )
                return

            if len(chunks) == 1:
                first_chunk = chunks[0]
                self._send_text_repeated(first_chunk, destination_id=destination_id)
                return

            ack = ACK_TEMPLATE.format(cmd_id=cmd_id, host=self.host, command=command)
            self._send_text(ack, destination_id=destination_id)
            time.sleep(0.1)
            self.output_buffer.store(cmd_id, chunks)

    def _run_command(self, command: str, cwd: Optional[str] = None) -> Tuple[str, str, int]:
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=cwd,
        )
        try:
            stdout, stderr = process.communicate(timeout=self.timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
            stderr = (stderr or "") + f"\nCommand timed out after {self.timeout}s"
        return stdout or "", stderr or "", process.returncode

    def _format_output(
        self,
        cmd_id: str,
        result: Tuple[str, str, int],
        timing_line: str,
    ) -> List[str]:
        stdout, stderr, exit_code = result
        combined = stdout
        if stderr:
            combined = combined + ("\n" if combined else "") + stderr
        combined = combined.strip()
        if not combined:
            combined = "<no output>"

        combined = f"{combined}\n{timing_line}\nDone"

        max_payload = MAX_MESSAGE_LEN

        def build_chunks(total_guess: int) -> List[str]:
            chunks_local: List[str] = []
            remaining = combined
            index = 0
            while remaining:
                if index == 0:
                    header = OUTPUT_PREFIX.format(cmd_id=cmd_id, index=index, total=total_guess)
                else:
                    header = f"MSG-ID:{cmd_id}\nCHUNK:{index}/{total_guess}\n"
                available = max_payload - len(header)
                if available <= 0:
                    return [f"MSG-ID:{cmd_id}\nOutput too long"]
                chunk_body = remaining[:available]
                remaining = remaining[available:]
                chunks_local.append(header + chunk_body)
                index += 1
            return chunks_local

        total_guess = 1
        chunks = build_chunks(total_guess)
        while len(chunks) != total_guess:
            total_guess = len(chunks)
            chunks = build_chunks(total_guess)

        return chunks

    def run(self) -> None:
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MeshtasticalC2 agent service")
    parser.add_argument("--port", default=os.getenv("MINIC2_PORT", "/dev/ttyACM0"))
    parser.add_argument("--channel-index", type=int, default=int(os.getenv("MINIC2_CHANNEL", "1")))
    parser.add_argument("--timeout", type=int, default=int(os.getenv("MINIC2_TIMEOUT", "20")))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    agent = AgentService(args.port, args.channel_index, args.timeout)
    logging.getLogger("agent").info("Agent service running on %s channel %s", args.port, args.channel_index)
    agent.run()


if __name__ == "__main__":
    main()
