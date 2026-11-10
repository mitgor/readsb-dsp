# Native Stream1090 repair/trust extension (offline research)

This in-process C++20 library adds the full pinned Stream1090 demodulation core
behind a C ABI, complementing the smaller `../../dsp_stream_phase.c` clean-CRC
port. It runs on caller-owned finite UC8 buffers. It does not launch a process,
open the SDR, change signals, create a feeder connection, or alter readsb.

The extension reuses upstream's unmodified error tables, weak-bit confidence
and erasure solver, DF19 repair, ICAO+capability trust, two separated sightings,
TTL, and phase/address suppression. All supported upstream formats are
processed internally because DF11 and other frames influence trust; only DF17
is exported to match the current rescue branch. Repairs cannot establish new
trust. The existing downstream causal stock guards remain necessary.

The input frontend, block sizes, startup state, final zero-padding and sample
clock convention match the executable's `-s 2.4 -u 8` stdin invocation. Trust
resets for each call, matching the currently deployed per-window executable.
Persisting trust across windows would be a separate behavior change.

Build explicitly with `make` in this directory (optionally
`ARCHFLAGS=-mcpu=cortex-a76` on the measured Pi 5). Nothing in the normal readsb
build links or enables it. Optimized objects are linked without fast-math to
avoid changing the caller's floating-point mode at library load. See `native.h` for errors, timestamp convention and
output overflow handling; discard all output after an error. The outer caller
must enforce its own finite workload, admission rules and deadlines. This is
not yet a whole-readsb live streaming integration.

## Provenance

`upstream/` contains unmodified dependency headers from Martin Gronemann's
[Stream1090](https://github.com/mgrone/stream1090), commit
`2189bdaca1d62d5e88600b21a281ccc5c18012f2`, copied from the clean checkout
used by the deployed executable. `PROVENANCE.json` records their SHA-256 hashes.
Upstream authorship notices and GPL-3.0-or-later license are retained. This is
reuse of that implementation, not a claim of a new repair algorithm or a C
rewrite of the upstream core.

See the [paired saved-RF benchmark](../../../validation/stream-repair-20261110/report.md)
for distance, CPU and integration limitations.
