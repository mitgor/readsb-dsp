# Real DSP extras: asynchronous relay validation on Pi

**Transport compatibility passes at the3second diagnostic age limit; the default250ms profile fails with the current producer timing. Neither was deployed.** The stock-only FR24 trial remains active through November1 at20:00Berlin; the working decoder, relay, ADS-B Exchange and capture pipeline are unchanged.

## What was actually tested

Observed already-guarded real production DSP results through read-only inotify notifications on the existing RAM outbox, plus read-only stock30005/current-relay31005 clients. No outbox entry was consumed, renamed, removed, held for synchronization or modified. No SDR/mirror client, model inference, service restart, routing/switch/gain/cap change or collector flush was introduced.

Two independent isolated fan-in instances received the same results at their observed actual arrival times: frozen250ms freshness and explicit3s diagnostic freshness. Both retain immediate stock, original RF timestamps, all source/alignment/CRC/prior-stock/conflict/duplicate guards, and a shared five-second bounded history. **3s is an age ceiling for extras, not an output holdback.** Production still publishes in whole-second groups; this test does not implement the proposed per-completion producer/admission bridge.

35s warmup,180s measured interval and5s tail; full observer wall time221.29s. Nice19/core3/35%quota/1GiB/finite unit. Outputs stayed in owned tmpfs files, never connected to a production feeder.

## Recovery counts and method latency

Counts below use the same observed producer-publication cohort. They are attributed extras beyond stock, **not additional recoveries beyond our existing complete DSP pipeline**, and method attribution is not an ablation. Two producer-admitted records were not present in the current-relay reference either; the diagnostic did not add or lose any currently relayed packet.

| Method | Producer admitted | Current relay matches | Strict250ms | Async3s diagnostic | >=180nm | Estimated RF age median: async/current(s) | Existing DSP CPU, one core |
|---|---:|---:|---:|---:|---:|---:|---:|
| energy | 731 | 730 | 0 | 730 | 9 | 1.26 / 3.07 | 3.94% |
| timing | 532 | 531 | 0 | 531 | 6 | 1.27 / 3.07 | 1.15% |
| soft | 593 | 593 | 0 | 593 | 8 | 1.38 / 3.06 | 0.42% |
| matched | 144 | 144 | 0 | 144 | 2 | 1.34 / 3.07 | 1.15% |
| coherent | 1,494 | 1,494 | 0 | 1,494 | 22 | 1.48 / 3.07 | 12.31% |
| neural | 307 | 307 | 0 | 307 | 5 | 1.51 / 3.05 | 12.30% |
| stream1090 | 793 | 793 | 0 | 793 | 2 | 1.43 / 3.13 | 11.62% |
| **Total** | **4,594** | **4,592** | **0** | **4,592** | **54** | method-specific | see shared CPU below |

All4,592diagnostic emissions match actual current-relay payload, timestamp, amplitude and frame type exactly. **0lost /0new** versus that existing-relay cohort. All147,178measured stock records are present in the actual current relay; the two test profiles also preserve the entire captured3,407,248byte stock stream exactly by SHA-256, including opaque fragments. No capacity eviction or late-stock-after-extra race was recorded in this run. This does not prove such races cannot happen.

Reference coverage: all219inotify notifications read successfully,0file-read misses/queue overflows. Every one of4,605actual wire extras arriving in the measured interval has an observed producer reference. The4,605wire-arrival count and4,592producer-cohort count use different interval boundaries because the current relay holds data; their difference is not packet loss.

Disabled sequence/acquisition/header/SIC/pulse remain disabled. BroadCRC research output remains quarantined, never relay-eligible. The strict profile rejects all eligible extras; the youngest observed extra was already about364ms old relative to the stock-clock reference, and method medians were about0.99–1.18s at publication. Producer file observation itself was fast: approximately0.6ms median. Additional observer/guard queueing is separate.

## Latency

| Measurement | Median | p95 | p99 |
|---|---:|---:|---:|
| Existing relay stock, observed localhost delay | 3018.6ms | 3302.7ms | 3583.9ms |
| Async3s diagnostic stock enqueue | 3.12ms | 86.34ms | 94.48ms |
| Producer observation -> diagnostic extra emission | 274.5ms | 558.9ms | 617.6ms |

Stock enqueue time is measured after the observer receives its upstream chunk; it is not a client TCP delivery or RF-to-cloud measurement. Extra RF age is estimated from the latest received stock sample-clock watermark and receipt time. The resource-limited observer can receive data late, so these ages have socket scheduling/buffering uncertainty. The test ran both variants together under a35%one-core cap and included profiling/capture. Do not treat these as an unloaded production latency guarantee. Original RF timestamps were not rewritten to make late results appear fresh.

## CPU

- Existing live worker processing during the metric interval: **121.989CPU-s/180.497wall-s = 67.58%of one core**. The method table is measured exclusive computation attribution, not causal marginal cost. Shared frontend/FIR/overhead accounts for **23.21%of one core**; quarantined BroadCRC computation adds about1.49%. Do not sum just the seven output methods to infer full pipeline CPU.
- Diagnostic relay core calls: **36.685CPU-s/221.290wall-s = 16.58%of one core** (~4.14%of four-core capacity).
- Strict relay core calls: **1.11%of one core**, while emitting no extras.
- Entire observer process, including both relay variants, packet capture, profiling and health coordination: **23.19%of one core**. Child health-query CPU is outside the parent process counter. Core-call timings exclude queue/IPC/I/O overhead; they are not standalone deployed-relay CPU or an electrical-power measurement. No baseline relay CPU reduction is claimed.

The added cost in the compatibility profile makes its repeated stock-history admission scans a useful next profiling target. The5second duplicate lookup alone is not the whole relay cost.

## Distance

Quality-screened stock context supplied54estimated distant opportunities from3aircraft at180–200nm; all54were retained by the diagnostic, none by the strict profile. There were no estimated>=200nmopportunities. Unknown range remains unknown. Distribution of4,592diagnostic extras:

| Range(nm) | Extras |
|---|---:|
| 0-50 | 1043 |
| 50-100 | 1604 |
| 100-150 | 1323 |
| 150-180 | 183 |
| 180-200 | 54 |
| 200-250 | 0 |
| 250+ | 0 |
| unknown | 385 |

Range requires a prior observed stock position with NIC/NACp>=5, no MLAT/TIS-B, age<=15s and conservative availability timing. Availability is screened against the estimated RF event time, whose absolute wall-clock mapping is not present in the outbox; these bins are descriptive rather than strict causal training-label qualification. CRC validity/position metadata are not surveyed physical truth. This is transport retention, not a new decoder range improvement or training-label qualification. All captured data remains evaluation-only; no I/Q/training labels were created.

## Decision

**Keep production unchanged. Do not deploy the250ms profile.** The queue transport works, but the old one-second publication/stock-settling path prevents it from receiving sufficiently fresh extras. Widening to3s preserves the packets in this sample but leaves out-of-order extras approximately1.3–1.5s old. Earlier isolated FR24 replay showed that second-scale reordering can change local position output, so packet parity alone is not approval for FR24 deployment.

The next step is an isolated per-completion producer/admission bridge with shared rolling alignment and a stock-processing watermark, while preserving the original group/collection path. Profile indexed/shared relay guards, then repeat fresh transport and actual-FR24 semantic validation before any live condition. The ongoing stock-only cloud comparison stays separate.

Protected PIDs, decoder/collector configuration, source/library/model hashes, gain, SDR lost/dropped counters and stock-only FR24 route passed. No recording retention/cap or normal flush schedule changed. Existing pipeline CPU measurements do not include readsb/capture/feeder CPU. Binary packets, raw positions, full source snapshots and detailed candidate records remain private on the Mac; only aggregate reports are published.
