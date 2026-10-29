# Offline Rust soft-phase / EM estimator

This experiment ports `sf_em`, the disabled soft-phase estimator inside method 0
of `src/rescue/research_science.c`. It compares full window decisions at 1, 2 and
4 bounded iterations. It does not enable this research method, change any live
library or modify the existing Rust coherent pipeline.

## Selection

Historical common-RF Pi 4 measurements covered 72 captures. The EM decision
stage averaged 0.719 CPU seconds per approximately one RF second (including
coherent preparation), versus 0.071 for the coherent window kernel, 0.167 for
sequence work and 0.275 for the shared frontend. The EM method was disabled.
Header relaxation, CFAR and legacy joint had larger *whole-method* totals, but
much of their implementation was Python/NumPy. Those totals cannot identify a
most expensive maintained C function. `validation/.../selection.json` records
all these measurements and this limitation. This is an evidence-based next
native-heavy target, not an exhaustive proof of the globally hottest C function.
Historical Pi 4 rates are not treated as current Pi 5 performance.

## Port and scope

`phase.rs` implements the iterative soft PPM probabilities, payload-assisted
complex gain estimate, bounded five-frequency search per iteration, final
coherent scores and confidence. It reuses the already validated Rust CRC/table
and noise-quantile helpers through a source include; it never calls a C DSP
kernel. Rust uses safe slice indexing in the algorithm. Only the explicit FFI
boundary and elementary libm calls are unsafe. The seed, thresholds, iteration
bounds, score tie rules and repair policy remain unchanged. Rust sin_cos and C
compiler-generated paired sine/cosine operations use the target math library.

The exported research API supports only method=0 (EM). It is not a drop-in
replacement for the sequence and combined methods=1/2 of rescue_science.
Sequence detection, acquisition, frontend resampling and baseline coherent
preparation are outside timed scope. Identical precomputed initial logits,
confidence and carrier seeds are passed to both implementations. Noise median
sorting uses their existing typed C and Rust standard sorts respectively;
therefore library/compiler choices remain part of the comparison.

## Inputs and controls

The fixture contains 368 windows: eight chronological hard-header, failed-energy
candidates from each of the 42 previously consumed shared-feedback RF captures,
plus 32 deterministic Gaussian noise controls. Finite and missing carrier seeds
exercise both entry paths. Initial coherent data is frozen into the same fixture
for both versions. Private RF and predictions are not published or used as
training labels. No prospective/evaluation RF is newly consumed.

A separate control set contains 48 clean packets, 16 weak one/two-bit repair
cases and 64 Gaussian negatives. The packet has known CRC-valid content;
frequency, phase and deterministic noise vary. All clean and weak cases must
recover the intended payload; all negatives must be rejected, for every tested
iteration count. Repeated iteration tests are not independent noise trials.
This is finite implementation regression, not a false-acceptance certification.

## Reproduce

Use existing project Python with NumPy and the native frontend, plus Rust 1.99.1:

```sh
python experiments/rust-phase/prepare.py \
  --input /path/to/already-consumed/shared-feedback-20261028 \
  --output experiments/rust-phase/.work/windows.bin
python experiments/rust-phase/build.py --rustc /path/to/rustc-1.99.1
python experiments/rust-phase/controls.py \
  --work experiments/rust-phase/.work --output /tmp/mac-phase-controls.json
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  python experiments/rust-phase/benchmark.py --output /tmp/mac-phase.json
```

Common C harness, same preallocated inputs/outputs, two untimed warmups per
process, nine fresh-process alternating-order trials per iteration count.
Initialization, compiler time and output I/O are excluded. CPU is process CPU
per presented window; elapsed time under target quota is not throughput.
Memory is whole-process RSS, including identical buffers. Linux peak uses
exec-local VmHWM rather than inherited launcher ru_maxrss. Uniformly stripped
copies provide code-size measurements without altering timed executables.
All packet bytes, repair choices and hard decisions must match. Floating
scores use rtol=1e-12 and atol=1e-12; bitwise equality is reported separately.

The Pi job is staged under an owned tmpfs directory. `pi_job.sh` extracts the
same official checksum-verified Rust archives as the prior coherent experiment;
no system packages are installed. Run via `protected_job.py` at nice 19, core 3,
35% CPU quota, 1536 MiB maximum memory and a bounded 900-second runtime. The
supervisor samples health every three seconds and terminates only its owned
child process group after repeated health failures, before continuing a risky
benchmark. It never restarts receiver services. Existing guard/receiver/feeder
services, captures, models, gain, routing and limits remain unchanged.

Only owned temporary files are cleaned after verified Mac backups. Results:
[Pi/Mac report](../../validation/rust-phase-20261029/report.md).
