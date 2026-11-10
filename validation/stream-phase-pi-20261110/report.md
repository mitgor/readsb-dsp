# Native Stream1090 comparison on Pi — 10 November 2026

Keep the current executable enabled. The native clean-CRC subset used **31.1% less method CPU**, but recovered fewer useful packets in the primary replay. No working receiver configuration, model, feeder route, capture limit or service was changed.

## Primary comparison: 119 one-second RF windows

Uniformly selected historical windows; one of 120 selected windows lacked complete paired references and was excluded for both implementations. These are guarded, deduplicated DF17 additions beyond stock, not all raw decoder outputs. Distance in this historical recording is an estimate from stock positions without NIC/NACp qualification.

| Distance (nm) | Native port | Current executable |
|---|---:|---:|
| 0-50 | 67 | 238 |
| 50-100 | 86 | 380 |
| 100-150 | 56 | 287 |
| 150-180 | 2 | 22 |
| 180-200 | 0 | 3 |
| 200-250 | 0 | 0 |
| 250+ | 0 | 0 |
| unknown | 3 | 38 |
| **Total** | **214** | **968** |

There were 152 shared additions, 62 native-only and 816 executable-only. These are Stream method differences before overlap with the other DSP methods; they are not demonstrated full-pipeline losses. Against the historical recorded unified output, native added 35 candidates and the executable 61 (11 shared); this historical unified feed is not the current full-pipeline baseline.

| CPU measurement | Native port | Current executable |
|---|---:|---:|
| CPU seconds per RF second, decode + common guards | 0.0956 | 0.1387 |
| Equivalent one-core usage at real time | 9.56% | 13.87% |
| CPU milliseconds per guarded stock extra | 53.2 | 17.1 |

CPU includes executable child time, startup, pipes and parsing, or native buffered-call conversion, plus the same guards. It excludes RF file reading and the rest of the live pipeline. The saving is about 4.31% of one core, or 1.08% of four-core capacity, not a 31% reduction of total receiver CPU. The current executable is more efficient per useful extra on this sample.

Native emitted 16,004 raw unique DF17 transmissions versus 14,953 for the executable; many were already stock. Raw totals alone would give the wrong conclusion about useful recovery.

## Recent full-pipeline supplement

383 aligned short clips, 24.24718 RF seconds after edge trimming. Stock-derived distances require causal positions, NIC/NACp >=5, age <=15 seconds and no MLAT/TIS-B. Native/executable stock extras were 19/11. After frozen current other-DSP replay they were 9/2. Replacing the executable in that replay gained eight and lost one; retaining the executable and adding native produced **two additional guarded candidates**, one at 50–100 nm and one at 100–150 nm, after masking actual unified output and annotations. **Zero additions beyond 180 nm.** All experimental outputs remain quarantined, not labels or feeder input.

Recent short-clip CPU was 0.1006/0.1919 CPU-s per RF-s, native/executable. Short clips amplify executable startup and cold trust-cache effects; the one-second primary comparison is more representative of current windowing. Distant opportunity coverage is insufficient to claim a range improvement.

## Scope, timing and checks

The native path is the unchanged C eight-phase clean-CRC DF17 search in `readsb/dsp_stream_phase.c`, not the full upstream decoder. It omits repair, DF11/18/19, preamble-confidence scoring and upstream trust cache. Both searches received identical I/Q and common causal stock-identity, conflict and transmission-dedup guards. Full readsb admission rules and live method deadlines were not exercised; the isolated native kernel used an unlimited internal deadline within finite saved input. This is a kernel/search benchmark, not an end-to-end integration approval.

Each implementation's sample offset was calibrated independently from same-window stock anchors (native 2,400 ticks; executable 769 ticks). Mac/Pi per-implementation packet/timestamp digests, distance bins and calibrations matched exactly. Stock matching tolerance was 120 microseconds, conflict tolerance four microseconds, causal stock identity retention 30 seconds. Complete synthetic packet controls emitted only the known payload (native three, executable two detections); pure noise produced zero candidates or admissions. Native integration unit tests passed on Mac and Pi without opening the SDR.

## Target safety and reproducibility

One full Pi pass completed. During repeat two, two consecutive FR24 status checks failed around 13:04 Berlin; the supervisor stopped only this owned benchmark. Partial repeat two is excluded, and no three-run median or variability claim is made. A timeout/disconnect was present in the private feeder journal; causality is unproved. FR24 was subsequently connected without intervention. Protected service PIDs, configurations, methods, models, gain, SDR loss counters and capture cap matched before/after.

Execution used nice 19, core 3, CPUQuota 35%, finite 900-second runtime and requested MemoryMax 1 GiB/zero swap. The target memory controller did not expose enforcement; observed supervisor RSS was about 89 MiB. All work used owned tmpfs, copied binaries/libraries and saved RF, without a live mirror or SDR consumer. Inputs and results were checksum-verified and fsynced on Mac before deleting 74 owned temporary files. No persistent receiver archives were deleted.

Reproducible scripts are in `experiments/stream-phase-pi-20261110/`. Private inputs, packet-level outputs, journals, source snapshots and transfer receipts remain in the private data workspace. The results binary backup SHA-256 is `3df2dfc61e7fb7fdd264620b81617b7d4e2342545aa6fa164ffc60d4a68dd3b0`. Summary JSON contains aggregate counts and implementation hashes only. No raw RF, aircraft addresses, credentials or private receiver diagnostics are published.
