import json
import os
import threading
import time
from pathlib import Path
from typing import Dict
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .settings import WeatherSettings


_ENDPOINT = "https://api.open-meteo.com/v1/forecast"
_MOCK_CONDITIONS = {"clear", "cloud", "rain", "thunder"}
_THUNDER_CODES = {95, 96, 99}
_HEAVY_RAIN_CODES = {65, 67, 82}


class WeatherObserver:
    def __init__(self, settings: WeatherSettings):
        self.settings = settings
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._snapshot: Dict[str, object] = {"available": False}
        self._thread = threading.Thread(target=self._run, name="weather-observer", daemon=True)

    def start(self) -> None:
        if not self.settings.enabled:
            return
        if self.settings.mock_condition:
            if self.settings.mock_condition not in _MOCK_CONDITIONS:
                raise ValueError("weather.mock_condition must be clear, cloud, rain, thunder, or empty")
            self._snapshot = {
                "available": True, "condition": self.settings.mock_condition,
                "temperature_f": self.settings.mock_temperature_f,
                "observed_at": time.time(), "stale": False, "mock": True,
                "severe_weather_alert": self.settings.mock_condition == "thunder",
            }
            return
        if self.settings.provider != "open_meteo":
            raise ValueError("Only the open_meteo weather provider is supported")
        self._load_cache()
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def snapshot(self) -> Dict[str, object]:
        with self._lock:
            value = dict(self._snapshot)
        observed = value.get("observed_at")
        value["stale"] = bool(
            observed and time.time() - float(observed) > self.settings.stale_after_seconds
        )
        return value

    def _run(self) -> None:
        while not self._stop.is_set():
            current = self.snapshot()
            observed = float(current.get("observed_at", 0))
            age = time.time() - observed
            if current.get("available") and age < self.settings.refresh_interval_seconds:
                self._stop.wait(self.settings.refresh_interval_seconds - age)
                continue
            try:
                value = _fetch(self.settings)
                with self._lock:
                    self._snapshot = value
                _write_cache(self.settings.cache_file, value)
                print(
                    f'Weather Open-Meteo: {value["temperature_f"]:.0f}°F, {value["condition"]}',
                    flush=True,
                )
                self._stop.wait(self.settings.refresh_interval_seconds)
            except Exception as error:
                print(f"Weather Open-Meteo: unavailable: {error}", flush=True)
                self._stop.wait(min(300, self.settings.refresh_interval_seconds))

    def _load_cache(self) -> None:
        try:
            value = json.loads(self.settings.cache_file.read_text(encoding="utf-8"))
            if (isinstance(value, dict) and value.get("available")
                    and "severe_weather_alert" in value):
                self._snapshot = value
        except (OSError, ValueError, json.JSONDecodeError):
            pass


def _fetch(settings: WeatherSettings) -> Dict[str, object]:
    query = urlencode({
        "latitude": settings.latitude,
        "longitude": settings.longitude,
        "current": "temperature_2m,weather_code,cloud_cover,precipitation",
        "hourly": "weather_code",
        "forecast_hours": settings.severe_forecast_hours,
        "temperature_unit": "fahrenheit",
        "timezone": "auto",
    })
    request = Request(_ENDPOINT + "?" + query, headers={"User-Agent": "MPDObserver/0.1"})
    with urlopen(request, timeout=settings.timeout_seconds) as response:
        raw = json.load(response)
    current = raw.get("current") or {}
    temperature = current.get("temperature_2m")
    code = current.get("weather_code")
    if not isinstance(temperature, (int, float)) or not isinstance(code, int):
        raise ValueError("Open-Meteo response lacks current temperature or weather code")
    forecast_codes = (raw.get("hourly") or {}).get("weather_code") or []
    forecast_codes = [value for value in forecast_codes[:settings.severe_forecast_hours]
                      if isinstance(value, int)]
    return {
        "available": True,
        "temperature_f": float(temperature),
        "condition": classify_weather_code(code),
        "weather_code": code,
        "cloud_cover": current.get("cloud_cover"),
        "precipitation": current.get("precipitation"),
        "observed_at": time.time(),
        "source_time": current.get("time", ""),
        "severe_weather_alert": severe_weather_alert(forecast_codes),
        "stale": False,
    }


def classify_weather_code(code: int) -> str:
    if code == 0:
        return "clear"
    if code in _THUNDER_CODES:
        return "thunder"
    if 51 <= code <= 86:
        return "rain"
    return "cloud"


def severe_weather_alert(forecast_codes: list) -> bool:
    """Return true for forecast mentions of thunder or explicitly heavy rain."""
    return any(code in _THUNDER_CODES or code in _HEAVY_RAIN_CODES
               for code in forecast_codes)


def _write_cache(path: Path, value: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
    temporary.replace(path)
