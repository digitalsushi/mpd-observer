import hashlib
import json
import os
import re
import threading
import time
import unicodedata
from pathlib import Path
from typing import Dict, Optional, Tuple
from urllib.error import HTTPError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from .settings import MusicBrainzSettings


_MUSICBRAINZ = "https://musicbrainz.org/ws/2/recording"
_COVER_ART = "https://coverartarchive.org/release-group/"
_lock = threading.Lock()
_last_musicbrainz_request = 0.0
_METADATA_ONLY = object()


def read_artwork(settings: MusicBrainzSettings, artist: str, title: str) -> Optional[Tuple[bytes, str]]:
    if not settings.enabled or not artist.strip() or not title.strip():
        return None
    key = hashlib.sha256((_normalize(artist) + "\0" + _normalize(title)).encode()).hexdigest()
    image_path = settings.cache_directory / f"{key}.image"
    metadata_path = settings.cache_directory / f"{key}.json"
    with _lock:
        cached = _read_cache(settings, image_path, metadata_path)
        if cached is not False:
            outcome = ("metadata cache hit" if cached is _METADATA_ONLY else
                       "negative cache hit" if cached is None else "image cache hit")
            print(f"Artwork MusicBrainz: {outcome} for {artist} — {title}", flush=True)
            return None if cached is _METADATA_ONLY else cached
        print(f"Artwork MusicBrainz: searching for {artist} — {title}", flush=True)
        result = _lookup(settings, artist, title)
        settings.cache_directory.mkdir(parents=True, exist_ok=True)
        if result is None:
            _write_json(metadata_path, {
                "cached_at": time.time(), "found": False, "matched": False,
                "duration_seconds": None, "album": None,
            })
            print(f"Artwork MusicBrainz: no confident match for {artist} — {title}", flush=True)
            return None
        body, content_type, source, duration_seconds, album = result
        if not body:
            _write_json(metadata_path, {
                "cached_at": time.time(), "found": False, "matched": True,
                "duration_seconds": duration_seconds,
                "album": album,
                "artist": artist, "title": title,
            })
            print(f"Artwork MusicBrainz: track matched without cover for {artist} — {title}", flush=True)
            return None
        _atomic_write(image_path, body)
        _write_json(metadata_path, {
            "cached_at": time.time(), "found": True, "matched": True,
            "content_type": content_type,
            "source": source, "artist": artist, "title": title,
            "duration_seconds": duration_seconds,
            "album": album,
        })
        print(f"Artwork MusicBrainz: cached {len(body)} bytes for {artist} — {title}", flush=True)
        return body, content_type


def read_duration(settings: MusicBrainzSettings, artist: str, title: str) -> Optional[float]:
    """Resolve and cache the track, then return MusicBrainz's duration if known."""
    read_artwork(settings, artist, title)
    key = hashlib.sha256((_normalize(artist) + "\0" + _normalize(title)).encode()).hexdigest()
    try:
        metadata = json.loads((settings.cache_directory / f"{key}.json").read_text(encoding="utf-8"))
        value = metadata.get("duration_seconds")
        return float(value) if value is not None and float(value) > 0 else None
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None


def read_track_info(settings: MusicBrainzSettings, artist: str, title: str) -> Dict[str, object]:
    """Resolve and return cached online metadata used by the presentation."""
    read_artwork(settings, artist, title)
    key = hashlib.sha256((_normalize(artist) + "\0" + _normalize(title)).encode()).hexdigest()
    try:
        metadata = json.loads((settings.cache_directory / f"{key}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {}
    result: Dict[str, object] = {}
    duration = metadata.get("duration_seconds")
    if isinstance(duration, (int, float)) and duration > 0:
        result["duration"] = float(duration)
    album = metadata.get("album")
    if isinstance(album, str) and album.strip():
        result["album"] = album.strip()
    return result


def _read_cache(settings, image_path: Path, metadata_path: Path):
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if "duration_seconds" not in metadata or "album" not in metadata:
            return False
        # A confident track match is useful permanent metadata even when Cover
        # Art Archive has no image. Older cache entries predate `matched`, so
        # infer it from their successful fields during migration.
        matched = bool(metadata.get(
            "matched",
            metadata.get("found") or metadata.get("album") or metadata.get("duration_seconds"),
        ))
        age = time.time() - float(metadata["cached_at"])
        ttl = settings.positive_ttl_seconds if matched else settings.negative_ttl_seconds
        if ttl > 0 and age > ttl:
            return False
        if not metadata.get("found"):
            return _METADATA_ONLY if matched else None
        body = image_path.read_bytes()
        return (body, str(metadata.get("content_type", "image/jpeg"))) if len(body) <= settings.max_bytes else False
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return False


def _lookup(settings, artist: str, title: str) -> Optional[Tuple[bytes, str, str, Optional[float], str]]:
    query = f'recording:"{_lucene(title)}" AND artist:"{_lucene(artist)}"'
    url = _MUSICBRAINZ + "?" + urlencode({"query": query, "fmt": "json", "limit": 5})
    recording = _matching_recording(_get_musicbrainz_json(url, settings), artist, title, settings.minimum_match_score)
    if not recording:
        return None
    length = recording.get("length")
    duration_seconds = float(length) / 1000 if isinstance(length, (int, float)) and length > 0 else None
    album = _release_title(recording)
    group_id = _release_group_id(recording)
    if not group_id:
        return b"", "", "", duration_seconds, album
    try:
        art = _get_json(_COVER_ART + group_id, settings)
    except HTTPError as error:
        if error.code == 404:
            return b"", "", "", duration_seconds, album
        raise
    image_url = _front_image_url(art)
    if not image_url or not image_url.startswith("https://coverartarchive.org/"):
        return b"", "", "", duration_seconds, album
    request = Request(image_url, headers={"User-Agent": settings.user_agent})
    with urlopen(request, timeout=settings.timeout_seconds) as response:
        if not _trusted_image_url(response.geturl()):
            return None
        content_type = response.headers.get_content_type()
        if not content_type.startswith("image/"):
            return None
        body = response.read(settings.max_bytes + 1)
    if len(body) > settings.max_bytes:
        return None
    return body, content_type, image_url, duration_seconds, album


def _get_json(url: str, settings: MusicBrainzSettings) -> Dict[str, object]:
    request = Request(url, headers={"User-Agent": settings.user_agent, "Accept": "application/json"})
    with urlopen(request, timeout=settings.timeout_seconds) as response:
        value = json.load(response)
    return value if isinstance(value, dict) else {}


def _get_musicbrainz_json(url: str, settings: MusicBrainzSettings) -> Dict[str, object]:
    global _last_musicbrainz_request
    delay = 1.05 - (time.monotonic() - _last_musicbrainz_request)
    if delay > 0:
        time.sleep(delay)
    try:
        return _get_json(url, settings)
    finally:
        _last_musicbrainz_request = time.monotonic()


def _matching_recording(data, artist: str, title: str, minimum_score: int):
    for recording in data.get("recordings", []):
        credits = recording.get("artist-credit", [])
        credited = "".join(str(item.get("name", "")) for item in credits if isinstance(item, dict))
        if (int(recording.get("score", 0)) >= minimum_score
                and _normalize(str(recording.get("title", ""))) == _normalize(title)
                and _normalize(credited) == _normalize(artist)):
            return recording
    return None


def _release_group_id(recording) -> str:
    releases = sorted(recording.get("releases", []), key=lambda item: item.get("status") != "Official")
    for release in releases:
        group = release.get("release-group") or {}
        if group.get("id"):
            return str(group["id"])
    return ""


def _release_title(recording) -> str:
    releases = sorted(recording.get("releases", []), key=lambda item: item.get("status") != "Official")
    for release in releases:
        group = release.get("release-group") or {}
        title = group.get("title") or release.get("title")
        if title:
            return str(title)
    return ""


def _front_image_url(data) -> str:
    images = sorted(data.get("images", []), key=lambda item: not (item.get("front") and item.get("approved")))
    for image in images:
        if image.get("front"):
            thumbnails = image.get("thumbnails") or {}
            return str(thumbnails.get("500") or thumbnails.get("large") or image.get("image") or "")
    return ""


def _trusted_image_url(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and (host in ("coverartarchive.org", "archive.org") or host.endswith(".archive.org"))


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).casefold()
    return " ".join(re.sub(r"[^\w]+", " ", value).split())


def _lucene(value: str) -> str:
    return re.sub(r'([+\-!(){}\[\]^"~*?:\\/]|&&|\|\|)', r"\\\1", value)


def _write_json(path: Path, value: object) -> None:
    _atomic_write(path, json.dumps(value, indent=2).encode("utf-8"))


def _atomic_write(path: Path, body: bytes) -> None:
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    temporary.write_bytes(body)
    temporary.replace(path)
