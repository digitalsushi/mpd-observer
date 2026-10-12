# Miso display layout

`kanshi/config` is the verified display-manager configuration for Miso's two
480×1920 panels. It makes both panels landscape and reapplies their rotations
when HDMI outputs reconnect, including after a monitor power interruption.

- HDMI-A-1: left panel, MPD Observer, transform 270, position 0,0.
- HDMI-A-2: right panel, gauge-card, transform 90, position 1920,0.

Install as `/home/mikec/.config/kanshi/config` on Miso, preserving a backup of
any existing configuration. Reload the running display manager with
`pkill -HUP -x kanshi` from Miso's user session. The existing
`miso-displays.service` startup script uses the same geometry.

Verified on 2026-10-10: both transforms and positions reported correctly by
`WAYLAND_DISPLAY=wayland-0 wlr-randr`, both browser services remained active,
and the user confirmed both panels were upright. Reconnection recovery has
not yet been tested with another power interruption.

## Freezing thermometer colors

The blue-ring outdoor needle is T01 (`sensor.thermometer_t_01_temperature`),
under the porch in shade with airflow. The `cards` directory contains the
modified Sora server and gauge files captured from the live installation.
The server uses its existing `/opt/laundry.py` dependency and credentials;
these files are not a standalone replacement for the entire cards installation.

The server tracks an uninterrupted hour of observations rounded to 32°F,
persisting the timer in its existing thermometer cache. Missing observations,
API failures, or gaps over 90 seconds reset the timer. Both cold states use
navy (`#000080`). Below 32°F immediately freezes a white
graduated bezel; the completed rounded-32°F hour rotates it clockwise once per
minute. Returning to the boundary from below also resumes rotation. Above the
rounded boundary for a continuous hour restores the original face and removes
the ice bezel. Missing observations interrupt that warm-hour timer.
The existing heat emergency takes priority. Unhealthy API data uses the normal
face. The browser does not accumulate the timer, so reloads do not restart it.

`freeze-preview.html` shows labeled transition and frozen gauges side by side,
with matching mock needles for a direct monitor color comparison. It leaves
Home Assistant data unchanged. On Miso the temporary right-browser override is
`~/.config/systemd/user/miso-browser@HDMI-A-2.service.d/freeze-preview.conf`.
To return to the live gauge, remove that override, run
`systemctl --user daemon-reload`, then restart
`miso-browser@HDMI-A-2.service`. Only the right browser needs restarting.

Approved and activated on 2026-10-12; the temporary browser override was removed.
The comparison page remains available for future color and animation iterations.
