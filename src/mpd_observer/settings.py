from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict


@dataclass(frozen=True)
class MpdSettings:
    host: str
    port: int
    connect_timeout_seconds: float
    reconnect_max_seconds: float
    stream_metadata_poll_seconds: float = 10


@dataclass(frozen=True)
class ServerSettings:
    host: str
    port: int


@dataclass(frozen=True)
class DebugSettings:
    maximum_lines: int
    refresh_seconds: int


@dataclass(frozen=True)
class DeploymentSettings:
    host: str
    username: str
    identity_file: Path
    directory: str


@dataclass(frozen=True)
class RAudioSettings:
    enabled: bool
    base_url: str
    timeout_seconds: float
    max_bytes: int


@dataclass(frozen=True)
class MusicBrainzSettings:
    enabled: bool
    cache_directory: Path
    positive_ttl_seconds: int
    negative_ttl_seconds: int
    timeout_seconds: float
    max_bytes: int
    minimum_match_score: int
    user_agent: str


@dataclass(frozen=True)
class WeatherSettings:
    enabled: bool
    provider: str
    latitude: float
    longitude: float
    refresh_interval_seconds: int
    severe_forecast_hours: int
    stale_after_seconds: int
    timeout_seconds: float
    cache_file: Path
    mock_condition: str
    mock_temperature_f: float


@dataclass(frozen=True)
class DisplaySettings:
    title: str
    width: int
    height: int
    theme: Dict[str, str]
    fallback_artwork: bool
    refresh_interval_ms: int
    show_clock: bool
    track_text_colors: Dict[str, str]


@dataclass(frozen=True)
class Settings:
    mpd: MpdSettings
    raudio: RAudioSettings
    musicbrainz: MusicBrainzSettings
    weather: WeatherSettings
    server: ServerSettings
    debug: DebugSettings
    deployment: DeploymentSettings
    display: DisplaySettings


def default_settings_path() -> Path:
    user_path = Path.home() / ".mpd-observer" / "SETTINGS.yaml"
    return user_path if user_path.is_file() else Path("SETTINGS.yaml")


def _section(data: Dict[str, Any], name: str) -> Dict[str, Any]:
    value = data.get(name)
    if not isinstance(value, dict):
        raise ValueError(f"SETTINGS.yaml requires a '{name}' mapping")
    return value


def load_settings(path: Path) -> Settings:
    with path.open("r", encoding="utf-8") as stream:
        raw = _parse_settings_yaml(stream.read())

    mpd = _section(raw, "mpd")
    server = _section(raw, "server")
    debug = _section(raw, "debug")
    deployment = raw.get("deployment", {})
    if not isinstance(deployment, dict):
        raise ValueError("SETTINGS.yaml 'deployment' must be a mapping")
    display = _section(raw, "display")
    artwork = _section(raw, "artwork")
    raudio = _section(artwork, "raudio_http")
    musicbrainz = _section(artwork, "musicbrainz")
    weather = _section(raw, "weather")
    theme = _section(display, "theme")
    track_text_colors = _section(display, "track_text_colors")
    required_colors = ("background", "foreground", "muted", "accent")
    missing = [name for name in required_colors if name not in theme]
    if missing:
        raise ValueError("display.theme is missing: " + ", ".join(missing))

    cache_directory = Path(str(musicbrainz.get("cache_directory", ".cache/mpd-observer/artwork")))
    if not cache_directory.is_absolute():
        cache_directory = Path.cwd() / cache_directory
    weather_cache = Path(str(weather.get("cache_file", ".cache/mpd-observer/weather.json")))
    if not weather_cache.is_absolute():
        weather_cache = Path.cwd() / weather_cache

    return Settings(
        mpd=MpdSettings(
            host=str(mpd["host"]),
            port=int(mpd.get("port", 6600)),
            connect_timeout_seconds=float(mpd.get("connect_timeout_seconds", 3)),
            reconnect_max_seconds=float(mpd.get("reconnect_max_seconds", 30)),
            stream_metadata_poll_seconds=max(
                1, float(mpd.get("stream_metadata_poll_seconds", 10))
            ),
        ),
        raudio=RAudioSettings(
            enabled=bool(raudio.get("enabled", False)),
            base_url=str(raudio.get("base_url", "")).rstrip("/"),
            timeout_seconds=float(raudio.get("timeout_seconds", 3)),
            max_bytes=int(raudio.get("max_bytes", 10 * 1024 * 1024)),
        ),
        musicbrainz=MusicBrainzSettings(
            enabled=bool(musicbrainz.get("enabled", False)),
            cache_directory=cache_directory,
            positive_ttl_seconds=int(musicbrainz.get("positive_ttl_seconds", 30 * 86400)),
            negative_ttl_seconds=int(musicbrainz.get("negative_ttl_seconds", 6 * 3600)),
            timeout_seconds=float(musicbrainz.get("timeout_seconds", 10)),
            max_bytes=int(musicbrainz.get("max_bytes", 10 * 1024 * 1024)),
            minimum_match_score=int(musicbrainz.get("minimum_match_score", 95)),
            user_agent=str(musicbrainz.get("user_agent", "MPDObserver/0.1")),
        ),
        weather=WeatherSettings(
            enabled=bool(weather.get("enabled", False)),
            provider=str(weather.get("provider", "open_meteo")),
            latitude=float(weather["latitude"]),
            longitude=float(weather["longitude"]),
            refresh_interval_seconds=max(300, int(weather.get("refresh_interval_seconds", 3600))),
            severe_forecast_hours=max(1, int(weather.get("severe_forecast_hours", 6))),
            stale_after_seconds=int(weather.get("stale_after_seconds", 10800)),
            timeout_seconds=float(weather.get("timeout_seconds", 10)),
            cache_file=weather_cache,
            mock_condition=str(weather.get("mock_condition", "")).strip().lower(),
            mock_temperature_f=float(weather.get("mock_temperature_f", 72)),
        ),
        server=ServerSettings(
            host=str(server.get("host", "127.0.0.1")),
            port=int(server.get("port", 8080)),
        ),
        debug=DebugSettings(
            maximum_lines=max(1, int(debug.get("maximum_lines", 2500))),
            refresh_seconds=max(1, int(debug.get("refresh_seconds", 5))),
        ),
        deployment=DeploymentSettings(
            host=str(deployment.get("host", "")),
            username=str(deployment.get("username", "")),
            identity_file=Path(str(deployment.get(
                "identity_file", "~/.ssh/id_rsa"
            ))).expanduser(),
            directory=str(deployment.get("directory", "mpd-observer")),
        ),
        display=DisplaySettings(
            title=str(display.get("title", "MPD Observer")),
            width=int(display.get("width", 1920)),
            height=int(display.get("height", 480)),
            theme={name: str(theme[name]) for name in required_colors},
            fallback_artwork=bool(display.get("fallback_artwork", True)),
            refresh_interval_ms=int(display.get("refresh_interval_ms", 2000)),
            show_clock=bool(display.get("show_clock", True)),
            track_text_colors={str(name): str(value)
                               for name, value in track_text_colors.items()},
        ),
    )


def _parse_settings_yaml(source: str) -> Dict[str, Any]:
    """Parse the mapping-and-scalars subset used by SETTINGS.yaml.

    Keeping the configuration schema deliberately small lets the kiosk start on
    a stock Raspberry Pi Python installation without a YAML package dependency.
    """
    root: Dict[str, Any] = {}
    stack = [(-1, root)]
    for number, original in enumerate(source.splitlines(), 1):
        if not original.strip() or original.lstrip().startswith("#"):
            continue
        indent = len(original) - len(original.lstrip(" "))
        if "\t" in original[:indent]:
            raise ValueError(f"SETTINGS.yaml line {number}: tabs are not supported")
        key, separator, text = original.strip().partition(":")
        if not separator or not key:
            raise ValueError(f"SETTINGS.yaml line {number}: expected key: value")
        while stack[-1][0] >= indent:
            stack.pop()
        parent = stack[-1][1]
        value_text = text.strip()
        if not value_text:
            child: Dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = _scalar(value_text)
    return root


def _scalar(value: str) -> Any:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    lowered = value.lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    try:
        return float(value) if "." in value else int(value)
    except ValueError:
        return value
