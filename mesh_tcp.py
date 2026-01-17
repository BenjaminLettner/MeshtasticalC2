#!/usr/bin/env python3
import queue
import time
from typing import Callable, Dict, List, Optional

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


def send_and_listen(
    command: str,
    port: str,
    channel: int,
    timeout: int,
    more_delay: int = 1,
    wait_config: bool = False,
    on_message: Optional[Callable[[str], None]] = None,
) -> Dict[str, object]:
    listener = Listener()
    pub.subscribe(listener.on_receive, "meshtastic.receive")
    pub.subscribe(listener.on_receive, "meshtastic.receive.text")

    interface = meshtastic.serial_interface.SerialInterface(port)
    try:
        if wait_config:
            wait_for_config = getattr(interface, "waitForConfig", None)
            if callable(wait_for_config):
                wait_for_config()

        interface.sendText(command, channelIndex=channel)

        deadline = time.monotonic() + timeout
        start = time.monotonic()
        last_cmd_id: Optional[str] = None
        active_cmd_id: Optional[str] = None
        outputs: List[str] = []
        raw_messages: List[str] = []
        output_seen = False
        ack_seen = False
        done_seen = False
        last_more_at = 0.0
        more_attempts = 0
        max_more_attempts = 200
        next_index = 0
        awaiting_chunk = False
        retry_delay = max(1.0, float(more_delay))

        while time.monotonic() < deadline:
            remaining = max(0.0, deadline - time.monotonic())
            try:
                text = listener.messages.get(timeout=min(1.0, remaining))
            except queue.Empty:
                if last_cmd_id and not done_seen and more_attempts < max_more_attempts:
                    if time.monotonic() - last_more_at >= retry_delay:
                        if output_seen or ack_seen:
                            interface.sendText(
                                f"more {last_cmd_id} {next_index}",
                                channelIndex=channel,
                            )
                            if on_message:
                                on_message(
                                    f"[controller] request chunk idx={next_index} (attempt {more_attempts + 1})"
                                )
                            last_more_at = time.monotonic()
                            more_attempts += 1
                            awaiting_chunk = True
                            retry_delay = min(retry_delay * 1.8, 60.0)
                continue

            if text.strip().startswith("more "):
                continue

            raw_messages.append(text)
            if on_message:
                on_message(text)

            msg_id: Optional[str] = None
            if text.startswith("MSG-ID:"):
                first_line = text.splitlines()[0]
                msg_id = first_line.replace("MSG-ID:", "").strip()
                if "\nDone" in text or text.rstrip().endswith("Done"):
                    done_seen = True

            if "Cmd received" in text and msg_id:
                ack_seen = True
                active_cmd_id = msg_id
                last_cmd_id = msg_id

            if active_cmd_id and msg_id and msg_id != active_cmd_id:
                continue

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

            if "Output:" in text:
                output_seen = True
                awaiting_chunk = False
                output_text = text.split("Output:", 1)[1].lstrip()
                output_lines = output_text.splitlines()
                if output_lines and output_lines[-1].strip() == "Done":
                    output_text = "\n".join(output_lines[:-1]).rstrip()
                if output_text:
                    outputs.append(output_text)
            elif text.startswith("MSG-ID:") and "Cmd received" not in text:
                trimmed_lines = lines[1:]
                if trimmed_lines and trimmed_lines[-1].strip() == "Done":
                    trimmed_lines = trimmed_lines[:-1]
                output_text = "\n".join(trimmed_lines).strip()
                if output_text:
                    output_seen = True
                    awaiting_chunk = False
                    outputs.append(output_text)

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
