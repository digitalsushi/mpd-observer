# MPD Observer

A read-only, kiosk-style now-playing display for an unusually wide Raspberry Pi
screen (approximately 8.8 × 3 inches).

This repository is both a real proof of concept and a place to learn an
effective Codex workflow. Requirements will evolve as the display hardware and
upstream MPD environment become available.

## Product intent

The observer connects to a nearby Music Player Daemon (MPD), presents current
playback metadata and album artwork, and never controls or mutates MPD.

Initial capabilities:

- Observe player changes without aggressive polling.
- Read the current track, playback state, and elapsed time.
- Retrieve album artwork when MPD exposes it.
- Render a legible, attractive interface for a very wide, short display.
- Recover cleanly when MPD or the network is unavailable.

## Non-goals

- Playback controls, queue editing, volume changes, or any other MPD mutation.
- Dependence on the source code or internal data model of the upstream MPD
  project.
- Submitting listening history to Last.fm or another scrobbling service.

## Design boundary

All MPD communication belongs behind a small observer interface. The rest of
the application consumes our own stable `NowPlaying` model and must not depend
on raw MPD responses. See [docs/architecture.md](docs/architecture.md).

## Run the v1 kiosk

The MPD endpoint, web-server binding, display geometry, colors, clock, and
refresh interval are configured in `$HOME/.mpd-observer/SETTINGS.yaml` when it
exists, otherwise root-level `SETTINGS.yaml`. The repository file contains
non-operational public defaults and Walt Disney World weather coordinates.
Relative cache paths remain relative to the application's working directory.
The optional `artwork.raudio_http` section enables rAudio stream metadata and
artwork as a fallback; standard MPD artwork remains the primary source. The
observer takes one read-only MPD snapshot every
`mpd.stream_metadata_poll_seconds`; it does not hold `idle` connections open.
The heavier rAudio `status.sh` enrichment runs only once per raw stream title
and is reused until MPD reports a new title.
The optional `artwork.musicbrainz` section adds a final online lookup through
MusicBrainz and the Cover Art Archive. Results and misses are cached on disk;
the cache location and lifetimes are configurable. With
`positive_ttl_seconds: 0`, confident track matches—including album and duration
without cover art—remain cached indefinitely. Only unidentified tracks expire
on the negative TTL and retry upstream. Delete entries from the configured
cache directory to evict successful matches manually.
When a stream has no MPD duration but MusicBrainz supplies one, the kiosk shows
an eight-step estimated pie indicator below the artist.
If MusicBrainz identifies the album but no image is available, the kiosk uses
the album title as subdued, oversized background typography instead of showing
the generic artwork placeholder. When no album is known, it uses the artist as
the atmospheric fallback instead.

The optional weather ornament uses Open-Meteo current conditions at the
coordinates in `SETTINGS.yaml`. External data is refreshed no more than hourly,
cached on disk, and marked as stale after the configured interval. Set
`weather.mock_condition` to `clear`, `cloud`, `rain`, or `thunder` for UI work;
leave it empty for live data.

The next `weather.severe_forecast_hours` hours are also checked for forecast
thunderstorms or explicitly heavy rain. A matching forecast draws a thick red
border around the kiosk until a later hourly weather refresh clears the alert.

`/debug` shows an HTML-escaped, automatically refreshing tail of console output
retained since the server process started. Its capacity and browser refresh
cadence are configured under `debug` in `SETTINGS.yaml`. Consecutive identical
lines are collapsed into a `Last message repeated N times` entry when the next
different message arrives.

The title, artist, and album share a randomly selected color on each new track.
The palette is configured by `display.track_text_colors` in `SETTINGS.yaml`.

```sh
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/mpd-observer
```

Open `http://localhost:8080` in a browser. On the Raspberry Pi, launch that URL
with the browser's kiosk/full-screen flag. The app observes MPD through a strict
read-only command allowlist and a low-frequency snapshot poll. The browser
refreshes a local normalized snapshot; it never talks to MPD directly.

To deploy code to the saved Raspberry Pi installation without overwriting its
site settings or runtime cache, run `./deploy-pi.sh`. It rebuilds the remote
virtual environment, validates `SETTINGS.yaml`, runs all tests on the Pi, and
does not start the application. Target details may be overridden with the
`MPD_OBSERVER_DEPLOY_HOST`, `MPD_OBSERVER_DEPLOY_USERNAME`,
`MPD_OBSERVER_DEPLOY_IDENTITY`, and `MPD_OBSERVER_DEPLOY_DIR` environment
variables.

Run the isolated tests with:

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## Working with Codex

Good requests describe an outcome and constraints, for example:

> Add a local MPD probe. It must issue only read-only commands, tolerate missing
> tags, and include tests that do not require a live MPD server.

Codex can inspect and edit the repository, run checks, explain tradeoffs, and
show diffs. Keep discoveries in `docs/requirements.md` so decisions survive
across sessions and remote experimentation.
