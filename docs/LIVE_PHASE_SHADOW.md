# Native phase live shadow validation

This research observer reads the **existing nonblocking IQ copy** on the Pi.
It does not open an SDR or send a Beast/AVR feed. The working readsb and FR24
services continue to own reception and output. The observer has a bounded
20-minute direct-pairing runtime (the previous validation used 30 minutes),
low scheduling priority, an 80% one-core CPU ceiling, 256 MB memory
ceiling, and writes a bounded event log to `/run` (RAM). It is not enabled at
boot.

The observer can run the pinned old Stream1090 executable and native C on each
identical one-second IQ core. It aligns their sample clocks using at least ten
shared clean payloads, requires a stable median offset, and pairs exact DF17
payloads within 120 µs. It reports old-only clean events, how many native
repairs recover, and residual old-only events. This compares decoder output
before the production stock-identity and conflict guard; a matched packet is
not independently verified. The same old executable and flags are used by
the working Stream1090 integration, which also starts a bounded process per
RF second. Direct-pairing aggregates are in the RAM-only
`/run/adsb-rescue/native-phase-direct-status.direct.jsonl` file.
The [20-minute direct comparison](../validation/stream-phase-live-20261029/native-direct-live/REPORT.md)
reports its final counts and limitations.

Separately, the observer compares CRC-valid DF17 candidates with read-only stock
and actual unified Beast streams. Stock-absent counts are distinct from
unified-absent counts. A candidate absent from the unified stream is only a
*shadow candidate*: the full production guard knows corrected-bit status, but
Beast does not export that flag. The shadow ICAO prefilter is therefore a
permissive approximation. The event log records candidate kind (`0` clean,
`1` CRC table, `2` confidence erasure), range bin when a fresh local stock
position exists, sample tick and wall time.

The research module is `readsb/tests/dsp-rescue/live_phase_shadow.py`; its
systemd unit is `deploy/adsb-native-phase-shadow.service`. The additional IQ
mirror drop-in is `deploy/95-native-phase-mirror.conf`. It changes only the
rescue shadow's mirror list. The native C shared library is built from
`readsb/dsp_stream_phase.c` with `-D_POSIX_C_SOURCE=200809L -O3 -fPIC -shared`.
The Pi must have the `rescue.stream1090_shadow` and `rescue.wire` modules
installed, because the observer reuses their Beast parsing and IQ framing.

The drop-in requires one restart of `adsb-rescue-shadow`; `readsb`, `fr24feed`
and `adsb-rescue-feed` are not restarted. After starting, check all of those
services, `/run/adsb-rescue/feed-status.json` stock age and upstream error,
the production `/run/adsb-rescue/status.json` input drop counters, and the
observer's configured `--status` path for decoder errors and incomplete
comparison windows. The event log uses the same stem with `.events.jsonl`;
the direct-pairing log uses `.direct.jsonl`. The current service uses
`/run/adsb-rescue/native-phase-direct-status.json`.

For rollback, stop `adsb-native-phase-shadow`, remove only
`/etc/systemd/system/adsb-rescue-shadow.service.d/95-native-phase-mirror.conf`,
run `systemctl daemon-reload`, and restart only `adsb-rescue-shadow`. Confirm
the original `--mac-helper-socket` remains in the effective ExecStart and
FR24 stock freshness returns. Do not remove the Mac helper drop-in or change
the receiver SDR service.

The Mac's paired stock/unified Beast capture supports a second check with
`readsb/tests/dsp-rescue/analyze_live_phase_shadow.py`. Optional adsb.fi
aircraft positions are collected by `collect_track_context.py` with source
attribution; they provide **track context**, not independently received raw
ADS-B packets. A later exact stock payload recurrence also supports
plausibility but is not an independent receiver. Neither kind of context
establishes a false-positive rate for repaired frames.

As a negative control, 300 seconds of uniform random UC8 I/Q with 3,236
historically seen ICAOs admitted 4 clean, 1 CRC-table and 14 erasure
CRC-valid candidates. Uniform noise does not represent the receiver's RF
distribution, but it demonstrates that CRC plus known ICAO cannot prove a
repaired message. **Keep all phase repairs quarantined; do not route to FR24.**

SPDX-License-Identifier: GPL-3.0-or-later.
