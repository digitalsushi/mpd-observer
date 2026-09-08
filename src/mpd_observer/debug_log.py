import html
import threading
from collections import deque
from datetime import datetime
from typing import Deque, List, TextIO


class ConsoleLog:
    """Thread-safe, process-lifetime tail of console output."""

    def __init__(self, maximum_lines: int = 2500):
        self._lines: Deque[str] = deque(maxlen=maximum_lines)
        self._lock = threading.Lock()
        self._last_message = None
        self._repeat_count = 0

    def append(self, line: str) -> List[str]:
        emitted = []
        with self._lock:
            if line == self._last_message:
                self._repeat_count += 1
                return emitted
            if self._repeat_count:
                summary = f"Last message repeated {self._repeat_count} times"
                self._append_timestamped(summary)
                emitted.append(summary)
            self._append_timestamped(line)
            emitted.append(line)
            self._last_message = line
            self._repeat_count = 0
        return emitted

    def _append_timestamped(self, line: str) -> None:
        timestamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
        self._lines.append(f"{timestamp}  {line}")

    def page(self, refresh_seconds: int = 5) -> bytes:
        with self._lock:
            content = "\n".join(self._lines)
        escaped = html.escape(content, quote=False)
        return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<meta http-equiv="refresh" content="{refresh_seconds}"><title>MPD Observer — Debug</title>
<style>html{{color-scheme:dark}}body{{margin:0;background:#080a0d;color:#d8dce3;font:14px/1.45 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}}pre{{box-sizing:border-box;min-height:100vh;margin:0;padding:1rem;white-space:pre-wrap;overflow-wrap:anywhere}}</style>
</head><body><pre>{escaped}</pre><script>scrollTo(0,document.body.scrollHeight)</script></body></html>""".encode("utf-8")


class TeeStream:
    """Forward writes to the terminal while collecting complete lines."""

    def __init__(self, stream: TextIO, console: ConsoleLog):
        self._stream = stream
        self._console = console
        self._partial = ""
        self._lock = threading.Lock()

    def write(self, value: str) -> int:
        with self._lock:
            parts = (self._partial + value).split("\n")
            self._partial = parts.pop()
            for line in parts:
                for emitted in self._console.append(line):
                    self._stream.write(emitted + "\n")
            self._stream.flush()
            return len(value)

    def flush(self) -> None:
        self._stream.flush()

    def isatty(self) -> bool:
        return self._stream.isatty()
