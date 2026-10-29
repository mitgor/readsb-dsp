# Offline Rust improved-acquisition scorer/selector

Ports the maintained `rescue_extended_scores_neon` and
`rescue_extended_select_neon` routines from `pipeline_extended_neon.c`. Acquisition
is disabled in the working pipeline and stays disabled. No installed library,
model, service, routing, threshold, budget or collector setting is changed.

## Why this target?

Historical common-RF bundle timings showed selection work rising from about
0.120 to 0.437 CPU seconds per RF second when acquisition was included. This
native-heavy score/peak-selection work is the next supported target after the
coherent and soft-phase kernels. Legacy-bundle timings aggregate several C and
Python routines, so they cannot establish a single globally hottest function.
See the saved selection evidence. Historical timings are Pi 4; new target is Pi 5.
The maintained C reference includes later NEON optimization, not an artificially
slow pre-optimization baseline.

## Equivalent computation

Both use the same 18 known pulse slots, rolling double-precision 52-sample
normalization, four-lane NEON double accumulation order, scalar tail, 0.30 peak
threshold, plateau midpoint, three-sample peak spacing, stable descending top-k
ranking, strict RF/halo bounds and unchanged caller budgets. Rust validates one
fixed NEON load footprint and uses constant offsets; no fast math or reassociated
reductions are allowed. Rust's intrinsics require unsafe loads, bounded by that
validated slice; ordinary indexing/sorting remains checked.

Both return -2 for duplicate peak priorities so the existing Python/SciPy tie
fallback can remain unchanged. The experiment does not replace that fallback or
change the search. C uses libc qsort and explicit malloc/calloc; Rust uses standard
unstable sorting and fallible vector reservations. Implementation/compiler/library
choices remain part of this comparison.

## Same data and parity

The fixture contains 24 time-spread first RF blocks from the same 42 previously
consumed development captures, approximately one RF second total and 3,979,973
power samples. Power and the exact float-derived template weights are frozen
once and shared by both implementations. No new/reserved RF or training labels.

Full score arrays and candidate IDs/order/scores are compared byte-for-byte.
Nine fresh-process alternating-order trials separately time scoring and the full
selector at budgets 16, 64 and 256. Two process warmups; allocation within the
selector is timed, caller allocation, file output, initialization and compilation
are excluded. The same C dlopen driver is used for both. CPU is process time;
quota-limited elapsed time is not throughput. Whole-process RSS includes identical
fixture/output buffers and each implementation's allocator/runtime footprint.

Controls cover 1,201 exact scorer/selector cases, small/tail lengths, zero/flat
power, boundaries, budgets 1/8/16/64/256, plateau/distance behavior and the -2 tie
fallback. Candidate hypotheses from 64 complex Gaussian noise blocks are replayed
only in the frozen installed coherent library in the isolated test process;
hypotheses are not accepted messages. No CRC-valid noise outputs are allowed.
The control set is finite and is not a general false-alarm certificate.

## Reproduce

```sh
python experiments/rust-acquisition/prepare.py \
  --input /path/to/already-consumed/shared-feedback-20261028 \
  --output experiments/rust-acquisition/.work/blocks.bin
python experiments/rust-acquisition/build.py --rustc /path/to/rustc-1.99.1
python experiments/rust-acquisition/controls.py \
  --work experiments/rust-acquisition/.work --output /tmp/mac-acq-controls.json
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  python experiments/rust-acquisition/benchmark.py --output /tmp/mac-acq.json
```

Use project Python/NumPy/native frontend, with Rust 1.99.1. No Cargo dependencies.
C uses -O3 -std=c11 -ffp-contract=off; Rust uses opt-level 3, one codegen unit,
panic=abort. Both compile native ARM64 NEON on the test platforms. Private RF,
compiler archives and temporary binaries stay under ignored `.work/`.

Pi staging is a separate owned tmpfs tree. `pi_job.sh` uses the same official,
checksum-verified temporary Rust archives as previous experiments; no system
installation. `protected_job.py` monitors production and aborts only its own
process group after repeated health failures or an external protected PID change.
Run at nice 19, core 3, 35% CPU quota, 1536 MiB memory bound, 900-second runtime.
Keep the live receiver, feeders, capture and Rust coherent guard unchanged. Remove
only owned temporary files after checksum-verified Mac backups.

Results: [C/Rust acquisition report](../../validation/rust-acquisition-20261029/report.md).
