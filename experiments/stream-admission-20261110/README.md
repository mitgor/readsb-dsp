# Incremental Stream1090 admission and anonymous relay replay

This experiment follows the decoder-only `stream-incremental-20261110` study.
It is **not installed in production**. Before this experiment, at 16:37 UTC,
the existing rollback guard had restored the executable after a sample-loss
counter increase. This experiment leaves that fallback unchanged. The timed
reference here is the previously validated extended native batch decoder, not
a claim that the native library is currently active. The guard trigger alone
does not attribute the counter change to a particular workload.

## What is tested

Eight contiguous historical RF seconds from the reserved completion-bridge
fixture, with actual recorded stock arrival times. Two independent workers run
Stream1090 and the existing energy frontend. Stream1090 receives either the
whole one-second logical window or successive 20 ms chunks. Energy uses its
unchanged 50 ms FIR blocks and hard decisions; no neural predictions supply
stock identity or alignment. Native trust resets at the original one-second
window boundary. Only already available producer output and stock can authorize
an early result.

`bridge.py` reuses production `stream1090_shadow.compare` for clock acquisition
and `shadow.evaluate` for energy alignment, CRC, stock-only prior identity,
conflicts and duplicate checks. An early 20 ms slice waits for both producer
watermarks and the stock watermark. The energy audit covers at most the previous
RF second. Alignment requires 20 energy matches and median error <=2 us; native
clock acquisition requires the existing 10-match check. The clock mapping stays
fixed within a logical window and is checked again at finalization. Energy
candidates have single ownership in the logical core; halo copies cannot supply
additional alignment votes.

Cold-start slices without enough evidence do not bypass the guards. A separate
finalization lane reuses cached raw results at the original one-second boundary.
It does not decode RF again. Both lanes enter one final five-second Rust history
with 120 us transmission matching, using the previously tested dependency-free
`energy-coherent-async-20261030/dedup.rs` library. Same payload at a different
transmission time remains eligible. Original captured stock DF17 frames always
pass, including late arrivals; a late-stock race is counted explicitly.

Final output is an anonymous AF_UNIX socketpair with a bounded RAM-only sink.
There is no listening socket, SDR connection, mirror consumer, production outbox,
FR24/ADSBExchange connection or external packet injection. Original captured
stock Beast bytes and order are checked across the sink. This fixture retained
DF17 stock metadata only: the byte-preservation result does not cover uncaptured
stock message types. Candidate output remains quarantined.

## Limits of the comparison

This is a timed **energy + Stream1090** subset. Recorded complete-pipeline producer
and actual-relay records provide post-measurement masks; missing per-method
completion times prevent an honest timed replay of all other algorithms. The
reference is historical, not fresh prospective validation. The RF wall origin
is estimated; original 20 ms tap-arrival timestamps are absent. Socket receive
latencies and a +50 ms clock sensitivity are reported, without claiming physical
antenna-to-feeder latency or a guaranteed clock-error bound. One or a few distant
packets cannot establish a range improvement.

`controls.py` exercises future-stock rejection, missing energy watermarks, epoch
rejection, invalid CRC, finalization fallback, the shared cross-method history,
new repeated transmissions, stock-only prior identity/conflicts, late-stock
preservation and rejection of unvalidated extras. The incremental decoder's
separate boundary/deadline/overflow/noise/sanitizer tests remain in the preceding
study; this experiment does not modify that decoder.

## Reproduction

Use the existing private Python environment, copied runtime and checksum-verified
libraries. BLAS/OMP threads must be one. The original private fixture is
`data/raw/completion-bridge-20261030/capture`, reserved evaluation-only in
`data/raw/long-validation-completion-bridge-20261030/reserved-intervals.json`.

```sh
PYTHONPATH=/path/to/copied/runtime OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  /path/to/python benchmark.py --capture /path/to/capture \
  --batch /path/to/current-native.so --incremental /path/to/incremental.so \
  --dedup /path/to/dedup.so --output /path/to/new-output.json
```

Outputs are append-only: the benchmark refuses existing output paths. Packet-level
results and receiver snapshots stay in the private workspace. Only aggregate
results belong in the public report. Pi supervision verifies stage hashes against
the manifest and copied production source/library hashes against the live files,
then verifies the pinned native baseline hash and protects service PIDs, configurations, methods, gain, sample-loss counters,
FR24 connection, status freshness and collection limits. Target execution is
nice19/core3/35% of one core, with a finite deadline and 1 GiB memory limit
requested. Memory-controller availability must be reported rather than assumed.

## Admission profiling and repeatability

The first quota-limited Pi replay was not acceptable: repeated full stock-history
maximum scans and broad dictionary copies built a queue and caused age-guard
rejections. Replacing just the repeated maximum scans improved CPU but still lost
packets under the quota. Both results and their sources are retained privately.

The final version maintains the exact stock high-water mark on insertion, uses
payload indexes for native clock matching, and supplies `shadow.evaluate` with
an immutable `StockSnapshot` containing precisely the payload/identity indexes
that its candidate list can query. Stock evidence, RF-age limits, CRC, thresholds,
method priority and window semantics are unchanged. `VERIFY_ADMISSION=1` runs both
the narrowed and original full-index function for every admission call and
requires identical rows, audits and decision counters. The full eight-second Mac
parity audit is saved separately from uninstrumented timing runs.

`evidence.py` can preserve the closed owned tmpfs tree with member SHA-256 checks,
reusing identical Mac input files rather than transferring RF already held on the
Mac. It downloads changed/new immutable members, verifies every file, fsyncs files
and directories and creates a separate checksum-backed private binary archive.
It does not delete remote files or touch persistent collection datasets.

## Result

The final Pi replay retained all 79/79 extras (32 energy, 47 Stream1090) and all
6,630 captured stock DF17 frames, with no raw decoder/energy parity differences.
It consumed 0.3704 process CPU seconds per RF second versus 0.3366 for the native
batch subset. Under the 35%-of-one-core quota, median sink latency was 732 ms,
p95 1,093 ms and 19/79 extras arrived within 250 ms. The latency gate therefore
remains unmet. This is not a deployment candidate. Only one recovered packet had
a qualified recorded range >=180 nm; none of the results establish better range.

See `validation/stream-admission-20261110/report.md` for the Mac comparison,
per-method/distance counts, earlier failed quota gates, memory-controller limit
and the pre-existing live native rollback. All benchmark evidence was copied,
member-hash verified and fsynced on Mac before removing 256 owned tmpfs files.
No persistent collection archive was deleted. Production source/model hashes,
service PIDs, settings, gain, cap and primary sample-loss counters stayed unchanged.
