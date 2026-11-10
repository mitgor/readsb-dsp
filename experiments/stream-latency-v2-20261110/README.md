# Stream1090 latency v2: four isolated changes

This follows the `stream-admission-20261110` experiment. It implements the four
requested latency changes without installing them in the working pipeline.
Four separate implementation agents supplied the four components; the parent
integrated and benchmarked them. Receiver/feeder configuration, methods, models,
gain, routing, collection and retention remain unchanged.

1. **Shared energy completion input.** `shared_energy.py` accepts complete,
   already-computed pre-admission energy output, including stock-matching anchors.
   It enforces causal availability, contiguous exclusive RF ownership, epoch,
   completion sequence and bounded memory. It never decodes RF. Extras-only
   production journals cannot substitute for the required complete energy input.
2. **Rust admission.** `native_admission.rs` maintains bounded stock-only indexes
   and reproduces production CRC, alignment, identity, conflict, 120 us matching,
   neural/energy duplication and all 12 source priorities. Exact quarter-tick
   timestamps preserve historical timing/matched records. The Python boundary
   keeps candidate metadata and returns the original selected dictionaries.
3. **Completion-driven publication.** `completion_bridge.py` tracks changed
   evidence and unfinished windows. Future callbacks wake the benchmark directly;
   scheduled RF/stock arrival events set its next timeout. Idle polling is absent
   from the optimized condition. Both producers' coverage and available stock
   still limit what can be authorized.
4. **Cold-start retry.** `cold_start.py` retains pending slices and retries them
   after relevant evidence changes. Later RF anchors may authorize an older
   packet only after those anchors have actually arrived. It does not relax the
   original audit or identity checks. Finalization remains a no-redecode fallback.

The final five-second Rust transmission history and anonymous AF_UNIX socketpair
sink are reused from the preceding experiment. Original stock DF17 wire bytes
and order remain checked. No listening port, production outbox, SDR connection,
mirror consumer, candidate feeder connection or live publisher is created.

## Comparison and accounting

The paired comparison runs the prior 20 ms decoder/indexed-Python admission and
the new integrated 20 ms path on the same eight reserved historical RF seconds.
Two trials reverse the condition order. Both include actual energy decoding once
inside measured total process CPU: the optimized sharing adapter receives those
completed producer results rather than decoding again. Upstream and consumer
CPU are reported separately. This demonstrates a sharing contract; it does not
claim a measured saving across an actual live production publisher/consumer pair.

Raw native output must match the unchanged batch decoder exactly, including
packet order and timestamps. Raw energy hashes and original stock wire hashes
must match across conditions. Unique extras are compared with the same complete
saved stock, recorded other-method/full producer masks and actual relay, with
strict causal admission and normal 120 us transmission matching.

This is an engineering regression, not fresh prospective RF or a timed replay of
all enabled algorithms. Other methods lack completion timestamps. The RF origin
is estimated: original 20 ms tap-arrival times are missing. Reported latency ends
at the anonymous socket sink, never FR24/cloud delivery. A +50 ms sensitivity is
not a proven physical clock-error bound. One known recovered >=180 nm packet
cannot establish better distant recovery; uncertain ranges stay unknown.

## Controls and target isolation

Component controls cover sharing/future-completion rejection, epoch/coverage
bounds, Rust/full-Python output/audit/counter parity, quarter-tick precision,
CRC/identity/conflicts/source order/eviction, idle bridge behavior and bounded
cold-start retries. Invalid candidate predictions never become training labels.

Use the private project Python with copied runtime and BLAS/OMP threads one.
The target job verifies all copied code/input/library checksums and current live
source hashes before acting. It builds with existing pinned Rust 1.99.1 archives
inside owned tmpfs; no system toolchain installation or new access is needed.
It runs nice19 on core3, CPUQuota35% of one core, finite deadline, MemoryMax1G
requested and zero swap. The Pi lacks a memory controller, so memory enforcement
must not be claimed. Protected service PIDs, settings, methods, gain, primary
sample loss, connections, status freshness and RF cap are monitored. On failure
only the owned test child is stopped.

The live native rollback guard had already restored the executable earlier on
10 November after a sample-loss counter increase. This experiment leaves that
fallback intact and uses the checksum-pinned previously validated native batch
library only as an isolated reference.

Private RF, per-packet records, snapshots, compiler/input manifests and immutable
binary evidence remain in the private workspace. Only sanitized aggregate reports
belong under `validation/stream-latency-v2-20261110`. Cleanup is restricted to owned
tmpfs files after durable, checksum-verified Mac backup; the 5 GB collection cap
and all persistent capture archives are preserved.

## Paired Pi result

Both trials retained all 79/79 extras: 32 energy and 47 Stream1090, with original
stock bytes preserved and exact raw native/energy parity. The optimized condition
published every extra early, without using the finalization fallback. Median
estimated test-sink latency improved from 957/571 ms to 189/151 ms. Optimized p95
was 488/250 ms, so the sub-250 ms tail goal is not consistently achieved. Average
whole-subset CPU demand decreased from 0.3740 to 0.3444 CPU seconds/RF second
(7.9%). Upstream energy computation is included once in both totals.

The final integration also removes redundant Python history snapshot copies:
clock lookup uses the current stock index synchronously on its single owner
thread, while Rust remains authoritative for admission. Earlier quota-bound
integration results and the stopped empty-engine-truthiness harness are preserved
privately. No successful result from the invalid harness is used as evidence.

See `validation/stream-latency-v2-20261110/report.md`. Longer untouched RF and actual
arrival/completion timestamps are required before a production latency claim or
activation. Only one recovered packet had a known range >=180 nm.
