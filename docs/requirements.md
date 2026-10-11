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

### Recurring rAudio Ethernet contact fault (2026-10-10)

- The separate rAudio music source at 10.0.0.6 has a recurring physical Ethernet
  contact fault that the user encounters roughly quarterly.
- On 2026-10-10, pressing the 8P8C connector upward restored the link after
  intermittent connectivity. The cable plug versus the device jack has not
  been isolated as the defective component.
- For future music-source outages, check this known connector/contact issue
  first before investigating Observer software. Symptoms can include failed
  ping, SSH and MPD timeouts, and occasional successful HTTP connections.
- This is distinct from Miso's display rotation issue and Maliwan's offline
  barn Zigbee bridge. Leave the music source unchanged unless the user requests
  work on it.

### Maliwan power recovery (2026-10-11)

- Maliwan is the barn Zigbee coordinator serving thermometers T01, T03, and
  T06. Its last known IP was 10.0.0.192.
- The user confirmed that Maliwan requires a physical power-button press
  after any power event; it does not power back on automatically.
- When these thermometers become unavailable after a power event, first
  arrange a physical power-button press on Maliwan before investigating DHCP,
  network connectivity, or Home Assistant's API.
