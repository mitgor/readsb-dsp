# Native eight-phase Stream1090 algorithm port

The optional `--dsp-rescue-stream-phase` path is a native C part of readsb's
existing DSP rescue module. It invokes no Stream1090 executable, socket or
subprocess. The working receiver configuration is unchanged by this source
change. It requires `--dsp-rescue`, and forwarding still requires the separate
`--dsp-rescue-output` switch.

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

This is an **algorithm subset**, not an exact port of Stream1090's complete
decoder. DF11/18/19, bit/erasure repair, preamble confidence scoring and its
own trust cache are intentionally absent. Those require separate parity and
false-positive validation before addition. The `raw[4]` counter can include
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

SPDX-License-Identifier: GPL-3.0-or-later.
