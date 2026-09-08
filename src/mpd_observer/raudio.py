import json
from typing import Dict, Optional, Tuple
from urllib.parse import quote, urlencode, urljoin, urlparse
from urllib.request import Request, urlopen

from .settings import RAudioSettings


# rAudio-specific behavior is intentionally contained in this optional adapter.
# The command is fixed: callers cannot use its general-purpose command gateway.
_STATUS_COMMAND = "/srv/http/bash/status.sh"


def read_status(settings: RAudioSettings) -> Optional[Dict[str, str]]:
    if not settings.enabled or not settings.base_url:
        return None
    body = urlencode({"cmd": "bash", "bash": _STATUS_COMMAND}).encode("ascii")
    request = Request(settings.base_url + "/cmd.php", data=body, method="POST")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urlopen(request, timeout=settings.timeout_seconds) as response:
        raw = json.load(response)
    if not isinstance(raw, dict):
        return None
    return {
        "uri": _text(raw.get("file")),
        "title": _text(raw.get("Title")),
        "artist": _text(raw.get("Artist")),
        "album": _text(raw.get("Album")),
        "artwork": _text(raw.get("coverart") or raw.get("stationcover")),
    }


def read_artwork(settings: RAudioSettings, reference: str) -> Optional[Tuple[bytes, str]]:
    url = _same_origin_url(settings.base_url, reference)
    if not settings.enabled or not url:
        return None
    request = Request(url, method="GET")
    with urlopen(request, timeout=settings.timeout_seconds) as response:
        content_type = response.headers.get_content_type()
        if not content_type.startswith("image/"):
            return None
        body = response.read(settings.max_bytes + 1)
    if len(body) > settings.max_bytes:
        return None
    return body, content_type


def _same_origin_url(base_url: str, reference: str) -> Optional[str]:
    if not reference:
        return None
    # rAudio sometimes returns a percent-encoded absolute filesystem path. It is
    # used by its web UI as an HTTP path, so retain the escaping and add a slash.
    if reference.startswith("%2F") or reference.startswith("%2f"):
        reference = "/" + reference
    candidate = urljoin(base_url + "/", reference)
    base = urlparse(base_url)
    parsed = urlparse(candidate)
    if (parsed.scheme, parsed.netloc) != (base.scheme, base.netloc):
        return None
    if parsed.scheme not in ("http", "https"):
        return None
    return candidate


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""
