# Coherent decoder: handwritten C versus Goose

Completed 2026-10-29. No deployed code, configuration, services or RF collection changed.

## Selection and implementation

Coherent decoding was the largest **attributed active C decoder branch** in the receiver statistics (about 14.4% of one core versus 4.0% for energy slicing). Shared frontend costs were not attributed to individual C functions, so this is not proof that it is the single largest C cost in the whole system. See [selection profile](selection-profile.json).

We ported the ordinary bounded coherent-window kernel: 41-bin carrier search, robust phase fit, coherent decisions and protected CRC repair. This experiment excludes shared FIR, acquisition, pair retries, neural inference and feeder transport. The Goose port does its own decoder work, with only elementary libm calls shared.

[Goose v2026.3](https://github.com/aardappel/goose/releases/tag/v2026.3) generates C. Both implementations therefore use the same target C compiler and `-O3 -std=c11 -ffp-contract=off`, without fast-math. Goose inlining is enabled; normal bounds checking is retained. This compares these two implementations/toolchains, not an intrinsic advantage of one language.

## CPU and memory

Median of seven fresh-process trials. CPU is microseconds per 120-microsecond RF window presented to the kernel, not CPU per second of continuous RF. Resident memory includes the entire standalone process and identical input/output buffers.

| Hardware | Implementation | CPU µs/window | CPU saving vs C | Resident MiB | Executable KiB |
|---|---|---:|---:|---:|---:|
| Mac M4 Max | C reference | 8.289 | — | 7.266 | 34.3 |
| Mac M4 Max | Goose | 6.849 | 17.4% | 7.391 | 51.8 |
| Mac M4 Max | C + Goose typed-sort control | 6.182 | 25.4% | 7.469 | 68.4 |
| Raspberry Pi 5 | C reference | 26.156 | — | 7.547 | 70.7 |
| Raspberry Pi 5 | Goose | 19.795 | 24.3% | 7.625 | 73.1 |
| Raspberry Pi 5 | C + Goose typed-sort control | 20.325 | 22.3% | 7.750 | 73.8 |

The target identifies as **Raspberry Pi 5 Model B Rev 1.0**, not Pi 4. Mac: Apple M4 Max, 64 GiB. Pi uses GCC 12.2; Mac uses Apple Clang. No Pi 4 performance claim is made. Raw trial values, compiler identities, flags and platform strings are in [Mac JSON](mac.json) and [Pi JSON](pi.json).

Goose reserves about **4 GiB more virtual address space** for its runtime stacks; this is not 4 GiB of resident RAM. On the Pi the C process reserves about 8.7 MiB virtual versus about 4,106.7 MiB for Goose. Touched resident memory is slightly higher with Goose. macOS has a much larger baseline virtual mapping, so compare the virtual-memory delta rather than absolute values across operating systems.

A preliminary Linux measurement used `getrusage().ru_maxrss`, which inherited a roughly 37.7 MiB launcher high-water mark. Those preliminary results were discarded. Published measurements were rerun with exec-local `/proc/self/status` VmHWM plus current RSS; Mac retains Mach RSS/getrusage. Very small differences between peak and later current samples can arise because instrumentation/output touches additional pages.

## What accounts for the speedup?

The diagnostic hybrid keeps the C algorithm and replaces only double-array quantile `qsort` calls with the same specialized Goose sort. It saves 22.3% on Pi versus 24.3% for the full port, and is faster than the full port on Mac. Thus most of the measured benefit can be obtained from sorting/library specialization. This control still links the Goose runtime and is not a proposed pure-C replacement or memory optimization.

The next practical optimization is an equivalent typed C sort or exact quantile selection, followed by parity and representative replay tests. These results do not justify rewriting the working pipeline in Goose. They also do not imply a 24% whole-pipeline CPU saving.

## Output checks and limits

The fixture contains 1,024 real candidate windows from previously consumed shared-feedback RF plus 32 seeded noise controls: 65 energy-valid control windows and 959 failed-energy windows. Selection was chronological, not chosen for language performance. Windows may overlap and are not unique transmissions. The [manifest](input-manifest.json) records source hashes and offsets; private RF and packet payloads are not published.

All three implementations produced the same 78 CRC-valid window outputs, 823 tracked windows, packet bytes, hard bits, repair choices and integer flags. On Pi all floating outputs also matched exactly. On Mac the largest floating difference was below 1e-15 and changed no bit decision. All 32 noise windows were rejected. This is finite implementation parity, not evidence of additional packets beyond stock, an independent accuracy evaluation, or a general false-positive bound.

The kernel excludes initialization and I/O from CPU timing, warms twice and rotates/reverses variant order. Pi execution was isolated in owned tmpfs with nice 19, core 3, CPUQuota 35%, MemoryMax 1 GiB and bounded runtime. CPU quota makes elapsed time unsuitable as a throughput measure. Protected receiver/feeder/capture PIDs and active states were identical before and after, with zero sample-loss/drop counters. No live mirror or SDR input was opened.

## Reproduction

See [experiment instructions](../../experiments/goose-coherent/README.md), [Goose source](../../experiments/goose-coherent/coherent.goose), [harness](../../experiments/goose-coherent/driver.c) and [provenance](provenance.json). Generated compiler output, binaries, private RF and scratch files are excluded. The corpus is a bounded development fixture; benchmark broader representative RF before considering a production change.
