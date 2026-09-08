import argparse
import json
import mimetypes
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Type
from urllib.parse import parse_qs, urlparse

from .debug_log import ConsoleLog, TeeStream
from .mpd import read_artwork
from .observer import Observer
from .online_artwork import read_artwork as read_online_artwork
from .raudio import read_artwork as read_raudio_artwork
from .settings import Settings, default_settings_path, load_settings
from .weather import WeatherObserver


STATIC = Path(__file__).parent / "static"


def make_handler(settings: Settings, observer: Observer,
                 weather: WeatherObserver, console: ConsoleLog) -> Type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/api/now-playing":
                self._json(observer.snapshot())
                return
            if parsed.path == "/api/settings":
                display = settings.display
                self._json({"title": display.title, "width": display.width,
                            "height": display.height, "theme": display.theme,
                            "fallback_artwork": display.fallback_artwork,
                            "refresh_interval_ms": display.refresh_interval_ms,
                            "show_clock": display.show_clock,
                            "track_text_colors": list(display.track_text_colors.values())})
                return
            if parsed.path == "/api/weather":
                self._json(weather.snapshot())
                return
            if parsed.path == "/debug":
                body = console.page(settings.debug.refresh_seconds)
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if parsed.path == "/api/artwork":
                uri = parse_qs(parsed.query).get("uri", [""])[0]
                if not uri:
                    self.send_error(400, "Missing uri")
                    return
                track = observer.snapshot().get("track")
                current_uri = track.get("uri") if isinstance(track, dict) else None
                if uri != current_uri:
                    self.send_error(403, "Artwork is limited to the current track")
                    return
                try:
                    artwork = read_artwork(settings.mpd, uri)
                    if artwork:
                        print(f"Artwork MPD: found {len(artwork[0])} bytes", flush=True)
                    if not artwork:
                        reference = observer.snapshot().get("raudio_artwork")
                        if isinstance(reference, str):
                            artwork = read_raudio_artwork(settings.raudio, reference)
                            if artwork:
                                print(f"Artwork rAudio: found {len(artwork[0])} bytes", flush=True)
                    if not artwork:
                        current = observer.snapshot().get("track")
                        if isinstance(current, dict):
                            artwork = read_online_artwork(
                                settings.musicbrainz,
                                str(current.get("artist", "")),
                                str(current.get("title", "")),
                            )
                except Exception:
                    artwork = None
                if not artwork:
                    self.send_error(404, "Artwork unavailable")
                    return
                body, content_type = artwork
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                # The track-specific browser URL includes a cache-busting token,
                # allowing the foreground and blurred copy to reuse one response.
                self.send_header("Cache-Control", "private, max-age=300")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            relative = "index.html" if parsed.path == "/" else parsed.path.lstrip("/")
            path = (STATIC / relative).resolve()
            if STATIC.resolve() not in path.parents or not path.is_file():
                self.send_error(404)
                return
            body = path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, value: object) -> None:
            body = json.dumps(value).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            if urlparse(self.path).path == "/debug":
                return
            print(f"HTTP {self.address_string()} - {format % args}")

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the MPD Observer kiosk server")
    parser.add_argument("--settings", type=Path, default=default_settings_path())
    args = parser.parse_args()
    settings = load_settings(args.settings)
    console = ConsoleLog(settings.debug.maximum_lines)
    original_stdout, original_stderr = sys.stdout, sys.stderr
    sys.stdout = TeeStream(original_stdout, console)
    sys.stderr = TeeStream(original_stderr, console)
    observer = Observer(settings.mpd, settings.raudio, settings.musicbrainz)
    observer.start()
    weather = WeatherObserver(settings.weather)
    weather.start()
    server = ThreadingHTTPServer((settings.server.host, settings.server.port),
                                 make_handler(settings, observer, weather, console))
    print(f"MPD Observer: http://{settings.server.host}:{settings.server.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        observer.stop()
        weather.stop()
        server.server_close()
        sys.stdout, sys.stderr = original_stdout, original_stderr


if __name__ == "__main__":
    main()
