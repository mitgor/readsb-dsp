# Native Stream1090 repair and trust — Pi validation, 10 November 2026

The extended native library retained every measured executable DF17 recovery and timestamp, using **24.5% less method CPU** on the primary saved-RF replay. The live pipeline remains unchanged. This is a separate in-process C++20 library with a C ABI, reusing the pinned upstream core; the existing clean-CRC C subset is unchanged.

## Recovery by distance

119 uniformly selected one-second historical RF windows with complete paired references, identical input to both implementations. Counts are guarded, deduplicated extras beyond stock. **Historical distances are estimates** without NIC/NACp qualification.

| Distance (nm) | Extended native | Current executable | Lost |
|---|---:|---:|---:|
| 0-50 | 238 | 238 | 0 |
| 50-100 | 380 | 380 | 0 |
| 100-150 | 287 | 287 | 0 |
| 150-180 | 22 | 22 | 0 |
| 180-200 | 3 | 3 | 0 |
| 200-250 | 0 | 0 | 0 |
| 250+ | 0 | 0 | 0 |
| unknown | 38 | 38 | 0 |
| **Total** | **968** | **968** | **0** |

All 968 extras were shared. The earlier clean-only C subset recovered 214 on this same RF; the extension now retains the executable's repair/trust recovery. Native and executable also matched all raw unique DF17 transmissions and all sample timestamps exactly on Pi. Against historical recorded unified output both added 61 candidates; this historical reference is not the full current pipeline.

## Pi CPU

One complete paired pass, alternating execution order per RF case. CPU includes native allocations, buffer conversion and common guards, or executable startup, child CPU, pipes, AVR parsing and the same guards. Raw RF file reads are excluded.

| Measurement | Extended native | Executable |
|---|---:|---:|
| CPU seconds per RF second | 0.1083 | 0.1433 |
| Equivalent one-core usage at real time | 10.83% | 14.33% |
| CPU milliseconds per guarded stock extra | 13.3 | 17.6 |

The saving is 3.51% of one core, approximately 0.88% of total four-core capacity. It is not a 24.5% reduction of the complete receiver's CPU. Savings include avoiding process/pipe/formatting overhead and computing no unused export RSSI, not a claimed new error-correction algorithm. Live scheduling latency was not tested.

## Recent complete-pipeline supplement

383 aligned short clips, 24.24718 RF seconds after edge trimming. Both implementations recovered 11 guarded extras beyond stock and two beyond the frozen current other-DSP replay, one at 50–100 nm and one at 100–150 nm. Neither added a packet beyond the full current union once current Stream1090, actual unified output and annotations were included: **zero gains and zero losses**. No additional recovery beyond 180 nm was established. All candidate output remains quarantined; nothing becomes training labels or feeder input.

Recent short-clip median CPU was 0.1226/0.2006 CPU-s/RF-s, native/executable. Short clips magnify executable startup and cold trust state, so use the one-second primary corpus for deployment expectations. Recent ranges require causal stock NIC/NACp >=5, age <=15 seconds and no MLAT/TIS-B. Three historical estimated 180–200 nm extras were retained, but distant opportunity coverage is too small for a range-improvement claim.

## Implementation and safety checks

The extension uses unmodified dependencies from [Stream1090](https://github.com/mgrone/stream1090) commit `2189bdaca1d62d5e88600b21a281ccc5c18012f2`; upstream GPL notices, license and SHA-256 provenance are included. It preserves:

- the exact 2.4-to-8 MHz frontend and eight-phase rolling framing;
- syndrome-table repairs, confidence-ranked bounded erasure repair, and DF19 repair;
- DF11 and other internal formats that affect trust, ICAO+capability keys, trust TTL, phase suppression and duplicate behavior;
- separate sightings before trust, with repaired candidates unable to seed new trust;
- per-window state reset and final partial-block zero-padding, matching current executable invocation.

Only DF17 is exported, matching current rescue admission. The C ABI returns explicit invalid-input, overflow and exception errors, with no usable output on error. Fast-math is applied only when compiling the native object, never at shared-library link time: a load-time floating-point-environment check passes on Mac and Pi. The earlier direct-link build had a `crtfastmath` initializer and was replaced before these final measurements. It creates no child process, SDR/mirror consumer, feeder connection or signal handler. Nothing in the normal readsb build enables it.

Known synthetic single-bit, adjacent two-bit, three-bit burst and DF19 repairs matched executable packets/timestamps exactly. Trusted cases recovered the known packet; damaged-only untrusted cases emitted zero. Clean and pure-noise controls passed. Direct trust-separation/expiry and non-table syndrome-solver tests passed under AddressSanitizer/UndefinedBehaviorSanitizer on Mac; API sanitizer tests covered successful decoding, invalid input and overflow. These verify implementation behavior, not correctness of every repaired real-world packet.

Stock alignment was independently calibrated for each implementation from the same RF (769 ticks). Physical RF-core trimming separately uses the frozen original-C baseline's measured stock-to-preamble offset of 2,400 ticks. An initial harness version conflated those origins; its matching paired outputs are retained only as a coordinate audit and excluded from final CPU/recovery results. Native/executable packet/timestamp digests match exactly on Pi. The final safe-link build has one complete paired pass; repeat variance is not estimated. Earlier coordinate/link-audit runs are preserved but excluded from the final performance table. Mac native/executable pairing also matches exactly. Mac/Pi digests are checked separately; target pairing is authoritative.

Target: Raspberry Pi 5 Model B Rev 1.0. Isolated owned tmpfs, nice 19, core 3, CPUQuota 35%, finite 900-second unit, requested MemoryMax 1 GiB and zero swap. The kernel did not expose memory-controller enforcement. Protected receiver/feeder PIDs, method switches, models, library/source hashes, gain, configurations and SDR loss counters remained unchanged; the 5,000,000,000-byte RF cap and normal disk-save schedule were preserved. No live route, service, model or logging change was made.

## Limits and next gate

This validates a native finite-window replacement core against the current executable on saved RF. It does not yet validate a live readsb binding, cancellation/deadline behavior, pending-queue integration or prospective distant RF. The smaller original C path and production executable remain unchanged. Preserve stock-first validation and downstream conflict/dedup guards if integrating later. Historical evaluation intervals stay reserved; outputs are not supervised labels.

Reproducible code and private input/output manifests are retained under the dated experiment. Public summary contains aggregates only; raw RF, packet-level records, receiver diagnostics and credentials remain private. The owned Pi work is removed only after checksum-verified durable Mac backup.
