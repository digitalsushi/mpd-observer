# Architecture

## Guiding rule

MPD is an observed external system, not part of this application. The observer
must remain useful across compatible MPD upgrades and unrelated upstream code
changes.

## Proposed flow

```text
MPD protocol -> read-only adapter -> NowPlaying snapshot -> kiosk presentation
                       |                    |
                 reconnect/backoff     artwork cache
```

For artwork and richer stream metadata, an optional rAudio HTTP adapter may
enrich a matching MPD snapshot. This appliance-specific fallback is isolated
behind the normalized model, uses one fixed status request, and accepts artwork
only from the configured rAudio HTTP origin. Standard MPD remains the primary
source.

If neither local source supplies artwork, an optional MusicBrainz provider uses
an exact artist/title match to identify a release group and retrieves its front
image from the Cover Art Archive. Both successful images and misses are cached
on disk with configurable lifetimes. Network failure never makes MPD appear
offline.

For durationless streams, a confident MusicBrainz match may also supply the
recording length. The observer treats the arrival of new artist/title metadata
as the approximate start time and labels the resulting progress as estimated.

The adapter may use the stable MPD protocol, including `status`, `currentsong`,
`albumart`, and `readpicture`. It must not expose a general-purpose
MPD client to the presentation layer.

## Safety boundary

The application will maintain an explicit allowlist of read-only commands. It
will not implement or forward playback, mixer, queue, playlist, database-update,
or output-management commands. Where supported, deployment should also use MPD
credentials restricted to read-only access, making the boundary independently
enforceable.

The development environment may connect to a live MPD server, but only through
this same allowlisted observer boundary. Ad hoc commands that bypass the
boundary are not part of the development workflow.

## Internal model

The normalized now-playing snapshot will eventually cover:

- connection and playback state
- track identity and display metadata
- elapsed time and duration
- an artwork reference plus provenance
- observation timestamp

Missing metadata is normal. Rendering must use graceful fallbacks rather than
leaking MPD-specific null handling throughout the UI.

## Coupling strategy

- Depend on the documented MPD wire protocol, not upstream implementation
  details or repository access.
- Translate raw fields at one boundary.
- Test the adapter with recorded/fake protocol conversations.
- Keep external metadata and artwork providers optional and replaceable.
- Treat the display geometry as configuration until the exact pixel dimensions
  and orientation are known.
