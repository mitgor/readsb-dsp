# Disabled soft-phase estimator: C versus Rust

29 October 2026. Offline experiment completed on Mac and Pi; the working Rust coherent pipeline, FR24, ADS-B Exchange and RF collection remain unchanged. This estimator remains disabled.

## Why this routine?

The historical 72-capture Pi 4 comparison attributed a mean 0.719 CPU seconds per approximately one RF second to the soft-phase decision stage, including coherent preparation. The coherent kernel itself averaged 0.071; sequence work 0.167; shared frontend 0.275. This makes the disabled soft-phase/EM estimator a useful next native-heavy target. Larger header/CFAR/legacy-joint whole-method totals include substantial Python/NumPy work and cannot rank maintained C functions. This is not an exhaustive proof of a globally most expensive C function. [Selection evidence](selection.json).

The port targets sf_em / method=0 of research_science.c: soft PPM probabilities, payload-assisted gain, five-frequency refinement per iteration, final bit confidence and restricted CRC repair. Initial coherent logits/confidence and carrier seeds are frozen into the same input for both versions; their preparation is excluded. Rust implements the estimator itself and reuses the validated Rust CRC/quantile helpers. It makes no C DSP-decoder calls. The original sequence and combined science methods are outside scope.

## Matched CPU results

Nine fresh-process trials, alternating implementation order, identical preallocated driver/buffers, two untimed warmups. Lower time is better. Compilation, initialization and I/O are excluded.

| Target | Iterations | C µs/window | Rust µs/window | CPU saving |
|---|---:|---:|---:|---:|
| Mac M4 Max | 1 | 22.909 | 20.326 | 11.3% |
| Mac M4 Max | 2 | 38.583 | 34.789 | 9.8% |
| Mac M4 Max | 4 | 67.945 | 61.559 | 9.4% |
| Raspberry Pi 5 | 1 | 127.588 | 114.356 | 10.4% |
| Raspberry Pi 5 | 2 | 218.160 | 197.676 | 9.4% |
| Raspberry Pi 5 | 4 | 399.134 | 362.166 | 9.3% |

The two-iteration row matches the historical candidate setting. One and four iterations exercise its bounded range. Historical Pi 4 stage costs and current Pi 5 kernel timings use different hardware/scopes and must not be treated as direct speedup measurements. None of these kernel savings are whole-pipeline or wattage claims.

## Memory and parity

| Target, two iterations | Implementation | Resident MiB | Debug-stripped executable KiB |
|---|---|---:|---:|
| Mac | c | 4.234 | 50.6 |
| Mac | rust | 4.422 | 1400.8 |
| Pi | c | 4.594 | 70.5 |
| Pi | rust | 4.984 | 1580.3 |

Resident memory is the complete standalone process, including identical input/output buffers; compiler memory is excluded. Linux uses exec-local VmHWM/current RSS, not inherited launcher ru_maxrss. Executable size is measured on uniformly debug-stripped copies, separate from timed executables and physical RAM. Rust statically includes parts of its standard runtime.

The fixture contains 368 windows drawn from 42 already consumed RF captures plus deterministic noise, with identical precomputed initial decisions and a mixture of supplied/automatic carrier seeds. All packet bytes, repair choices and hard decisions match. Floating diagnostics use rtol=1e-12 and atol=1e-12; bitwise equality is also checked and reported below.

Mac, 1 iterations: all output bytes identical = True; maximum logit difference 0, confidence 0, frequency 0 Hz. Accepted window outputs: 2; Gaussian-control accepts: 0.
Mac, 2 iterations: all output bytes identical = True; maximum logit difference 0, confidence 0, frequency 0 Hz. Accepted window outputs: 2; Gaussian-control accepts: 0.
Mac, 4 iterations: all output bytes identical = True; maximum logit difference 0, confidence 0, frequency 0 Hz. Accepted window outputs: 2; Gaussian-control accepts: 0.
Pi, 1 iterations: all output bytes identical = True; maximum logit difference 0, confidence 0, frequency 0 Hz. Accepted window outputs: 2; Gaussian-control accepts: 0.
Pi, 2 iterations: all output bytes identical = True; maximum logit difference 0, confidence 0, frequency 0 Hz. Accepted window outputs: 2; Gaussian-control accepts: 0.
Pi, 4 iterations: all output bytes identical = True; maximum logit difference 0, confidence 0, frequency 0 Hz. Accepted window outputs: 2; Gaussian-control accepts: 0.

For each iteration setting, separate synthetic controls recover all 48 clean packets and 16 weak repair cases (eight one-bit, eight two-bit), with the expected CRC-valid payload and matching repairs. All 64 Gaussian negatives are rejected. The 32 field-fixture noise controls are also rejected. These finite controls do not establish a general false-positive bound. No unverified prediction is promoted into a training label or feeder input; no new reception improvement is claimed.

Rust 1.99.1 opt-level 3, one codegen unit, panic=abort; C -O3 -std=c11 -ffp-contract=off. No fast-math or target-native specialization. Elementary sine/cosine/exp/min/max use target math semantics. C and Rust retain their typed median-sort library choices, and different compiler backends remain a confounder; this is not proof of an intrinsic language advantage.

## Isolation and interrupted first run

The first Pi run was stopped by the safety supervisor after the DSP service was restarted outside this experiment. Its optional latency metric was temporarily None during startup, causing the monitor to reject the sample. Partial timings are excluded. FR24, readsb and RF capture stayed running; the existing Rust coherent release remained active. The event is preserved in [interruption evidence](interruption.json) and the original log.

The monitor was clarified to detect PID changes before inspecting optional startup metrics. The same frozen estimator and input were then rerun against a fresh healthy baseline. The successful second attempt preserves all protected receiver, feeder, capture and shadow PIDs and configurations, with unchanged SDR loss/drop counters. The test supervisor samples every three seconds and kills only its own test process group if health checks repeatedly fail.

All Pi work uses owned tmpfs, nice 19, core 3, 35% CPU quota, bounded memory and runtime. Rust compiler archives are checksum-verified and temporary; no packages, libraries, models, gains, method switches, services, routing or capture caps were changed by the experiment. No live SDR or mirror consumer was opened, and no extra capture flush occurred.

## Decision and reproduce

Keep the estimator disabled. The Rust implementation is a performance candidate, not an instruction to deploy an expensive research method. Earlier evidence for useful incremental distant recoveries remains sparse; reducing its cost does not establish a reception benefit.

[Source and reproduction](../../experiments/rust-phase/README.md) · [Rust estimator](../../experiments/rust-phase/phase.rs) · [Mac trials](mac.json) · [Pi trials](pi.json) · [Pi controls](pi-controls.json) · [Mac controls](mac-controls.json) · [Receiver health](pi-health.json) · [Manifest](input-manifest.json) · [Provenance](provenance.json).
