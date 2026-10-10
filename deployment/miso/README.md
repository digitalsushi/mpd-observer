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
