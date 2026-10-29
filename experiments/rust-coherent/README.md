# One-to-one coherent decoder comparison: C, Goose and Rust

Offline experiment only. No production code, model, configuration, routing,
service or collection change. All ports implement the same ordinary 41-bin
coherent-window kernel; pair retries, acquisition, FIR and neural processing are
outside the timed scope.

The full Rust port is `coherent.rs`. It implements the carrier search, phase
unwrap, robust weighted fit, coherent bit decisions, CRC syndrome search and
restricted bit repair. It never calls a C decoder. Elementary libm operations
are shared with C/Goose to control floating-point behavior. Standard safe Rust
slice indexing remains in the hot algorithm; unsafe code is limited to the C
ABI/pointers and elementary FFI (plus libc sorting in its attribution control).

## Variants

| Executable | Decoder | Quantile sort |
|---|---|---|
| c-old | Original C | Original libc qsort |
| c-current | Currently deployed C algorithm | Goose-derived typed C sort |
| goose | Previous full Goose port | Goose standard typed sort |
| rust | Full Rust port | Rust std sort_unstable_by |
| rust-libc | Same Rust port | Same libc qsort as original C |
| rust-matched | Same Rust port | Safe Rust adaptation of the same Goose-derived sort as current C |

The last two controls help distinguish compiler/language effects from sorting
library differences. The DSP decisions, thresholds and mathematical operation
order remain the same. Rust-matched source has the same Apache-2.0 attribution
as the C typed-sort adaptation; the full decoder port follows project GPL-3.0-or-later.

## Toolchains and inputs

Rust 1.99.1 is pinned on both platforms. Goose standalone generated C comes from
the pinned v2026.3 compiler used in the earlier experiment. Both C variants and
Goose are built by the same target `cc -O3 -std=c11 -ffp-contract=off`. Rust uses
`-C opt-level=3 -C codegen-units=1 -C panic=abort -C debuginfo=0
-C strip=debuginfo`, without fast-math or target-native specialization. Compiler
versions differ between languages; this is not a pure language-speed theorem.

The primary fixture is the exact previously consumed 3,269-window development
corpus from the coherent-sort experiment: 42 RF files, up to 96 chronological
eligible windows/file plus 32 seeded noise controls. Every implementation gets
the same bytes, ordering and batch size. No new or reserved evaluation RF is
consumed. Private input windows and compiler binaries are ignored under `.work/`.

## Reproduce on Mac

With project Python/NumPy and Rust 1.99.1 available:

```sh
mkdir -p experiments/rust-coherent/.work
cp /path/to/coherent-sort/windows.bin experiments/rust-coherent/.work/windows.bin
cp /path/to/pinned-goose-output/coherent.c /path/to/pinned-goose-output/coherent.h \
  experiments/rust-coherent/.work/
python experiments/rust-coherent/build.py --rustc /path/to/rustc-1.99.1
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python experiments/rust-coherent/benchmark.py \
  --output /tmp/rust-coherent-mac.json
```

See `../coherent-sort/prepare.py` to reconstruct the fixture from its original
private development RF; the published manifest includes hashes and offsets.
Goose C/header generation is documented in `../goose-coherent/README.md`.
The common C driver owns exactly the same preallocated input/output buffers for
every executable. It warms twice per process and excludes initialization and
I/O from CPU timing. Nine fresh-process trials rotate/reverse execution order.
Peak and current RSS include the entire executable; Linux uses exec-local
VmHWM, avoiding inherited launcher ru_maxrss. VM reservation is separate from
resident RAM. Compiler/Python memory is not inference memory.

All packet bytes, hard bits, flags, inlier counts and repairs must match.
Floating diagnostics use rtol=1e-12, atol=1e-15, equal NaNs. All 32 noise controls
must be rejected. The Rust-matched tests also check 200,000 bounded sorts.
This is finite regression parity, not an independent RF accuracy proof.

## Isolated Pi run

`pi_job.sh` uses the checksum-verified official Rust compiler and standard library
archives below the owned tmpfs job directory. No installer or system package
change is made. Archives are from `https://static.rust-lang.org/dist/`:

- rustc-1.99.1-aarch64-unknown-linux-gnu.tar.xz:
  `acdcdfe09ae1f103aa9a2b7f88903a9588bc2e99288af10e6fbf5514e2e49f25`
- rust-std-1.99.1-aarch64-unknown-linux-gnu.tar.xz:
  `e25668477083d6a9ddb87b9beb9c00742225f38233ccb4bfba3afa7a07427f52`

Stage the scripts, ports, common driver/parity helper, C kernel/header, emitted
Goose C/header and fixture in an isolated source tree. Run `pi_job.sh` under
nice 19, core 3, CPUQuota 35%, MemoryMax 1536 MiB and a 900-second runtime limit.
The memory ceiling covers temporary compiler/toolchain extraction as well as
tests; reported decoder RSS comes only from the child executables. Wall time
under CPU quota is not decoder throughput. Snapshot protected service PIDs,
configuration hashes and sample-loss counters before and after; never restart
or install any service. Remove only the owned tmpfs tree after verifying local
backups and the final result checksum.
