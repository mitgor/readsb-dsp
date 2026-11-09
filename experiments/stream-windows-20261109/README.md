# Stream1090 shorter RF windows — 9 November 2026

Offline experiments only. The working receiver, relay, feeders, methods, gain,
models and recorder remain unchanged. No SDR/mirror access or experimental output
injection. RF and candidate data remain evaluation-only/quarantined.

The fixed comparison uses 1,000 / 500 / 250 / 100 ms cores with the existing
600-sample halo. `prepare.py` selects historical full RF seconds by recorded
stock/range before decoding. `supplement.py` includes closed, complete-reference
v4 distant-triggered evaluation RF. Final corpus: 24 RF seconds, ten >=180 nm
stock packets from three aircraft. Both sources are consumed historical RF,
not post-freeze prospective evidence. Continuous reservations remain untouched;
an additional experiment interval manifest records provenance, never labels.

`bench_stream.py` runs the unmodified binary with the same arguments. Strict
calibration is identical to current compare(): ten shared stock frames and
MAD <=360 ticks. A separate rolling one-second hypothesis accumulates distinct
stock transmissions across clips, rejects disagreement and never bypasses final
stock/energy guards. Core ownership and 120 us transmission deduplication exclude
halo seams. Preserve known aircraft/trust safety gates; no trust seeding or CRC
relaxation is used.

`baseline.py` recomputes the full currently enabled native/Rust/neural/pulse/
sequence/acquisition ring-worker output on the Pi, using copied production
sources/libraries/models/configs. Source precedence and three-model original-first
priority remain. SIC/header off; Broad CRC paid as research CPU but not forwarded.
`analyze.py` evaluates each union against stock, complete current replay and actual
historical relay/accepted references where available, with causal quality-gated
stock distances and strict timestamp matching. No model training or threshold
selection on RF occurs.

Mac tests precede Pi, then exact packet/time parity is checked. Pi RF input is
paced at native speed for Stream1090, with nice19/core3/CPUQuota35% and finite
runtime. Four native workers share core3 during the separate full-baseline pass;
this changes scheduling, not the selected algorithms. MemoryMax1G was requested,
but this kernel lacks the memory controller; it is not an enforced RSS bound.
Protected PIDs, sources/configs/models, gain, stock loss and cap are checked every
three seconds. Only the owned child can be aborted. Never alter production.

An initial launcher ran before the upload completed and performed no benchmark;
v2 is the main completed run. A range-analysis pass was restarted with indexed
lookups; this did not change decoder outputs. The rolling anchor implementation
was audited to ensure overlapping halos cannot double-count a stock transmission.
A targeted v3 100-ms repeat on Mac/Pi confirms unchanged packet sets/timestamps.
The final 100-ms latency/CPU uses that repeat; 1,000/500/250 ms use the original
counterbalanced run. Initial/follow-up results remain separately preserved.
Uncorrected 500/250 rolling diagnostics are not part of the qualified public
comparison; the strict results are used there.

Four unit tests cover anchor-count minimum, independence, timestamp matching and
unstable-clock rejection. Mac/Pi packet and timestamp parity is exact. Current
Stream-only additions beyond every other enabled method: 34. Shortened strict
500/250 ms recover 24/11; strict100 none; rolling100 recovers five. No new packets
beyond the full current union. Stream child CPU increases ~3%/~9%/~27%. Only one
Stream-only packet is beyond180 nm, so far parity is not established. See
validation/stream-windows-20261109/report.md for complete counts and limitations.

Latency is Stream candidate-ready RF age under replay quota, not final
admission/relay/cloud latency. Historical stock wall-arrival times are unavailable.
Reported medians are conditional on surviving packets; paired saved time is
separate. CPU measures child time including restarts; bundle estimates hold all
other decoder worker CPU fixed and exclude transport/capture/coordinator.

`fetch.py` / `fetch_unique.py` verify/fsync full source/input/result bundles on Mac.
`cleanup.py` / `cleanup_unique.py` recheck exact identities/hashes before deleting
only the closed owned tmpfs root. No persistent collection archives were deleted.
Source/model fingerprints, initial failure logs and all frozen inputs/results
remain private in results/stream-windows-20261109. `report.py` publishes only
redacted aggregates through existing HTTP access. Existing output paths are
frozen; use new destinations for a subsequent experiment.

Next: a persistent stateful Stream1090 process with smaller I/O chunks, preserving
trust/filter state, explicit output flushing, gap/epoch handling and timestamp
calibration. That approach has not been implemented or validated by this test.
