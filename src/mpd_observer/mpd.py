import socket
from dataclasses import dataclass
from typing import BinaryIO, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from .settings import MpdSettings


class MpdError(RuntimeError):
    pass


# This is the complete command surface of the adapter. Never accept a raw command
# from an HTTP request or presentation-layer caller.
READ_ONLY_COMMANDS = frozenset({"status", "currentsong", "readpicture", "albumart"})


def _quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _pairs(lines: List[bytes]) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for raw in lines:
        key, separator, value = raw.decode("utf-8", "replace").partition(": ")
        if separator:
            result[key] = value
    return result


class MpdConnection:
    def __init__(self, settings: MpdSettings):
        self.settings = settings
        self.socket: Optional[socket.socket] = None
        self.stream: Optional[BinaryIO] = None
        self.version = ""

    def __enter__(self) -> "MpdConnection":
        self.socket = socket.create_connection(
            (self.settings.host, self.settings.port),
            timeout=self.settings.connect_timeout_seconds,
        )
        self.stream = self.socket.makefile("rwb")
        greeting = self.stream.readline().decode("utf-8", "replace").strip()
        if not greeting.startswith("OK MPD "):
            raise MpdError(f"Unexpected MPD greeting: {greeting}")
        self.version = greeting[7:]
        return self

    def __exit__(self, *_: object) -> None:
        if self.stream:
            self.stream.close()
        if self.socket:
            self.socket.close()

    def command(self, name: str, *arguments: str) -> List[bytes]:
        if name not in READ_ONLY_COMMANDS:
            raise MpdError(f"Command is not read-only allowlisted: {name}")
        if not self.stream:
            raise MpdError("MPD connection is not open")
        line = " ".join([name] + [_quote(argument) for argument in arguments])
        self.stream.write((line + "\n").encode("utf-8"))
        self.stream.flush()
        response: List[bytes] = []
        while True:
            raw = self.stream.readline()
            if not raw:
                raise MpdError("MPD closed the connection")
            stripped = raw.rstrip(b"\r\n")
            if stripped == b"OK":
                return response
            if stripped.startswith(b"ACK "):
                raise MpdError(stripped.decode("utf-8", "replace"))
            response.append(stripped)

    def picture(self, command: str, uri: str, offset: int = 0) -> Optional[Tuple[bytes, str, int]]:
        if command not in ("readpicture", "albumart"):
            raise MpdError("Invalid artwork command")
        if not self.stream:
            raise MpdError("MPD connection is not open")
        self.stream.write(f"{command} {_quote(uri)} {offset}\n".encode("utf-8"))
        self.stream.flush()
        headers: Dict[str, str] = {}
        while True:
            raw = self.stream.readline()
            if not raw:
                raise MpdError("MPD closed the artwork response")
            stripped = raw.rstrip(b"\r\n")
            if stripped == b"OK":
                return None
            if stripped.startswith(b"ACK "):
                return None
            key, separator, value = stripped.decode("utf-8", "replace").partition(": ")
            if separator:
                headers[key] = value
            if key == "binary":
                size = int(value)
                body = self.stream.read(size)
                self.stream.readline()  # newline after the binary block
                trailer = self.stream.readline().rstrip(b"\r\n")
                if trailer != b"OK":
                    raise MpdError("Malformed MPD artwork response")
                return body, headers.get("type", "application/octet-stream"), int(headers.get("size", size))


def read_snapshot(settings: MpdSettings) -> Dict[str, object]:
    with MpdConnection(settings) as client:
        return read_snapshot_from_connection(client)


def read_snapshot_from_connection(client: MpdConnection) -> Dict[str, object]:
    """Read a snapshot without taking ownership of an existing connection."""
    status = _pairs(client.command("status"))
    song = _pairs(client.command("currentsong"))
    elapsed = _number(status.get("elapsed"))
    duration = _number(status.get("duration") or song.get("Time"))
    track = _track(song) if song else None
    return {
        "connected": True,
        "mpd_version": client.version,
        "state": status.get("state", "unknown"),
        "elapsed": elapsed,
        "duration": duration,
        "observed_at": __import__("time").time(),
        "track": track,
    }


def _track(song: Dict[str, str]) -> Dict[str, str]:
    uri = song.get("file", "")
    title = song.get("Title") or _filename(uri)
    artist = song.get("Artist") or song.get("AlbumArtist") or ""
    # Icecast commonly places both fields in Title. Parse the conventional
    # separator locally so observing a stream does not invoke rAudio's PHP and
    # status.sh stack merely to split metadata.
    if not artist and urlparse(uri).scheme in ("http", "https") and " - " in title:
        artist, title = title.split(" - ", 1)
    return {
        "uri": uri,
        "title": title.strip(),
        "artist": artist.strip(),
        "album": song.get("Album") or "",
        "date": song.get("Date", ""),
    }


def read_artwork(settings: MpdSettings, uri: str) -> Optional[Tuple[bytes, str]]:
    # MPD cannot provide embedded artwork for this appliance's infinite HTTP
    # streams. Avoid spending two additional client connections per track on
    # readpicture/albumart probes that are known to return nothing.
    if urlparse(uri).scheme in ("http", "https"):
        return None
    for command in ("readpicture", "albumart"):
        chunks = bytearray()
        content_type = "application/octet-stream"
        total = 1
        while len(chunks) < total:
            with MpdConnection(settings) as client:
                result = client.picture(command, uri, len(chunks))
            if not result:
                break
            body, content_type, total = result
            if not body:
                break
            chunks.extend(body)
        if chunks and len(chunks) >= total:
            return bytes(chunks), content_type
    return None


def _number(value: Optional[str]) -> Optional[float]:
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


def _filename(uri: str) -> str:
    name = uri.rsplit("/", 1)[-1]
    return name.rsplit(".", 1)[0] if name else "Unknown track"
