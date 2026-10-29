# Native phase repair: paired RF validation

**Decision:** Keep the current Stream1090 integration and FR24 feed unchanged.
The native readsb port now recovers most of Stream1090's extra DF17 events on
the same saved live RF, but repaired packets remain research-only pending an
independent false-positive check. Source switches are off by default; no new
binary or service configuration was installed on the Pi.

## What accounted for the gap

The prior [20-minute live capture](REPORT.md) supplied 1,195 complete RF
seconds. A diagnostic-only build of upstream Stream1090 at pinned commit
`2189bdaca1d62d5e88600b21a281ccc5c18012f2` traced how its 20,604
old-only CRC-valid DF17 outputs were admitted:

| Provenance | Old-only events |
|---|---:|
| Fixed CRC syndrome table | 10,846 |
| Confidence-based erasure repair | 7,271 |
| Clean decode | 2,414 |
| DF19-to-DF17 promotion | 73 |

Thus repairs, rather than DF types outside DF17, explained most of the
measured gap. The exact diagnostic patch is reproducible with
`readsb/tests/dsp-rescue/trace_stream1090_provenance.py`; its normal stdout
remained unchanged and its per-packet marker went only to stderr. The saved
classification is `gap-classification.summary.json`.

## Native extension

The native eight-phase search now has an additional explicit
`--dsp-rescue-stream-phase-repair` switch. It matches the pinned build's
expanded 933-pattern table (one-bit, adjacent and three-bit bursts, plus
selected two-bit separations), then tries a 24-weak-bit rolling-CRC erasure
solver with a five-flip cap.
Repairs require a prior clean-stock ICAO address bitmap and pass readsb's
existing recent-stock, duplicate and conflict checks. The bitmap is rebuilt
every five seconds and resets on RF gaps. Research-only repaired packets use
a separate deduplication ring and
**cannot suppress or reach the working output**, even if general DSP output
is enabled. Clean phase behavior is unchanged. The switches and receiver
configuration on the Pi remain unchanged.

On the same 1,195 RF seconds, the new native path matched **18,233 of the
20,604** previously old-only events (88.5%). It missed 2,371. Of 7,919
old-only events absent from stock in paired coverage, **6,273** were matched
(79.2%). All 161,014 clean-native events were preserved. Mac replay consumed
**29.00 CPU seconds** versus Stream1090's **64.96 CPU seconds**, a 55.4% reduction for these
different implementations; the old number includes per-second process starts.
The replay bitmap was filled only from stock Beast addresses preceding each
window and reset at RF discontinuities. Beast does not expose readsb's
corrected-bit flag, so its repaired-candidate counts are permissive upper
bounds on production admission. Summary: `native-repair-exact.summary.json`.

The native path also found repaired candidates not in the old decoder. Of
those, 1,477 fixed-table and 2,667 erasure candidates were absent from the
current unified feed. CRC validity and prior ICAO context are insufficient
to establish that these are real transmissions. None is routed to FR24.

## CPU and output preservation

A standalone 59-RF-second replay on the Pi 5 used RAM-backed UC8 and bitmap
files, `nice +10`, and no receiver or feeder sockets. With all 3,236
distinct stock addresses in the bitmap as a conservative CPU load, clean
phase used **6.69 CPU seconds (0.113 core)** and phase with repairs used
**9.46 CPU seconds (0.160 core)**. The RAM files were removed afterward.
These are Pi decoder costs, not a 24-hour live CPU or reception estimate.
The command and results are in `pi5-benchmark.json` and
`readsb/tests/dsp-rescue/bench_stream_phase.c`.

Full readsb ifile integration on 60 saved RF seconds gave exactly the same
stock output with either phase shadow mode. In explicit DSP-output mode,
enabling phase repair preserved all **505** previously forwarded DSP extras,
added **63 clean phase** records, and kept **435 repaired phase** records in
shadow. No stock record was lost; see `readsb-ifile-final-60s.json`.
Unit and ASan/UBSan checks passed for the rolling syndrome basis, three-bit
erasure solver, prior-stock guard, shadow isolation, and output preservation.
The full recorded-RF replay suite also preserved every stock record in
disabled, shadow, phase-clean-shadow, phase-repair-shadow, explicit-output and
tight-budget modes against the same readsb binary with DSP disabled; it
passed generated boundary, noise, shuffled-I/Q and nine
invalid-configuration controls (`full-replay-60s.json`).
After the Pi CPU benchmark, readsb, FR24, rescue feed and rescue shadow were
active; FR24's relay reported fresh stock (~0.02 s age), no upstream error.

## Remaining gate

The residual 2,371 events need timing/clean-decoder and trust-policy analysis.
Of the 1,646 misses absent from stock in paired coverage, 823 were upstream
erasure repairs, 756 table repairs, 40 clean decodes and 27 DF19 promotions.
1,620 of these 1,646 had a prior stock ICAO in the replay context, so the
remaining gap is primarily decoder behavior rather than the fast trust bitmap.
More importantly, a longer **live Pi shadow** run and independent packet
corroboration are required before any repaired output can be considered for a
canary. This run used a saved live capture and a bounded Pi RAM replay; it did
not deploy the new decoder into the active Pi pipeline.

Raw RF, paired Beast data and per-window candidate logs remain only on the
local Mac. This report and aggregate JSON contain no feeder credential or
private RF.
