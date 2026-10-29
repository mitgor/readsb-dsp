# Native eight-phase Stream1090 algorithm port

The optional `--dsp-rescue-stream-phase` path is a native C part of readsb's
existing DSP rescue module. It invokes no Stream1090 executable, socket or
subprocess. The working receiver configuration is unchanged by this source
change. It requires `--dsp-rescue`, and forwarding still requires the separate
`--dsp-rescue-output` switch. `--dsp-rescue-stream-phase-repair` is a further
explicit opt-in to **shadow-only** CRC-table and confidence-based repairs.
Neither switch is enabled by default.

## Provenance and exact scope

The algorithm is adapted from Martin Gronemann's GPL-3.0-or-later
[Stream1090](https://github.com/mgrone/stream1090), pinned at
`2189bdaca1d62d5e88600b21a281ccc5c18012f2`. The relevant upstream
sources are `include/InputReaderBase.hpp`, `include/RawInputFormat.hpp`,
`include/Sampler.hpp`, `include/SampleStream.hpp`, `include/ShiftRegisters.hpp`
and `include/CRC.hpp`. The native implementation lives in
`readsb/dsp_stream_phase.c`; its only interface is `dsp_stream_phase.h`.

The port keeps the useful acquisition idea: convert centered UC8 I/Q to
linear magnitude, interpolate 2.4 to 8 MS/s using the upstream 3:10 weights,
form eight phase-shifted Manchester streams by comparing samples four 8-MHz
ticks apart, and maintain a 128-bit shift window with a rolling 112-bit CRC.
An exact zero-CRC DF17 frame becomes a candidate. Global RF sample alignment
and the existing readsb history handle buffer boundaries. The output callback
enters the ordinary native rescue pending queue. Existing stock-first duplicate,
conflict and prior-ICAO checks decide whether it counts as an extra. There is
no separate aircraft cache, capture process or network output path.

The optional repair extension uses the pinned Stream1090 build's expanded
933-pattern CRC table: one-bit, adjacent and three-bit bursts, plus selected
two-bit separations. If that fails, it solves
the rolling CRC syndrome over the 24 least-confident non-DF bits, accepting at
most five flips. A fast bitmap admits only ICAO addresses previously seen by
uncorrected stock readsb; the existing 30-second stock-identity, duplicate and
conflict guard makes the final decision. The bitmap is rebuilt from recent
clean stock every five seconds and cleared on RF gaps, so long uptimes cannot
accumulate stale known addresses.
Research-only repaired candidates use a separate deduplication ring, so they
cannot suppress any working DSP output. **No native phase repair is forwarded,
even with `--dsp-rescue-output` enabled.** Clean phase candidates keep their
previous behavior.

This remains an **algorithm subset**, not an exact port of Stream1090's complete
decoder. DF11/18/19, its own trust cache and some timing/acceptance behavior
are absent. Repair is deliberately research-only pending independent
false-positive validation. The `raw[4]` counter can include
several phase views of one transmission; `extras[4]` is deduplicated with the
other methods. A candidate in the last buffer is not released without a later
stock pass, as with the other native DSP methods.

## Local validation

`make -C readsb readsb dsp-rescue-test dsp-rescue-test-sanitize` builds and
exercises a synthetic frame crossing an input-buffer boundary. The replay
test in `readsb/tests/dsp-rescue/replay.py` compares the optional shadow mode
against the unchanged stock output on generated and supplied UC8 files.

On five previously saved UC8 seconds, enabling the phase path in shadow mode
preserved byte-identical readsb stdout. It found 425 raw phase candidates;
all were already covered by stock or the earlier DSP methods, so it added zero
guarded extras on that short sample. Native rescue work increased from 261 to
352 ms over the capture. These are Mac replay figures, not Pi CPU benchmarks or
evidence of a field reception gain. Longer independent recordings are needed
before enabling the option on a receiver.

For a direct upstream comparison on the same saved sample, the two paths shared
172 unique DF17 payloads. The native clean-CRC search found 17 not emitted by
the full Stream1090 program, while Stream1090 emitted 30 not found by the native
search. Upstream has repair and independent trust rules; these output sets are
not expected to match. A native-only packet is a candidate, not proof that the
upstream decoder was wrong, and the missing upstream packets must not be
claimed as recovered by this subset.

## Twenty-minute comparison and Pi cost

On 1,195 complete RF seconds from a 20-minute live capture, the clean native
version missed 20,604 Stream1090 DF17 events. Instrumented upstream provenance
showed 10,846 fixed-table repairs, 7,271 confidence erasures, 2,414 clean
decodes and 73 DF19 guesses among those misses. With repairs enabled, the
native decoder recovered 18,233 of the 20,604 events (88.5%), while preserving
all 161,014 distinct clean-native events. Among 7,919 old-only events absent
from stock in paired coverage, it recovered 6,273 (79.2%). The remaining 2,371
old-only misses include
clean decoding/timing and upstream trust differences. Native Mac replay used
29.00 CPU seconds versus 64.96 for Stream1090 on the same RF. These are
candidate counts, not independently verified aircraft messages.

The repaired native path also produced 2,667 erasure and 1,477 fixed-table
candidates absent from the current unified feed. Some may be real, but exact
CRC and prior ICAO context do not independently establish truth. This is why
repair output remains quarantined. The offline bitmap can include stock
packets that readsb corrected, because Beast omits that flag, so these replay
counts are a permissive upper bound on production acceptance.

A separate 59-RF-second benchmark on the Pi 5, with the sample held entirely
in RAM and a deliberately broad known-address bitmap, used 6.69 CPU seconds
for clean phase search and 9.46 with repairs (0.113 and 0.160 core respectively).
Readsb and FR24 stayed active with fresh stock traffic. Full readsb ifile
integration preserved every stock record in shadow mode. With explicit DSP
output, adding phase repair preserved all 505 previously forwarded DSP extras;
it added 63 clean phase records while 435 repaired phase records stayed in
shadow. The saved summary and scripts are under
`validation/stream-phase-live-20261029/` and `readsb/tests/dsp-rescue/`.

The next validation gate is a longer Pi live shadow run with exact production
guard counts and independent packet/track corroboration. The active receiver
and FR24 routing have not been changed for this work.

SPDX-License-Identifier: GPL-3.0-or-later.
