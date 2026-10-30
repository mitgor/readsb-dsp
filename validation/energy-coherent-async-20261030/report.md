# Independent energy/coherent test with shared Rust deduplication

**Isolated only. No live switches or feeder routes changed.** Stock-only FR24 remains on port 30005 until 1 November at 20:00 Europe/Berlin; the existing combined pipeline, ADS-B Exchange, gain and collection stay unchanged. Target hardware reports Raspberry Pi 5.

## Architecture

Two independent spawned processes consume immutable 50 ms UC8 chunks through separate bounded queues. Each has its own frontend/resampler/candidate work: coherent does not wait for energy to publish or finish its worker job. No neural, timing, soft, matched, acquisition, sequence, header, SIC, pulse, Stream1090 or broad-CRC work runs in the isolated decoders. Those methods remain unchanged in production.

Completed candidates pass original CRC/address/conflict/sample-clock/stock-progress admission. Coherent still needs sufficient causal rolling energy/stock evidence for alignment (20 matches, median <=2 us). That safety prerequisite is explicit; it is not a whole-second producer barrier. Startup unverified alignment fails closed.

A **single shared Rust final cache** sees original stock plus admitted energy and coherent extras. Five-second monotonic retention, 100000-entry cap, full 14-byte payload and RF timestamps within 120 us identify the same transmission across both filters. The five seconds is memory lifetime, not waiting time or payload-only suppression. The same payload transmitted again later survives. Stock frames always pass, including stock arriving after an already emitted extra; those races are counted. Epoch/unvalidated/stale inputs fail closed. Original RF timestamps are preserved. There is no final timestamp sorting or output holdback. Existing admission still screens stock duplicates; Rust is the one shared final transmission cache.

The experimental output is Beast bytes in owned RAM, never connected to FR24/readsb/ADSBx. This replay records captured CRC-valid stock DF17 only; it is not a new lossless test of every possible opaque/control Beast type.

## Pi results

Eight previously reserved RF seconds from completion-bridge-20261030 were replayed with fixed 50 ms dispatch, nice19/core3/CPUQuota35%/MemoryMax1GiB. Both worker processes share the one permitted CPU for this safety-limited test; they are independently asynchronous, not a two-core throughput benchmark. This is repeated engineering RF, not independent prospective evidence or parameter fitting.

| Method | Complete two-method baseline | Retained | Estimated <=250 ms | Median / p95 age |
|---|---:|---:|---:|---:|
| energy | 32 | 22 | 5 | 284 / 355 ms |
| coherent | 135 | 65 | 0 | 405 / 481 ms |

Final repeat: **87/167 extras retained**, 5 estimated below 250 ms. Every emitted extra matches both recorded production acceptance and the actual relay; zero unexplained additions. All 5655 captured stock DF17 frames preserve payload, signal byte, timestamp and order in the final Beast output. The shared Rust cache rejected10 cross-stream duplicates, with no capacity eviction or late-stock race in this sample. History ended with714 entries.

The initial repeat retained90/167with0under 250 ms, energy median312 ms and coherent median418 ms. The final repeat added full-baseline CPU instrumentation and an explicit final contract check; decoder parameters were unchanged. Both outcomes are preserved, not separate fresh validations.

The complete two-method baseline contains 167 of the 210 recorded full-pipeline extras (79.5%), or 167/188 excluding the separate Stream1090 source (88.8%). This is an eight-second coverage comparison, not a general guarantee. Arrival-order deduplication can change the credited method.

## CPU and queue pressure

Complete two-method worker computation (including jobs shed from the timed stream and evaluated later only for baseline coverage): energy 1.364 CPU-s, coherent 1.902 CPU-s over 8 RF-s, together **40.8% of one core at real time**. Worker demand alone exceeds the 35% cap. Timed-stream admission adds 0.418 CPU-s; final Rust calls add 0.040 CPU-s (0.51% of one core at real time, including ctypes/call instrumentation). Shared CPU scheduling, input/coordination and admission remain additional costs.

Energy shed48/160 chunks; coherent shed79/160. One source being full does not stop the other source accepting a job. Median worker queue waits were124 ms and215 ms respectively. All 320 jobs were eventually evaluated for a complete two-method baseline; those late baseline-only results were never emitted and their CPU is separated from timed-stream CPU. Timed replay lasted8.32s; that excludes later baseline completion.

These queue drops and latencies are not production losses: the live pipeline never used this copy. A reliable sub-250 ms claim is not supported. Ages are pre-feeder replay estimates based on RF sample offsets and original last-chunk readiness minus 1.0005 s; unmeasured USB/input timing and local socket delivery/cloud latency are excluded.

## Rust/reference checks

Three native Rust tests pass on Mac and Pi. A further 50007-event trace matches every Python-reference decision, counter and bounded history length, covering expiry,capacity,epoch changes, adjacent timestamp bins, unvalidated extras and late stock. A final-stage test passes on both platforms, checking cross-method suppression, repeated broadcasts, preserved late stock and invalid-CRC rejection.

Pi interface-inclusive 100000-event benchmark: Python 0.453 CPU-s versus Rust 0.380 CPU-s, **16.1%less CPU** for this trace. On Mac the call-by-call wrapper was similar/slightly slower; no universal speedup is claimed. Rust deduplication is not the dominant latency source here. All original guards remain before its input; CRC validity alone never authorizes a packet or a training label.

## Decision

**Keep this experimental.** The requested independent paths and shared final Rust cache work, but the 35% one-core copy is undersized and sheds work. Reliable low latency needs adequate scheduling for the two workers and admission, or less frontend/guard cost; the normal production integration should reuse existing computation. Full independence deliberately duplicates frontend calculation. Keep the stock-only FR24 trial separate; no automatic deployment is scheduled.

Protected PIDs/config/source/model hashes, gain 38.6 dB, zero SDR lost/dropped and capture limits passed. No persistent archive deletion, recorder flush or 5 GB cap change. RF, packet-level logs, model/source snapshots and both test repeats remain private on Mac. Only aggregate results are published.
