# Coherent decoder: C, Rust and Goose, one-to-one

Completed 29 October 2026. The working receiver pipeline remains unchanged.

## CPU comparison

All six variants were rebuilt and rerun together on exactly the same 3,269 saved windows. These are nine-trial median process CPU times per presented window; initialization, file I/O and compilation are excluded. Lower time is better. Negative savings mean a slowdown.

| Target | Implementation | µs/window | Saving vs original C | Saving vs current C |
|---|---|---:|---:|---:|
| Mac M4 Max | Original C | 8.638 | 0.0% | -32.8% |
| Mac M4 Max | Rust / standard sort | 5.761 | 33.3% | 11.4% |
| Mac M4 Max | Goose | 7.268 | 15.9% | -11.8% |
| Mac M4 Max | Current optimized C | 6.502 | 24.7% | 0.0% |
| Mac M4 Max | Rust / libc-sort control | 8.639 | -0.0% | -32.9% |
| Mac M4 Max | Rust / matched-sort control | 6.471 | 25.1% | 0.5% |
| Raspberry Pi 5 | Original C | 26.335 | 0.0% | -28.4% |
| Raspberry Pi 5 | Rust / standard sort | 18.095 | 31.3% | 11.8% |
| Raspberry Pi 5 | Goose | 19.936 | 24.3% | 2.8% |
| Raspberry Pi 5 | Current optimized C | 20.510 | 22.1% | 0.0% |
| Raspberry Pi 5 | Rust / libc-sort control | 24.969 | 5.2% | -21.7% |
| Raspberry Pi 5 | Rust / matched-sort control | 19.220 | 27.0% | 6.3% |

## Memory and code size

Whole standalone-process resident memory includes identical preallocated input/output buffers, tables and library/runtime pages. Virtual address reservation is not physical RAM. Executable size is disk code size, not resident RAM.

| Target | Implementation | Resident MiB | Extra virtual MiB vs original C | Executable KiB, debug stripped |
|---|---|---:|---:|---:|
| Mac | Original C | 19.281 | 0.00 | 34.3 |
| Mac | Current optimized C | 19.281 | -0.34 | 50.5 |
| Mac | Goose | 19.406 | 4097.67 | 51.8 |
| Mac | Rust / standard sort | 19.516 | 1.23 | 1400.4 |
| Mac | Rust / libc-sort control | 19.531 | 0.94 | 1399.9 |
| Mac | Rust / matched-sort control | 19.516 | 1.36 | 1399.9 |
| Pi | Original C | 19.609 | 0.00 | 70.4 |
| Pi | Current optimized C | 19.625 | 0.02 | 70.4 |
| Pi | Goose | 19.609 | 4097.91 | 72.8 |
| Pi | Rust / standard sort | 20.094 | 0.88 | 1579.7 |
| Pi | Rust / libc-sort control | 20.078 | 0.86 | 1579.1 |
| Pi | Rust / matched-sort control | 20.094 | 0.88 | 1579.8 |

Goose reserves roughly 4 GiB extra virtual address space for runtime stacks, mostly untouched. Rust has a larger executable because it includes parts of its standard runtime; code size and resident memory are shown separately. The table uses uniformly debug-stripped copies: prebuilt Rust standard-library debug sections survived staticlib compilation on Pi. Raw and stripped sizes/hashes are in mac-size.json and pi-size.json; the original binaries used for CPU/RSS were not modified. The several-megabyte sample buffers dominate this standalone RSS. Linux memory uses exec-local VmHWM/current RSS rather than launcher-inherited ru_maxrss; Mac uses Mach RSS/getrusage.

## What is actually one-to-one?

Every variant implements the ordinary 41-bin coherent decoder: the same preamble carrier search, phase unwrap, magnitude quantiles, weighted/refined phase fit, coherent bit scores, protected weak-bit selection and CRC repair. There are no changed DSP thresholds, no new retry hypotheses and no reduced-accuracy fast path. Common elementary libm operations preserve numerical comparability. The Rust port performs the full decoder computation itself and never calls a C decoder.

The common C input/output harness gives every implementation identical IQ bytes, order, batch size, preallocated output buffers and warmups. Safe Rust indexing checks remain in its hot loops. Rust FFI/raw-pointer conversion is confined to the ABI boundary and elementary math; the libc sorting control explicitly calls libc qsort. Goose standard bounds checks remain enabled.

The default sort differs by implementation: original C uses libc qsort; Goose uses its specialized typed standard sort; current C uses the Goose-derived C sort; Rust uses std sort_unstable_by. Therefore two diagnostic Rust variants are included: Rust-libc uses the same libc sort as original C, and Rust-matched ports the same typed-sort algorithm as current C/Goose. These controls distinguish sorting-library choices from the rest of the decoder.

## Interpreting the controls

On Mac, Rust with its standard sort saves 11.4% versus current C; the matched-sort Rust control saves 0.5% versus current C. Rust-libc saves -0.0% versus original C. These measurements suggest how much comes from library selection, but do not establish an intrinsic language-speed advantage.
On Pi, Rust with its standard sort saves 11.8% versus current C; the matched-sort Rust control saves 6.3% versus current C. Rust-libc saves 5.2% versus original C. These measurements suggest how much comes from library selection, but do not establish an intrinsic language-speed advantage.

Rust 1.99.1 is used on both systems, compiled at opt-level 3 with one codegen unit, panic=abort and no debug info. Goose v2026.3 emits standalone C. Original/current C and generated Goose C use the same target compiler with -O3 -std=c11 -ffp-contract=off. No variant enables fast-math or target-native specialization. Mac uses Apple Clang; Pi uses GCC; Rust uses its bundled LLVM. Compiler/backend differences remain a confounder, even with matching algorithm controls.

## Parity and limits

All six versions produced the same 262 CRC-valid window outputs and 2,582 tracked windows. Packet bytes, repairs, inlier counts, tracked/valid flags and hard-bit decisions match exactly, and all 32 deterministic noise controls are rejected. Floating diagnostics meet the declared rtol=1e-12, atol=1e-15 tolerance; maximum differences are retained in each JSON.

Mac, Rust / standard sort: largest absolute logit difference 1.73e-18; confidence 6.66e-15; carrier frequency 0 Hz.
Mac, Goose: largest absolute logit difference 1.73e-18; confidence 6.66e-15; carrier frequency 0 Hz.
Pi, Rust / standard sort: largest absolute logit difference 0; confidence 0; carrier frequency 0 Hz.
Pi, Goose: largest absolute logit difference 0; confidence 0; carrier frequency 0 Hz.

The Rust tests check a known CRC packet, initialization and invalid bounds. The matched sort also passes 200,000 ordered/reversed/duplicate/adversarial/random arrays. This is bounded implementation regression, not a new false-positive certification or a count of unique extra aircraft transmissions. The 42 RF files are previously consumed development captures; no new or reserved prospective RF was used.

No whole-pipeline CPU saving, wattage reduction or improvement in reception is claimed. This test times only ordinary coherent-window decoding; acquisition, shared FIR, pair retry, neural work and feeder transport are excluded. A working-pipeline change would need its own validation and deployment request.

## Receiver isolation

The Pi identifies as Raspberry Pi 5 Model B, not Pi 4. The official checksum-verified Rust compiler and standard library were extracted only into the owned tmpfs experiment tree. No system package installation occurred. Build and tests ran under nice 19, core 3, CPUQuota 35%, MemoryMax 1536 MiB and bounded runtime. Compiler memory is excluded from decoder measurements; elapsed time under quota is not a throughput measure.

Protected decoder, DSP, FR24, ADS-B Exchange, relay and capture PIDs, config hashes, gain and method switches match before/after. Sample-loss/drop counters did not increase. No services were restarted, no routing/model/capture settings changed, and no live SDR or mirror input was opened.

## Artifacts and reproduction

[Experiment source and instructions](../../experiments/rust-coherent/README.md) · [Rust decoder](../../experiments/rust-coherent/coherent.rs) · [Mac trials](mac.json) · [Pi trials](pi.json) · [Provenance](provenance.json) · [Receiver health](health-check.json) · [Input manifest](input-manifest.json). Private RF, generated binaries and temporary compiler files are excluded from Git.
