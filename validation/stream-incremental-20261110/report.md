# Incremental native Stream1090 — Pi test, 10 November 2026

20 ms and 50 ms chunk processing retained all tested packets, timestamps and raw order. The prototype is isolated; **the working pipeline remains unchanged**. Recommended experimental chunk size: **20 ms**.

## Paced decoder output latency

Identical saved RF was delivered at its original sample rate to each implementation separately. 8 one-second windows produced 960 core packets per mode. Latency is measured from the packet's RF end to availability of its returned decoder result. It includes context creation, chunk waiting, incomplete-block carry, native work, Python conversion and OS scheduling under the target quota.

| Mode | Median | p95 | p99 | Maximum | Paced CPU-s/RF-s |
|---|---:|---:|---:|---:|---:|
| batch | 610.0 ms | 1047.3 ms | 1126.2 ms | 1228.1 ms | 0.1057 |
| 20ms | 14.6 ms | 24.2 ms | 27.8 ms | 49.8 ms | 0.1185 |
| 50ms | 34.2 ms | 57.3 ms | 71.6 ms | 96.0 ms | 0.1169 |

The 20 ms paced cost is **12.1% more Stream1090 CPU** than batch in this short run: approximately 1.28% of one core, or 0.32% of four-core capacity. The 50 ms paced increase is 10.7%. These are branch costs, not percentages of the whole receiver's existing CPU.

This is **decoder availability, excluding live RF transport, stock calibration/admission and feeder latency**. The current coordinator still gates a whole window. It has not been changed, and early feeder release has not been validated. Earlier candidates alone cannot establish sub-250 ms end-to-end delivery.

## Throughput CPU and retention

The full replay used 119 historical one-second windows and 383 aligned short clips (143.24718 core RF seconds). Modes ran in rotating order per case. Finite replay calls used disabled per-call deadlines, while deadline rejection was tested separately; this avoids quota-related aborts in timing comparisons. All raw callback rows, payload bytes, sample timestamps and ordering matched exactly, including terminal flush. Physical-core digests also match Mac/Pi and the frozen parent reference. There were **15,221 raw core packet records per mode, zero gains and zero losses**.

Long-window throughput CPU: batch 0.1059, 20 ms 0.1098, 50 ms 0.1091 CPU-s/RF-s. The unpaced 20 ms increase is 3.6%. The larger paced overhead is reported separately because short bursts and pacing can affect scheduling/frequency and wrapper costs. One throughput pass and eight paced RF seconds do not establish tail guarantees or precise steady-state energy savings.

After the SAME deferred frozen common guards, the historical long corpus retains these extras beyond stock. **Long distances are estimates**, without NIC/NACp qualification:

| Distance (nm) | Batch | 20 ms | 50 ms | Lost |
|---|---:|---:|---:|---:|
| 0-50 | 238 | 238 | 238 | 0 |
| 50-100 | 380 | 380 | 380 | 0 |
| 100-150 | 287 | 287 | 287 | 0 |
| 150-180 | 22 | 22 | 22 | 0 |
| 180-200 | 3 | 3 | 3 | 0 |
| 200-250 | 0 | 0 | 0 | 0 |
| 250+ | 0 | 0 | 0 | 0 |
| unknown | 38 | 38 | 38 | 0 |

All three modes retain **968 long-corpus stock extras**, including the same three estimated 180–200 nm events. The recent corpus retains **11 stock extras per mode**, with stock-quality-gated distances and no extras >=180 nm. Exact raw equality preserves the parent's full current-method-union result when the same deferred masks are used; there are no new full-pipeline detections here. These data are insufficient to claim improved range, and they are historical regression RF, not fresh prospective validation.

## Implementation

`incremental.h` supplies create/feed/finish/destroy. One context persists across chunks within the current logical window. Interpolation history, magnitude blocks, eight-phase registers, sample clock, repair confidence, trust and dedup state are carried forward. Contexts reset at the current logical window boundaries; this preserves the baseline's trust semantics. No new rolling one-second window is decoded for every chunk.

Complete native 8,208-sample blocks (~3.42 ms) are processed as soon as a call supplies them; partial blocks are carried to the next chunk. **No zero padding at chunk boundaries.** Finish reproduces the batch reader's single terminal zero-padded block, even when the input ends exactly on a block boundary. The original upstream magnitude/interpolation code and seven confidence/RSSI/preamble helper bodies are unchanged. Pinned upstream source headers retain their original hashes and licensing.

The API rejects gaps, overlap, wrong order, early/repeated finish, overflow, invalid lengths and deadlines. An error poisons the logical context; previously returned raw candidates must remain quarantined until the caller's appropriate validation/commit policy. Callers must reset on a receiver epoch change. This API does not itself forward packets or implement admission.

## Controls and protected receiver

Known clean/repaired packets straddled chunk and logical-core boundaries. Tests also varied feeds around the native block size. Fixed and irregular splits, including single-sample fragments, produced exact packet/time/order parity. Untrusted repairs and noise emitted zero. Gap, overlap, incomplete close, capacity and timeout controls rejected partial output. AddressSanitizer/UndefinedBehaviorSanitizer and library-load floating-point-environment checks passed on Mac and Pi.

Target: Raspberry Pi 5 Model B Rev 1.0. Owned tmpfs only; saved RF, copied libraries, nice19/core3/CPUQuota35%, requested MemoryMax1G/zero swap and finite 450-second runtime. The kernel did not expose memory-controller enforcement. The baseline library SHA-256 was checked against the installed native library before replay. No SDR or mirror consumer was opened, no candidate packets were sent, no models/method switches/gain/routes changed, no service restarted and no capture flush requested. The 5 GB RF cap remains unchanged.

Protected PIDs, source/model/configuration hashes, native backend, gain and primary SDR loss counters matched before/after. Across setup/test the best-effort copied RF tap recorded 705,184 additional gap samples (~0.294 RF seconds); causality is not established. Primary SDR loss counters did not increase. The copied-tap observation is retained rather than claiming no RF-copy loss.

Source, frozen data/reference manifests, libraries, controls and private diagnostics are checksum-backed on Mac. All candidate outputs remain evaluation-only, never training labels. Only verified owned temporary files were removed; persistent capture archives were untouched.

## Next validation gate

The next experiment is an isolated incremental admission/relay path: causal stock-clock corroboration and stock watermarks, conflict/dedup lookahead, exact original-first packet retention, logical-window/epoch failure handling and delivery latency through the relay. Preserve the working batch path until that path passes fresh RF and target-health checks. Current deferred reference masks must not be used as evidence that the early-admission problem is already solved.
