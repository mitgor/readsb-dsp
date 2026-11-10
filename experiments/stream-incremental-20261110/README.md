# Incremental native Stream1090 — isolated Pi experiment

Current batch native library is unchanged. The experimental API is
`readsb/contrib/stream1090-native/incremental.h`; create/feed/finish/destroy keep
the current logical window and preserve its trust/reset semantics. Feed chunks
are 20 or 50 ms, not overlapping one-second replays. No chunk-edge zero padding
is allowed. The existing batch EOF block is reproduced exactly at finish.
The caller must reset on RF epoch changes, enforce sample-clock continuity and
quarantine an entire failed logical window. Returned raw packets are not
feeder-ready or supervised labels.

Build only the optional incremental target (`make incremental` in the native
library directory), or compile `incremental.cpp` to an object with the pinned
O3/C++20/fast-math options and link WITHOUT fast-math. Pinned upstream headers
are unchanged. `incremental_stream.hpp` adapts only the SampleStream lifetime
and per-block interface; retained frontend/confidence helpers are audited.

`bindings.py` exposes test-only C ABI bindings. `benchmark.py` accepts explicit
`--root --batch --incremental --output` paths, rotates throughput order per case,
requires exact raw payload/time/order parity and parent physical-core digests,
and separately paces each method at the original RF rate. The root contains
`prepared/rf.bin`, `cases.json` and `reference-result.json`. Original masks,
source/data checksums and complete sample-clock reservations remain in the
private workspace. The same 119 historical long seconds and 383 recent clips
are evaluation-only, not new prospective RF or training labels.

Paced latency measures availability of raw decoder output AFTER the packet's RF
end. It includes chunk waiting and decoding, but excludes live tap transport,
stock-clock corroboration, conflict/dedup admission, other DSP and feeders.
Physical RF origin is pinned by the prior corrected sample-clock audit, not
inferred from a candidate-specific offset. Current coordinator admission still
waits for a whole window. The benchmark never feeds candidate packets.

`controls.py` checks known clean/repaired RF, untrusted repairs, noise, fixed and
irregular splits, gaps/overlap, missing/final/closed sessions, overflow and
cooperative deadlines. `sanitize.cpp` covers C API lifecycle/edge behavior with
ASan/UBSan and verifies that library loading preserves the floating-point mode.
`pi_supervisor.py` uses the existing protected-health prefix from the previous
native benchmark, checking receiver/feeder PIDs, configuration, counters,
coordinator and recorder freshness, queue/latency bounds and temperature.

Pi testing uses copied native libraries and saved RF only in owned tmpfs,
nice19/core3/35% CPU quota, requested MemoryMax1G/zero swap and a finite runtime.
Memory-controller enforcement is unavailable on this target. No SDR or mirror
consumer, service restart, live configuration change, archive deletion or forced
flush is allowed. Clean only owned files after verified durable Mac backups.

See [results](../../validation/stream-incremental-20261110/report.md).
