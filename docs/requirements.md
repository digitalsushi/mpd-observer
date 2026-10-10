# Requirements Notebook

This file records confirmed requirements, open questions, and discoveries made
while the proof of concept develops.

## Confirmed

- Target device: Raspberry Pi.
- Target display: unusually wide and short, approximately 8.8 × 3 inches.
- Data source: a nearby MPD service.
- A live MPD development server may be configured outside the repository.
- The application is an observer and kiosk display, not a scrobbler or remote.
- It must not mutate MPD.
- Live-server development and diagnostics must issue only explicitly allowlisted
  read-only MPD commands.
- Coupling to MPD and its upstream project must remain deliberately low.
- It should display now-playing metadata and album art attractively.

## Open questions

- Exact Raspberry Pi model and operating system.
- Native display resolution, rotation, connection, and browser/GPU constraints.
- MPD protocol version, port, authentication, and network reliability for the
  configured server.
- Whether artwork is available through `albumart`, `readpicture`, both, or
  neither.
- Preferred implementation language and kiosk runtime.
- Visual style, typography, transitions, and behavior while paused or offline.
- Whether any information may be cached on disk and for how long.

## Decisions

Record consequential choices here or as focused decision records when they
become large enough to deserve their own file.

### Miso display recovery (2026-10-10)

- Miso is the Raspberry Pi 4 at 10.0.0.8 running two Chromium displays under
  labwc. `miso.lan` did not resolve during this investigation; SSH by IP worked.
- The browsers load MPD Observer from `http://sora.lan:8081/` and gauge-card
  from `http://sora.lan:8082/`. Sora resolved to 10.0.0.142.
- 10.0.0.6 is the separate rAudio music source; leave it untouched when fixing
  Miso's displays. The local deployment settings targeting `pi.lan` are stale
  for this installation.
- Following a reported monitor power interruption, both HDMI outputs were
  unrotated despite correct rotations in the startup script. Miso's running
  kanshi display manager had an empty configuration.
- Restore the startup geometry and configure kanshi to maintain it across
  output reconnections. The verified configuration is stored in
  `deployment/miso/kanshi/config`; see `deployment/miso/README.md` for details.
