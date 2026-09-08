import threading
import time
from typing import Dict

from .mpd import read_snapshot
from .online_artwork import read_track_info
from .raudio import read_status as read_raudio_status
from .settings import MpdSettings, MusicBrainzSettings, RAudioSettings


class Observer:
    def __init__(self, settings: MpdSettings, raudio: RAudioSettings,
                 musicbrainz: MusicBrainzSettings):
        self.settings = settings
        self.raudio = raudio
        self.musicbrainz = musicbrainz
        self._lock = threading.Lock()
        self._snapshot: Dict[str, object] = self._offline("Starting")
        self._stop = threading.Event()
        self._stream_key = ""
        self._stream_started_at = 0.0
        self._online_key = ""
        self._raudio_key = ""
        self._raudio_status = None
        self._thread = threading.Thread(target=self._run, name="mpd-observer", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def snapshot(self) -> Dict[str, object]:
        with self._lock:
            return dict(self._snapshot)

    def _set(self, snapshot: Dict[str, object]) -> None:
        with self._lock:
            self._snapshot = snapshot

    def _offline(self, message: str) -> Dict[str, object]:
        return {"connected": False, "state": "offline", "message": message,
                "observed_at": time.time(), "track": None, "elapsed": None, "duration": None}

    def _run(self) -> None:
        delay = 1.0
        while not self._stop.is_set():
            try:
                snapshot = read_snapshot(self.settings)
                self._enrich(snapshot)
                self._set(snapshot)
                self._schedule_online_duration(snapshot)
                delay = 1.0
                self._stop.wait(self.settings.stream_metadata_poll_seconds)
            except Exception as error:
                self._set(self._offline(str(error)))
                self._stop.wait(delay)
                delay = min(delay * 2, self.settings.reconnect_max_seconds)

    def _enrich(self, snapshot: Dict[str, object]) -> None:
        if not self.raudio.enabled:
            return
        track = snapshot.get("track")
        if not isinstance(track, dict):
            return
        # rAudio's endpoint launches status.sh. Query it once per raw MPD title,
        # then reuse that result instead of spawning shell work every poll.
        key = "\0".join(str(track.get(field, "")) for field in ("uri", "title"))
        if key != self._raudio_key:
            self._raudio_key = key
            try:
                self._raudio_status = read_raudio_status(self.raudio)
            except Exception:
                # Optional enrichment must never make healthy MPD look offline.
                self._raudio_status = None
        status = self._raudio_status
        if not status or status["uri"] != track.get("uri"):
            return
        for key in ("title", "artist", "album"):
            if status[key]:
                track[key] = status[key]
        if status["artwork"]:
            snapshot["raudio_artwork"] = status["artwork"]

    def _schedule_online_duration(self, snapshot: Dict[str, object]) -> None:
        track = snapshot.get("track")
        if not self.musicbrainz.enabled or not isinstance(track, dict) or snapshot.get("duration"):
            return
        artist = str(track.get("artist", ""))
        title = str(track.get("title", ""))
        if not artist or not title:
            return
        key = artist.casefold() + "\0" + title.casefold()
        if key != self._stream_key:
            self._stream_key = key
            self._stream_started_at = time.time()
        if key == self._online_key:
            return
        self._online_key = key
        threading.Thread(
            target=self._resolve_online_info,
            args=(key, artist, title),
            name="online-track-duration",
            daemon=True,
        ).start()

    def _resolve_online_info(self, key: str, artist: str, title: str) -> None:
        try:
            info = read_track_info(self.musicbrainz, artist, title)
        except Exception as error:
            print(f"Track metadata MusicBrainz: unavailable for {artist} — {title}: {error}", flush=True)
            return
        if not info:
            print(f"Track metadata MusicBrainz: unknown for {artist} — {title}", flush=True)
            return
        with self._lock:
            track = self._snapshot.get("track")
            current_key = ""
            if isinstance(track, dict):
                current_key = str(track.get("artist", "")).casefold() + "\0" + str(track.get("title", "")).casefold()
            if current_key != key:
                return
            album = info.get("album")
            if album and isinstance(track, dict) and not track.get("album"):
                track["album"] = album
                self._snapshot["album_online"] = True
            duration = info.get("duration")
            if isinstance(duration, (int, float)) and duration > 0:
                now = time.time()
                self._snapshot["duration"] = duration
                self._snapshot["elapsed"] = max(0.0, now - self._stream_started_at)
                self._snapshot["observed_at"] = now
                self._snapshot["duration_estimated"] = True
        details = []
        if info.get("album"):
            details.append(f'album "{info["album"]}"')
        if info.get("duration"):
            details.append(f'{float(info["duration"]):.0f}s')
        print(f"Track metadata MusicBrainz: {', '.join(details)} for {artist} — {title}", flush=True)
