# Frozen companion: complete pipeline replay on Mac and Pi — 4 November 2026

**Alignment checks now pass on both machines. The frozen companion added zero unique guarded transmissions beyond the complete enabled pipeline and zero beyond that pipeline plus the previous best offline companion. No baseline packets were lost. Keep the new companion offline.**

## Alignment diagnosis and correction

The initial 2.10743-second sample contained only 29 shared Stream1090/stock packets. Their offsets were already stable (-1631 to -1628 ticks), but the comparison required at least 100 anchors. This was inadequate calibration coverage, not evidence of an unstable Stream1090 clock. The parser and production Stream1090 service were not changed.

The repaired offline workflow combines six original, immutable RF archives that were globally reserved for evaluation before training. It keeps the minimum 100 anchors, original MAD bound and sample-clock guards, and additionally requires every archive's measured offset to agree with the shared clock within 24 ticks. No artificial payload matches, forced offset, relaxed threshold or model tuning was used.

Expanded replay: 256 closed RF groups, **18.39535 RF seconds**, 17.88335seconds after 1 ms edge trimming at each end. One incomplete latest burst is excluded. Stream1090 supplies **163 shared anchors**, median offset **-1629ticks (-135.75us at12MHz)**, global MAD 0 ticks. Per-archive anchors 26/27/38/28/15/29, all median -1629 ticks and MAD 0–1 tick. Source/frame clocks and the companion hash stay fixed. All three Mac runs and all three Pi runs have identical accepted packet/timestamp signatures, distance bins and losses.

## Full enabled baseline and packet recovery

Current enabled methods: stock, energy, restricted CRC computation, timing, soft, matched, coherent with pair retry, original-first three-model neural cascade, and Stream1090. Broad-CRC outputs remain quarantined and do not count as feeder detections. Sequence, acquisition, pulse, header and SIC remain disabled. The prior best October 29 DSP companion is tested as a separate additional baseline, not silently counted as live.

The baseline is refreshed to current source/native policy: the Mac C coherent and pair kernels were rebuilt from copied live source, while Pi replay uses copies of the actual installed shared libraries and Stream1090 executable. Frozen candidate SHA256: 38f15bc328c3705e36a7a098f6f7a523d9781641e6e3b2aac467374ffd20c8d9. No retraining occurred in this validation.

Recovered extras beyond stock:

| Distance, nm | Current pipeline extras | New companion beyond current | New companion beyond previous best union |
|---|---:|---:|---:|
| 0-50 | 39 | 0 | 0 |
| 50-100 | 61 | 0 | 0 |
| 100-150 | 53 | 0 | 0 |
| 150-180 | 4 | 0 | 0 |
| 180-200 | 2 | 0 | 0 |
| 200-250 | 0 | 0 | 0 |
| 250+ | 0 | 0 | 0 |
| unknown | 33 | 0 | 0 |
| **All** | **192** | **0** | **0** |

Only one aircraft has quality-confirmed stock range beyond 180 nm in this RF, and the current pipeline already recovers two extras in 180–200 nm. There are no confirmed 200+ nm opportunities here. The supplied training experiment's two additional distant test-window reconstructions are not new field detections and cannot be added to this table. Original stock/valid outputs retain priority; raw baseline losses and additive union losses are zero on both machines.

Comparison masks cover the full current replay, the previous best replay, original recorded stock, actual unified relay output and conservative recorded provisional method annotations. Compact references retain exact multiplicity for 1206 stock and 1410 unified frame instances inside measured RF;2833 causal-address queries agree with the originals. Reference compaction is a replay memory optimization, not payload deduplication or a change to production. Annotations remain best-effort and are not claimed to be a complete authoritative acceptance ledger or supervised labels.

## CPU, median of three identical-RF passes

CPU-seconds consumed per RF-second, summed serial algorithm replay:

| Bundle | Mac | Pi |
|---|---:|---:|
| Current production pipeline | 0.2200 | 0.7482 |
| Production + previous best offline companion | 0.2157 | 0.7795 |
| Above + new frozen companion | 0.2225 | 0.8249 |
| New companion inference alone | 0.0061 | 0.0327 |

The new companion inference costs **0.0327 CPU-seconds/RF-second on Pi** (range 0.0326–0.0335). That is approximately3.3% of one core, or 0.82% of four cores, for this inference step alone after the previous-best cascade; roughly 4.4% of the measured production algorithm CPU. Mac incremental inference median is 0.0061 CPU-seconds/RF-second.

Replay includes separate serial frontend work and launching Stream1090 for each short clip. The production shared ring, live scheduling, admission, statistics and transport overhead are not modeled by this CPU sum. Differences of small bundle timings include warmup/cache/order noise, so a lower Mac median for the previous-best bundle is not an optimization claim. These are not electrical-power measurements. With zero unique additions, no beneficial CPU-per-additional-detection ratio is established.

## Controls, protected execution and preservation

Six Stream1090 parser/comparison tests pass. Frozen training controls are retained: zero unexplained valid outputs in clean/noise checks, 20,000 noise windows per model, known secondary-interferer outputs explicitly accounted for, and zero exported packet/bit differences. All original waveform/source/model/reservation manifests are private and unchanged. The RF does not overlap any new training interval and is evaluation-only; it predates candidate freeze and is not post-freeze prospective evidence.

Pi replay ran only in an owned tmpfs directory using nice 19, core 3, CPUQuota 35%, requested MemoryMax1G and a 900-second finite unit. 93 health samples passed. Observed replay high-water RSS was 191248 KiB; the kernel did not expose MemoryCurrent, so MemoryMax enforcement is not claimed. The first cleanup stopped on a root-owned Python cache; remaining owned files were reverified against durable Mac backups and removed with established sudo. No persistent archives were removed during validation.

Protected PIDs, sources/libraries/models, configurations, method switches, gain 38.6 dB, capture cap 5,000,000,000 bytes and SDR loss/drop counters match. FR24 remained connected directly to stock 30005 with valid timing. The 24-hour trial's deadline remains 4 November 18:10 Berlin. No SDR opening, mirror use, service restart, flush, pipeline routing change or candidate deployment occurred.

All results and native binaries were checksum-copied back before temporary cleanup. Private results: results/companion-validation-20261104; RF/runtime/input and result TARs: data/transfer/companion-validation-20261104. The existing validated companions remain retained. More untouched distant RF with complete references is required before claiming reception improvement.
