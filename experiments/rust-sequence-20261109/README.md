# Rust pulse-sequence benchmark — November 9–10, 2026

User authorized a Rust pulse-sequence port and comparison against optimized C.
Production pulse sequence stays unchanged. The separately authorized Rust
Stream1090 binary activation is documented in the neighboring activation folder.
All sequence tests run after that activation with the new Stream ELF fingerprint
included in protected state; no sequence test restarts or changes a live service.

`sequence.rs` ports the optimized-v3 prepared-template gain, repeated interior
pulse templates, four-state forward/backward sequence detection, traceback,
soft confidences and bounded CRC repair. Generic non-repeated templates retain
the original mathematical fallback. Existing Rust complex/libm, noise, carrier
seed and CRC helpers are included directly; no C decoder is called. Elementary
math uses platform libm, without fast math or fused multiply-add changes.

`prepare.py` extracts 3,840 chronological candidate windows: the first 160 per
frozen RF second across 24 previously consumed historical RF seconds, preserving
496-sample halo context and carrier seeds. This is a CPU/parity fixture, not
training data. A first pilot from four RF seconds is preserved separately; final
sampling was spread across all cases before target timing, never selected by
candidate success. Live nine-tap pulse model values were verified equal.

`build.py` builds the Rust library and optimized current C source with O3 and
FP contraction off. The target also copies the exact live `_pipeline_v3.so` as
an independent third reference. The live library's `sf_noise` calls libc qsort;
current optimized C source uses the validated typed finite sort, with qsort only
for nonfinite fallback. Saved objdump evidence distinguishes them. Do not credit
that existing C optimization to the Rust port. Rust uses its existing validated
sort_unstable noise quantile helper.

`benchmark.py` checks bit-exact logits, confidences, packet rows, repair bits,
validity flags and return codes; 35 prepared pulse models, non-repeated-template
fallback, supplied/NaN carrier seeds, zero/noise/frequency controls, 128 complex
phase/amplitude/timing perturbations and invalid count/start/empty bounds.
Nine counterbalanced trials, six repetitions per mode, include identical Python
allocation and FFI overhead; initialization and two warmups are excluded. Valid
window outputs are not automatically unique extras beyond the full pipeline.

`overlay.py` modifies only an isolated copied loader to use Rust prepare/batch.
The initial `full_replay.py` passes compare 24 RF seconds with exact-live C,
rebuilt optimized C and Rust, preserving every raw/guarded event, stock alignment
and admission decision. All current native/neural/pulse/coherent/acquisition
methods and original-first guards are included. Stream1090 is a separate child;
its identical frozen output from the prior benchmark preserves the same union.
One sequential pass per mode is insufficient for precise whole-pipeline CPU:
unmodified neural/energy stages also varied materially between passes.

`patch_paired.py` / `paired.py` resolve that timing confound. Only a copied ring
gets a shared selector; coherent workers load optimized C and Rust once. The
coordinator changes sequence batch ABI only when the complete RF second has
finished and all leases/tasks are quiescent. Both modes use identical prepared
templates and every other optimized-C/native/Rust library, all within one
persistent four-worker pool. Two warm RF seconds precede two counterbalanced
passes through all 24 cases per mode. Every raw event, accepted event, alignment
and decision is checked against the frozen reference on every invocation.

Target jobs are nice19, core3, 35% quota, finite runtime. MemoryMax1G is requested;
this kernel lacks a usable memory controller, so a separate conservative summed
child RSS threshold below 1 GiB is checked every three seconds. The same checks
protect all live PIDs, model/library/config/Stream ELF hashes, gain, switches,
sample-loss counters, feeder/collector health and processing margin. Only the
owned benchmark may abort. No SDR, mirror access, packet injection, flush, live
sequence change or persistent archive deletion.

`finalize.py` and `finalize_paired.py` assert closed-run results. `fetch.py` saves
complete source/toolchain/RF/library/model/output/log evidence with streamed
SHA-256 verification and fsync on the Mac. `cleanup.py` rechecks exact unchanged
owned file/symlink identities before deleting only this closed tmpfs root.
Reports publish aggregate results only; raw RF and models remain private.

The RF corpus has only ten >=180 nm stock opportunities from three aircraft.
These checks establish regression parity, not prospective far-range improvement.
No candidate output or unverified prediction becomes a label or FR24 input.
Date-fixed scripts are reproducibility records; inspect current state before reuse.

The initial paired harness rejected tuple-valued repair metadata when comparing
fresh Python objects with JSON-loaded list metadata. Its saved diagnostic records
were exactly equal after serialization, including order and multiplicity. V2
normalizes fresh witnesses through the identical JSON output contract; it does
not sort, drop fields, loosen numeric comparison or bypass packet assertions.
The failed original and short diagnostic are preserved separately. Only the V2
closed/supervised run supplies paired timing evidence.
