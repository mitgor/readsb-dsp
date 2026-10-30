# Small-batch publication and immediate stock — 30 October 2026

Experimental only. Production remains unchanged while the 12-hour stock-only
FR24 baseline runs until 20:00 Europe/Berlin. No consumer is routed to this code.

`prototype.py` provides:
- An opt-in pool mixin tapping completed 50/100 ms DSP batches while retaining
  the original whole-second statistics/training assembly unchanged. Works through
  inheritance with the existing file/shared-ring pool. No extra DSP inference.
- A bounded pending queue, 250 ms fail-closed wait ceiling, stock-progress
  watermark and rolling one-RF-second energy anchors. It calls the unchanged
  production admission function (20 matches, median <=2 microseconds; original
  CRC, prior-stock ICAO, conflict and 120 microsecond duplicate rules).
- Immediate original stock bytes, original RF timestamps, shared five-second
  event cache, current switches on every DSP source, epoch/age gates and explicit
  late-stock race counters. Same payload at a different RF time is retained.

The 250 ms ceiling is an experiment parameter, not a proven FR24 guarantee.
Rolling alignment and watermark gating may reject additional candidates; this
must be measured against a complete fresh RF replay before activation. An extra
already emitted cannot be recalled when stock arrives later. No silent stock
loss or timestamp rewriting is allowed. The stock watermark cannot guarantee
that every earlier stock packet has arrived over a reordered upstream stream.

`test_prototype.py` checks transport, guard and early-publication behavior.
`probe.py` records only existing localhost outputs for 45 seconds, under a finite
isolated process budget. It never opens an SDR, mirror socket, output listener,
production outbox or feeder input. Protected PIDs/hashes/methods/gain/cap and loss
counters must match throughout. Binary packets are private evidence only.
`analyze_probe.py` checks byte/hash integrity and measures current relay latency
and the actual feeder send-log cadence. This is not early DSP inference timing.

Next acceptance gates: real completed DSP batch versus whole-second event parity;
original reference/alignment guards under gaps/restarts; end-to-end RF-age tails,
unique additions/losses and CPU on fresh RF; same-binary isolated FR24 replay;
then review the stock baseline before a bounded reversible live/cloud condition.
