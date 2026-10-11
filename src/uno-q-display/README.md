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
to the sketch.  When AMI is unavailable it alternates the ASL3 and question-mark
pages while retrying; the service does not need Asterisk to be running first.
