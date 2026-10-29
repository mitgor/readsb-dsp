# Coherent decoder: C versus Goose

An isolated language/code-generation experiment, not a production replacement.
Results and limitations: [2026-10-29 report](../../validation/goose-coherent-20261029/report.md).

The bounded coherent-window algorithm in `src/rescue/coherent_kernel.c` is ported
in full to `coherent.goose`: 41-bin preamble carrier search, robust pulse-phase
fit, coherent bit decisions and protected weak-bit CRC repair. Goose invokes
libm for elementary math but never calls the C decoder. This tests the ordinary
kernel, not candidate acquisition, pair retries, FIR, the neural model or the
complete live pipeline.

## Pinned toolchain

Use [Goose v2026.3](https://github.com/aardappel/goose/releases/tag/v2026.3),
commit `acc6310a83df7a322d3f8264a808f675348c4260`. For macOS ARM64 download
`goose-v2026.3-macos-arm64.tar.gz` from that release and verify SHA-256:

```
2ffaaf46b3edde27aed03fcd9ebe73e9b6639cac30d8a6915f7dc00795b7aedf
```

Extract the complete archive (including stdlib) below `.work/compiler/`.
Goose emits standalone C; the same target C compiler builds both implementations
with `-O3 -std=c11 -ffp-contract=off`, no fast-math. Goose's `-O2` enables its
inlining pass. Standard runtime checks remain enabled. Compiler execution and
initialization are outside timed decoding. No system-wide Goose installation
is required; `GOOSE_HOME` stays inside `.work/`.

## Reproduce

From the repository root, with a Python environment containing project
dependencies and NumPy:

```sh
python experiments/goose-coherent/prepare.py \
  --input /path/to/already-consumed/shared-feedback-20261028 \
  --output experiments/goose-coherent/.work/windows.bin
python experiments/goose-coherent/build.py \
  --goose experiments/goose-coherent/.work/compiler/goose-v2026.3-macos-arm64/goose
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  python experiments/goose-coherent/benchmark.py --output /tmp/goose-mac.json
```

Private RF is deliberately excluded from the repository. The input manifest
records source hashes, offsets and fixture SHA-256 so an owner of those captures
can reconstruct the input. With other RF this is a new comparison, not a
reproduction of the published numbers. No live SDR access is used.

For a Linux ARM target, copy this experiment's scripts, C driver, sort control,
`src/rescue/coherent_kernel.c`, and generated `.work/coherent.c`, `coherent.h`,
`windows.bin` into an isolated tree. Run `build.py` there without `--goose`, then
`benchmark.py --output /tmp/goose-pi.json` with NumPy installed. Run at low
priority with a bounded CPU/memory budget. Do not install any of these binaries
as a service or change receiver routing.

Each executable preallocates identical input/output buffers, initializes its
own tables, warms twice and then decodes the same windows repeatedly. Seven
fresh-process trials rotate/reverse variant order. CPU time measures kernel
work only; wall time is retained but not treated as throughput under CPU quota.
Memory includes buffers, libraries and the language runtime. Linux peak memory
uses exec-local `VmHWM`, avoiding inherited launcher `ru_maxrss`; current RSS
is also sampled. macOS uses `getrusage` and Mach resident/virtual memory.

`c-sort` is a diagnostic hybrid: the C decoder delegates double-array quantile
sorting to Goose's typed sort; pattern sorting and all other decoder work stay
in C. Its Goose runtime means it is not a pure-C memory comparison. It helps
separate library specialization from a language-wide advantage.

Parity checks cover packet bytes, hard bits, valid/tracked flags, inlier counts,
repair choices and floating scores (rtol 1e-12, atol 1e-15). The final 32 seeded
noise windows must produce zero accepted packets. This is a finite regression
check, not a general false-acceptance or accuracy certification.

All experiment-owned generated code, RF windows, executables and scratch output
stay in ignored `.work/`. Original project GPL-3.0-or-later licensing applies to
the port; Goose compiler/runtime licensing is in its release archive.
