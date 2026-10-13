# ASL3 Arduino UNO Q display

This directory contains the Arduino App and Linux components installed by the
`asl3-appliance-uno-q` package.

The Arduino App owns the microcontroller side of the design.  Its minimal STM32
sketch initializes the matrix, displays an `ASL` mark with a small superscript
`3` as a startup fallback, and exposes a `draw` RPC through Arduino Router.  The
otherwise-idle Python component keeps the Arduino App alive so the supported
Arduino App CLI can provision and supervise that sketch.

The Linux service does the stateful work.  It runs as `asterisk`, reads existing
AMI credentials from `/etc/asterisk/manager.conf` (including its configured
includes), monitors app_rpt events, builds complete 8x13 frames, and sends them
to the sketch. While idle, it holds `ASL³` for three seconds and then scrolls
` Node:<number> `, followed by `Link:<number>[,<number>...] ` when linked.
Scrolling advances one column every 150 ms. `ASL³` stays at brightness 4; the
scrolling text uses brightness 2 with no links and brightness 4 when linked.
Spaces and colons occupy two columns; other characters occupy four. The leading
space and `Node` are visible as soon as scrolling starts; the scroll restarts
after the final digit and trailing space are visible. RX and TX status interrupt
the scroll; the idle sequence restarts when activity ends. When AMI is unavailable, the
display alternates `ASL³` and a broken-line symbol while retrying; the service
does not need Asterisk to be running first.

The Linux renderer uses a small project-local font so it can interrupt
the scroll for RX/TX and preserve the selected brightness levels. Its glyphs
should be compared on the matrix with the separate ArduinoGraphics font test.

## Updating an installed display

Run `make deploy` from this directory on the UNO Q for both first installation
and subsequent updates. It installs and restarts the App Lab project and Linux
display service. Use `make status` or `make logs` to inspect the services.

The managed App Lab project is `/home/arduino/ArduinoApps/asl3-node-display`.
The systemd services target only `user:asl3-node-display`; they do not remove
other App Lab projects with the same display name.
