"""Static cards and cached hourly precipitation; standard library only."""
from datetime import datetime, timedelta, timezone
import json
import logging
import math
import os
import subprocess
from pathlib import Path
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from laundry import Laundry

LOG = logging.getLogger('miso-cards')


def normalize(raw, fetched_at):
    hourly = raw['hourly']
    times, chances = hourly['time'], hourly['precipitation_probability']
    if len(times) != len(chances) or len(times) < 12:
        raise ValueError('Incomplete hourly forecast')
    codes = hourly.get('weather_code', [None] * len(times))
    if len(codes) != len(times):
        raise ValueError('Incomplete hourly weather codes')
    hours = []
    for stamp, chance, code in zip(times, chances, codes):
        if not isinstance(stamp, (int, float)) or not math.isfinite(stamp):
            raise ValueError('Invalid forecast timestamp')
        if chance is not None and (not isinstance(chance, (int, float)) or not math.isfinite(chance) or not 0 <= chance <= 100):
            raise ValueError('Invalid precipitation probability')
        if code is not None and (type(code) is not int or not 0 <= code <= 99):
            raise ValueError('Invalid weather code')
        hours.append({'time': stamp, 'chance': chance, 'weatherCode': code})
    if any(b['time'] - a['time'] != 3600 for a, b in zip(hours, hours[1:])):
        raise ValueError('Forecast hours are not consecutive')
    daily = raw.get('daily', {})
    solar = {}
    for event in ('sunrise', 'sunset'):
        solar[event] = [stamp for stamp in daily.get(event, [])
                        if isinstance(stamp, (int, float)) and math.isfinite(stamp) and stamp > 0]
    return {'available': True, 'fetchedAt': fetched_at, 'hours': hours,
            'solar': solar, 'source': 'Open-Meteo'}


class Forecast:
    def __init__(self, config, cache):
        self.config, self.cache = config, Path(cache)
        self.lock = threading.Lock()
        self.value = {'available': False, 'hours': []}
        self.error = None
        try:
            saved = json.loads(self.cache.read_text())
            if saved.get('location') == config:
                self.value = saved['forecast']
        except (OSError, ValueError, KeyError):
            pass

    def snapshot(self):
        with self.lock:
            value = dict(self.value)
            value['error'] = self.error
        value['stale'] = time.time() - value.get('fetchedAt', 0) > 10800
        return value

    def run(self):
        while True:
            try:
                query = urlencode({**self.config, 'hourly': 'precipitation_probability,weather_code',
                                   'daily': 'sunrise,sunset', 'forecast_days': 3,
                                   'timeformat': 'unixtime', 'timezone': 'America/New_York'})
                with urlopen('https://api.open-meteo.com/v1/forecast?' + query, timeout=15) as response:
                    value = normalize(json.load(response), time.time())
                with self.lock:
                    self.value = value
                    self.error = None
                self.cache.parent.mkdir(parents=True, exist_ok=True)
                temporary = self.cache.with_suffix('.tmp')
                temporary.write_text(json.dumps({'location': self.config, 'forecast': value}))
                temporary.replace(self.cache)
                LOG.info('Hourly precipitation forecast refreshed: %d hours', len(value['hours']))
                time.sleep(900)
            except Exception as exc:
                with self.lock:
                    self.error = error_code(exc)
                LOG.exception('Forecast refresh failed; keeping cached data and retrying in 60 seconds')
                time.sleep(60)


def error_code(exc):
    return 'http ' + str(exc.code) if hasattr(exc, 'code') else type(exc).__name__.lower()


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def normalize_aircraft(raw, fetched_at):
    if not isinstance(raw.get('ac'), list):
        raise ValueError('Missing aircraft list')
    stamp = raw.get('now', fetched_at)
    if not number(stamp):
        raise ValueError('Invalid aircraft timestamp')
    if stamp > 1e11:
        stamp /= 1000
    if abs(fetched_at - stamp) > 120:
        raise ValueError('Stale aircraft response')
    aircraft = []
    for a in raw['ac']:
        if not isinstance(a, dict) or a.get('alt_baro') == 'ground':
            continue
        lat, lon, age = a.get('lat'), a.get('lon'), a.get('seen_pos')
        altitude = a.get('alt_geom') if number(a.get('alt_geom')) else a.get('alt_baro')
        if not all(number(v) for v in (lat, lon, age, altitude)) or not -90 <= lat <= 90 or not -180 <= lon <= 180 or not 0 <= age <= 60:
            continue
        def label(key):
            return str(a.get(key) or '').strip()[:16]
        aircraft.append({'id': label('hex'), 'callsign': label('flight'),
                         'aircraftType': label('t'), 'category': label('category'),
                         'latitude': lat, 'longitude': lon, 'altitudeFeet': altitude,
                         'positionAt': stamp-age,
                         'speedKnots': a.get('gs') if number(a.get('gs')) and 0 <= a['gs'] <= 1500 else None,
                         'track': a.get('track') if number(a.get('track')) else None,
                         'verticalFeetPerMinute': a.get('geom_rate', a.get('baro_rate', 0))})
    return {'available': True, 'fetchedAt': fetched_at, 'aircraft': aircraft, 'error': None}


class Aircraft:
    def __init__(self, location, settings):
        self.location, self.settings = location, settings
        self.lock = threading.Lock()
        self.value = {'available': False, 'aircraft': [], 'error': None}

    def snapshot(self):
        with self.lock:
            value = dict(self.value)
        value['settings'] = self.settings
        value['location'] = self.location
        value['stale'] = time.time()-value.get('fetchedAt', 0) > self.settings['maximumPositionAgeSeconds']
        return value

    def run(self):
        delay = self.settings['aircraftPollSeconds']
        while True:
            try:
                url = 'https://api.adsb.lol/v2/point/{latitude}/{longitude}/'.format(**self.location) + str(self.settings['fetchRadiusNauticalMiles'])
                with urlopen(url, timeout=12) as response:
                    value = normalize_aircraft(json.load(response), time.time())
                with self.lock:
                    self.value = value
                LOG.info('Aircraft refreshed: %d usable positions', len(value['aircraft']))
                delay = self.settings['aircraftPollSeconds']
            except Exception as exc:
                with self.lock:
                    self.value = {**self.value, 'error': error_code(exc)}
                delay = min(300, max(60, delay*2))
                LOG.exception('Aircraft API failed; retrying in %d seconds', delay)
            time.sleep(delay)


def load_aircraft_settings(path):
    settings = json.loads(Path(path).read_text())
    limits = {'northAngleDegrees': (0, 360), 'minimumElevationDegrees': (1, 89),
              'maximumDistanceMiles': (1, 100), 'observerElevationFeet': (-1500, 20000),
              'fetchRadiusNauticalMiles': (1, 250), 'aircraftPollSeconds': (30, 300),
              'positionUpdateSeconds': (5, 60), 'maximumPositionAgeSeconds': (30, 120)}
    for key, (low, high) in limits.items():
        if not number(settings.get(key)) or not low <= settings[key] <= high:
            raise ValueError('Invalid aircraft setting: '+key)
    return settings


ISS_REFRESH_SECONDS = 7200
ISS_MAX_AGE_SECONDS = 7*86400


def normalize_iss(text, fetched_at):
    lines = [line.rstrip() for line in text.splitlines() if line.startswith(('1 ', '2 '))]
    if len(lines) != 2 or not lines[0].startswith('1 25544') or not lines[1].startswith('2 25544'):
        raise ValueError('Missing ISS orbital elements')
    for line in lines:
        if len(line) != 69 or not line[-1].isdigit():
            raise ValueError('Invalid TLE length')
        checksum = sum(int(c) if c.isdigit() else 1 if c == '-' else 0 for c in line[:68]) % 10
        if checksum != int(line[68]):
            raise ValueError('Invalid TLE checksum')
    year = int(lines[0][18:20])
    year += 2000 if year < 57 else 1900
    epoch = (datetime(year, 1, 1, tzinfo=timezone.utc) + timedelta(days=float(lines[0][20:32])-1)).timestamp()
    if not -86400 <= fetched_at-epoch <= ISS_MAX_AGE_SECONDS:
        raise ValueError('Stale ISS orbital elements')
    return {'available': True, 'tle': lines, 'epoch': epoch, 'fetchedAt': fetched_at,
            'error': None, 'source': 'CelesTrak'}


class ISSOrbit:
    def __init__(self, cache):
        self.cache = Path(cache)
        self.lock = threading.Lock()
        self.value = {'available': False, 'error': None}
        try:
            saved = json.loads(self.cache.read_text())
            value = normalize_iss('\n'.join(saved['tle']), time.time())
            value['fetchedAt'] = saved['fetchedAt']
            self.value = value
        except (OSError, ValueError, KeyError, TypeError):
            pass

    def snapshot(self):
        with self.lock:
            value = dict(self.value)
        value['stale'] = time.time()-value.get('epoch', 0) > ISS_MAX_AGE_SECONDS
        return value

    def run(self):
        # A service restart reuses fresh disk cache instead of re-querying upstream.
        remaining = ISS_REFRESH_SECONDS-(time.time()-self.value.get('fetchedAt', 0))
        if remaining > 0:
            LOG.info('Reusing cached ISS orbit; next refresh in %d seconds', remaining)
            time.sleep(min(ISS_REFRESH_SECONDS, remaining))
        while True:
            try:
                with urlopen('https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=TLE', timeout=15) as response:
                    value = normalize_iss(response.read().decode('ascii'), time.time())
                self.cache.parent.mkdir(parents=True, exist_ok=True)
                temporary = self.cache.with_suffix('.tmp')
                temporary.write_text(json.dumps(value))
                temporary.replace(self.cache)
                with self.lock:
                    self.value = value
                LOG.info('ISS orbit refreshed; epoch %s', datetime.fromtimestamp(value['epoch'], timezone.utc).isoformat())
            except Exception as exc:
                with self.lock:
                    self.value = {**self.value, 'error': error_code(exc)}
                LOG.exception('ISS orbit refresh failed; retrying in two hours')
            time.sleep(ISS_REFRESH_SECONDS)


def normalize_sensor(raw, entity, humidity=False):
    if raw.get('entity_id') != entity:
        raise ValueError('Sensor identity mismatch')
    attrs = raw.get('attributes', {})
    result = {'entity': entity, 'label': attrs.get('friendly_name', entity),
              'value': None, 'reportedAt': raw.get('last_reported', raw.get('last_updated'))}
    try:
        value = float(raw['state'])
    except (ValueError, TypeError, KeyError):
        return result
    unit = attrs.get('unit_of_measurement')
    if not math.isfinite(value):
        return result
    if humidity:
        if unit == '%' and 0 <= value <= 100:
            result['value'] = value
    elif unit == '°F':
        result['value'] = value
    elif unit == '°C':
        result['value'] = value*9/5+32
    return result


def freezing_status(value, previous, now):
    """Latch ice until a continuous hour above the rounded freezing boundary."""
    if value is None or not math.isfinite(value):
        return {'state': previous.get('state', 'normal'), 'since': None,
                'warmSince': None, 'checkedAt': now}
    continuous = 0 <= now - previous.get('checkedAt', 0) <= 90
    state = previous.get('state', 'normal')
    since = previous.get('since') if continuous else None
    warm = previous.get('warmSince') if continuous else None
    if value < 32:
        state, since, warm = 'below', None, None
    elif math.floor(value + 0.5) == 32:
        warm = None
        if since is None or since > now:
            since = now
        if state != 'normal' or now - since >= 3600:
            state = 'plateau'
    else:
        since = None
        if state != 'normal':
            if warm is None or warm > now:
                warm = now
            if now - warm >= 3600:
                state, warm = 'normal', None
        else:
            warm = None
    return {'state': state, 'since': since, 'warmSince': warm, 'checkedAt': now}


class Thermometer:
    def __init__(self, settings, credential, cache='/var/lib/miso-cards/thermometer.json'):
        self.settings, self.credential = settings, Path(credential)
        self.cache = Path(cache)
        self.lock = threading.Lock()
        self.value = {'available': False, 'sensors': {}, 'error': None, 'emergency': False}
        try:
            saved = json.loads(self.cache.read_text())
            if saved.get('settings') == settings:
                self.value = saved['value']
        except (OSError, ValueError, KeyError):
            pass

    def snapshot(self):
        with self.lock:
            value = dict(self.value)
        value['settings'] = self.settings
        value['stale'] = time.time()-value.get('fetchedAt', 0) > 90
        return value

    def run(self):
        while True:
            try:
                credentials = json.loads(self.credential.read_text())
                humidity_entities = set(self.settings.get('humidities', {}).values()) | {self.settings['humidity']}
                entities = list(dict.fromkeys([self.settings['main'], *self.settings['needles'], *sorted(humidity_entities)]))
                sensors = {}
                for entity in entities:
                    if not entity.startswith('sensor.') or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789_.' for c in entity):
                        raise ValueError('Invalid sensor entity')
                    request = Request(credentials['baseUrl'].rstrip('/')+'/api/states/'+entity,
                                      headers={'Authorization': 'Bearer '+credentials['token']})
                    with urlopen(request, timeout=8) as response:
                        sensors[entity] = normalize_sensor(json.load(response), entity, entity in humidity_entities)
                    if entity == self.settings['emergencySensor'] and sensors[entity]['value'] is not None:
                        with self.lock:
                            self.value = {**self.value, 'emergency': sensors[entity]['value'] > self.settings['emergencyAboveF']}
                hot = sensors[self.settings['emergencySensor']]['value']
                now = time.time()
                freezing = freezing_status(sensors[self.settings['main']]['value'],
                                           self.value.get('freezing', {}), now)
                with self.lock:
                    emergency = self.value['emergency'] if hot is None else hot > self.settings['emergencyAboveF']
                    self.value = {'available': True, 'sensors': sensors, 'fetchedAt': time.time(),
                                  'error': None, 'emergency': emergency, 'freezing': freezing}
                self.cache.parent.mkdir(parents=True, exist_ok=True)
                temporary = self.cache.with_suffix('.tmp')
                temporary.write_text(json.dumps({'settings': self.settings, 'value': self.value}))
                temporary.replace(self.cache)
                LOG.info('Home Assistant thermometer refreshed: %d sensors; emergency=%s', len(sensors), emergency)
            except Exception as exc:
                with self.lock:
                    self.value = {**self.value, 'error': error_code(exc),
                                  'freezing': freezing_status(None, self.value.get('freezing', {}), time.time())}
                # Exception text can contain HTTP request information; log only a safe code.
                LOG.error('Home Assistant read failed: %s; retrying in 30 seconds', error_code(exc))
            time.sleep(30)


class OilTank:
    """On-demand JPEG cache; credentials are only passed to curl over stdin."""
    def __init__(self, credential):
        self.credential = Path(credential)
        self.lock = threading.Lock()
        self.image = None
        self.checked = -float('inf')

    @staticmethod
    def curl_config(config):
        def quote(value):
            return '"' + value.replace('\\', '\\\\').replace('"', '\\"').replace('\r', '\\r').replace('\n', '\\n') + '"'
        lines = ['url = ' + quote(config['url'])]
        if config.get('user'):
            lines += ['user = ' + quote(config['user']), config.get('auth', 'basic')]
        lines += ['header = ' + quote(h) for h in config.get('headers', [])]
        if config.get('insecure'):
            lines.append('insecure')
        return '\n'.join(lines) + '\n'

    def snapshot(self):
        with self.lock:
            if time.monotonic() - self.checked < 5:
                return self.image
            try:
                config = json.loads(self.credential.read_text())
                result = subprocess.run(
                    ['curl', '--disable', '--config', '-', '--silent', '--fail',
                     '--location', '--max-redirs', '3', '--proto', '=http,https',
                     '--proto-redir', '=http,https', '--connect-timeout', '5',
                     '--max-time', '12', '--max-filesize', '10485760'],
                    input=self.curl_config(config).encode(), stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL, timeout=15, check=True)
                image = result.stdout
                if not image.startswith(b'\xff\xd8\xff') or not image.endswith(b'\xff\xd9'):
                    raise ValueError('Not a JPEG')
                self.image = image
                LOG.info('Oil tank JPEG refreshed (%d bytes)', len(image))
            except Exception:
                self.image = None
                # Never log curl errors or config: they may contain credentials.
                LOG.warning('Oil tank snapshot unavailable; retry on next display request')
            self.checked = time.monotonic()
            return self.image


class OilLevel:
    def __init__(self, camera, history):
        self.camera, self.history = camera, Path(history)
        self.lock = threading.Lock()
        self.value = {'available': False}

    def snapshot(self):
        with self.lock:
            value = dict(self.value)
        if time.time()-value.get('fetchedAt', 0) > 3900:
            value['available'] = False
        return value

    def refresh(self):
        from io import BytesIO
        from PIL import Image
        from oil_vision import read_level
        stamp = time.time()
        try:
            jpeg = self.camera.snapshot()
            if not jpeg:
                raise ValueError('Camera unavailable')
            result = read_level(Image.open(BytesIO(jpeg)))
            value = {**result, 'available': True, 'fetchedAt': stamp}
            LOG.info('Oil level: %d%%, segmentation spread %.2f', result['percent'], result['spread'])
        except Exception:
            value = {'available': False, 'fetchedAt': stamp, 'error': 'unavailable'}
            LOG.warning('Oil level unavailable; retrying in five minutes')
        with self.lock:
            self.value = value
        try:
            self.history.parent.mkdir(parents=True, exist_ok=True)
            with self.history.open('a') as stream:
                stream.write(json.dumps(value)+'\n')
        except OSError:
            LOG.warning('Could not append oil observation history')
        return value['available']

    def run(self):
        while True:
            time.sleep(3600 if self.refresh() else 300)


def make_handler(forecast, directory, aircraft=None, iss=None, thermometer=None, oiltank=None, oil_level=None, laundry=None):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=directory, **kwargs)

        def end_headers(self):
            self.send_header('Cache-Control', 'no-store')
            super().end_headers()

        def do_GET(self):
            if urlsplit(self.path).path == '/api/oiltank.jpg':
                body = oiltank.snapshot() if oiltank else None
                self.send_response(200 if body else 503)
                self.send_header('Content-Type', 'image/jpeg' if body else 'text/plain')
                body = body or b'Camera unavailable'
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if urlsplit(self.path).path in ('/api/forecast', '/api/aircraft', '/api/iss', '/api/thermometer', '/api/oil-level', '/api/laundry'):
                source = {'/api/forecast': forecast, '/api/aircraft': aircraft, '/api/iss': iss, '/api/thermometer': thermometer, '/api/oil-level': oil_level, '/api/laundry': laundry}[urlsplit(self.path).path]
                body = json.dumps(source.snapshot() if source else {'available': False, 'error': 'not configured'}).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                super().do_GET()
    return Handler


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    config = json.loads(Path(os.environ.get('MISO_WEATHER_CONFIG', '/etc/miso-cards/weather.json')).read_text())
    if set(config) != {'latitude', 'longitude'} or not -90 <= config['latitude'] <= 90 or not -180 <= config['longitude'] <= 180:
        raise ValueError('Weather config requires valid latitude and longitude')
    forecast = Forecast(config, os.environ.get('MISO_WEATHER_CACHE', '/var/lib/miso-cards/forecast.json'))
    threading.Thread(target=forecast.run, daemon=True).start()
    settings = load_aircraft_settings(os.environ.get('MISO_AIRCRAFT_CONFIG', '/opt/miso-cards/clock/settings.json'))
    aircraft = Aircraft(config, settings)
    threading.Thread(target=aircraft.run, daemon=True).start()
    iss = ISSOrbit('/var/lib/miso-cards/iss-orbit.json')
    threading.Thread(target=iss.run, daemon=True).start()
    thermometer_settings = json.loads(Path('/opt/miso-cards/clock/thermometer.json').read_text())
    credential = Path(os.environ.get('CREDENTIALS_DIRECTORY', '/etc/miso-cards'))/'homeassistant'
    laundry = Laundry(credential)
    threading.Thread(target=laundry.run, daemon=True).start()
    thermometer = Thermometer(thermometer_settings, credential)
    threading.Thread(target=thermometer.run, daemon=True).start()
    oiltank = OilTank(Path(os.environ.get('CREDENTIALS_DIRECTORY', '/etc/miso-cards'))/'oiltank')
    oil_level = OilLevel(oiltank, '/var/lib/miso-cards/oil-observations.jsonl')
    threading.Thread(target=oil_level.run, daemon=True).start()
    LOG.info('Serving cards and cached precipitation API on port 8082')
    ThreadingHTTPServer(('0.0.0.0', 8082), make_handler(forecast, '/opt/miso-cards', aircraft, iss, thermometer, oiltank, oil_level, laundry)).serve_forever()
