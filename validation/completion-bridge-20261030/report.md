# Per-completion bridge: isolated Pi validation

Implemented and tested, **not ready for deployment**. FR24 remains direct stock on port 30005 through 1 November at 20:00 Berlin. Working DSP, combined relay, ADS-B Exchange and collection remain unchanged. Target hardware reports **Raspberry Pi 5**, despite older Pi4 references.

## Results

Eight fresh contiguous RF seconds were captured from the idle optional mirror, checksum-transferred and reserved evaluation-only before replay. No SDR access, persistent recorder flush, model fitting or feeder injection. This is repeated engineering evaluation, not independent prospective validation.

The unchanged grouped replay exactly reproduces all 188production worker-pool extras, **including payload, sample timestamp and method attribution**. The other 22production extras are Stream1090, a separate producer outside this pool bridge. They are not decoder replay misses.

Final capped target run retained 58/188 extras (30.9%) within the diagnostic 3 s ceiling, **0/188 below 250 ms**. All 58 match actual production admissions and relay transmissions; zero new unexplained transmissions. The normal grouped output retains all 188; only the isolated early-admission branch loses packets. No live output is affected.

| Baseline method | Full replay extras | Retained <=3s, any completion | <=250ms | Median retained age | Exclusive method CPU-s |
|---|---:|---:|---:|---:|---:|
| energy | 32 | 11 | 0 | 1.796s | 0.288 |
| timing | 25 | 6 | 0 | 2.141s | 0.089 |
| soft | 28 | 11 | 0 | 2.129s | 0.038 |
| matched | 17 | 3 | 0 | 1.973s | 0.093 |
| coherent | 68 | 21 | 0 | 1.800s | 0.876 |
| neural | 18 | 6 | 0 | 1.146s | 0.948 |

Retention is attributed to each packet's baseline method even when a different method completes first. The actual first-completion emission attribution is energy 11 / timing 1 / soft 3 / matched 2 / coherent 41 / neural 0: adding these to the baseline counts would double-count transmissions. For example, six baseline neural packets survived through another earlier completion.

## CPU and latency interpretation

Worker computation: **4.224 CPU-s  / 8 RF-s = 52.8% of one core at real time**. Admission bridge: **1.057 CPU-s  / 8 RF-s = 13.2% of one core**. These together require about66.0% of one core, before remaining coordination/I/O. The entire copied observer was capped at 35% of one core, nice 19 / core 3 / 1 GiB, so backlog is expected. Replay wall time was22.61s. Method CPU columns are exclusive measured attribution; shared frontend, CRC quarantine and overhead are additional. CPU time is not electrical power.


This deliberately restricted full decoder copy cannot establish sub-250 ms production performance. Production uses multiple existing workers; the intended bridge would reuse their results, not duplicate inference. No lower live CPU or production latency claim is made. CPU utilization is scheduling-sensitive: the preceding engineering run retained 73/188 under the same cap; the final old-epoch-safety repeat retained 58/188. Both retained zero under 250 ms. This variability is preserved rather than selecting the better run.

Ages are estimated pre-transport event-to-admission times on a real-time-paced replay. RF time is anchored to original final-batch readiness minus 1.0005 s; USB buffering and earlier input latency are not measured. The old tap wall timestamp is roughly 33 ms later than this availability-derived origin. Do not interpret these as antenna-to-output or RF-to-cloud measurements, or compare them directly with the earlier unconstrained production observer medians.

## Implementation and safeguards

`CompletionPool` copies raw completed-future events before the ordered whole-second grouping stage. A slow coherent future does not block a completed DSP future. Original grouping/statistics/collection output remains intact. Raw seam candidates must not be pre-deduplicated: the original merge is non-transitive.

`Bridge` reuses unchanged production admission on indexed stock history, causal rolling energy anchors and a stock-progress watermark. It retains CRC, 20 alignment matches/median <=2 us, prior-stock address, conflict, 120 us duplicate and bounded 5 RF-second shared history checks. Pending anchor windows survive stock progress until their admission deadline; expiry remains explicit. The input owner explicitly changes epochs, preventing late old futures from resetting the bridge. Epoch/alignment failures fail closed. Original timestamps are never rewritten. Broad CRC predictions remain quarantined.

An optional `publish_to` adapter submits individual guarded events to the experimental AsyncFanIn. It opens no sockets and is not attached to any feeder. The target measurements stop at admission; additional TCP-delivery latency is not included. Stream1090 needs a separate guarded completion adapter before this covers the full pipeline.

Nine tests pass on Mac and Pi: independent completion, raw seam preservation, watermark gating, shared deduplication, out-of-order completion, pending-anchor retention, actual CRC/address/conflict gates, old epoch rejection and publication field preservation (some checks share test cases). Frozen source/model hashes, protected PIDs/configs, gain 38.6 dB, zero SDR lost/dropped counters, stock-only FR24 route and capture limits passed. The optional mirror was released normally. No 5 GB cap, retention or normal 12-hour flush schedule changed.

## Engineering history and next gate

The first target attempt failed an overly short replay-harness deadline; its evidence is retained. A second separated-window diagnostic exposed overly aggressive anchor eviction and is not a continuous performance result. Contiguous capped attempts 3/4 preserve their different scheduling outcomes. Decoder arithmetic, weights and admission thresholds were not tuned on RF. All source/data evidence remains private on Mac.

**Keep production unchanged.** A safe next gate is controlled shadow integration that reuses existing worker results, with indexed/shared admission profiling, complete Stream1090 coverage and measured source-to-admission p50/p95/p99. It requires validation at the real production scheduling topology rather than treating this 35% duplicate observer as its latency predictor. Any later trial must preserve the ongoing FR24 stock-only comparison and separately validate actual FR24 behavior.
