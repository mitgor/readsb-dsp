# Rust pulse-sequence comparison — November 9–10, 2026

Production sequence remains on C. Rust Stream1090 was activated separately with rollback; that is the only authorized production change in this task. All sequence work was isolated and began after Stream activation, with its new ELF included in protected fingerprints.

## Sequence batch benchmark

The Rust port covers prepared pulse templates, gain, optimized repeated-template four-state forward/backward sequence detection, traceback, confidences, carrier fallback and bounded CRC repair. The generic non-repeated-template fallback is retained. No C decoder is called; existing validated Rust helpers and platform libm are reused, without fast math or altered decisions.

Target is the current **Pi 5 / Cortex-A76**, not a Pi 4. Nine counterbalanced trials with six repetitions per mode use 3,840 chronological halo-preserving candidate windows, spread over 24 historical RF seconds. Median CPU seconds per 3,840-window batch:

| Implementation | CPU seconds | Microseconds / window |
|---|---:|---:|
| Exact live optimized-v3 C library | 0.158926 | 41.39 |
| Rebuilt current optimized C | 0.140540 | 36.60 |
| Rust pulse-sequence port | 0.111003 | 28.91 |

Rust reduces sequence batch CPU by **20.51% versus rebuilt optimized C**, and 29.91% versus the exact live C library. The live library still calls libc qsort for its noise quantile; rebuilt C already uses the validated typed finite sort. Saved disassembly distinguishes them. Rust uses its existing sort_unstable quantile helper. This is an implementation comparison, not proof that a language alone causes the difference. Mac batch saving was 13.57%.

Timing includes identical Python allocation/FFI overhead, with initialization/two warmups excluded. This batch is only part of dashboard sequence CPU, which also includes shared screening and carrier fitting.

## Parity and controls

Every logit, confidence, row byte, repair bit, validity flag and return code matched **bit-exactly** across Rust, optimized C and the exact live C library. Tests cover 35 pulse models, 3,840 recorded windows, finite/NaN carrier seeds, generic-template fallback, invalid bounds/empty batches and 128 phase/amplitude/fractional-timing perturbations. Zero/DC and 64 noise windows yield zero valid packets. The 36 valid recorded-window outputs are not 36 new unique transmissions beyond the pipeline.

Complete current native pipeline replays, including all enabled neural/DSP branches and original-first stock/address/alignment/admission guards, matched all raw candidates, guarded packets and decisions across all three implementations. Native extras remain **369**, with no added or lost packet. Combining the unchanged, previously byte-validated Stream output preserves the same **403-extra** frozen corpus union.

## Complete worker CPU: much smaller, uncertain benefit

Initial one-pass native-worker timings, retained for audit:

| Sequence library | CPU seconds / RF second |
|---|---:|
| actual_C | 0.611256 |
| optimized_C | 0.566257 |
| Rust | 0.603934 |

Those sequential passes also showed material variation in unchanged neural/energy stages, so they do not establish a whole-pipeline speedup.

A second comparison keeps the **same four persistent workers**, all other libraries, templates and RF fixed. Only the sequence batch ABI switches between optimized C and Rust, at a quiescent complete-RF boundary. Two warm RF seconds precede 48 timed RF seconds per mode, counterbalanced by case and repeat. Every raw/guarded event, stock alignment and admission decision is checked against the frozen serialized output contract on every invocation.

| Paired mode | Complete native-worker CPU / RF second |
|---|---:|
| Optimized C sequence | 0.573104 |
| Rust sequence | 0.570346 |

Observed complete-worker reduction: **0.48%**. A descriptive 95% bootstrap interval, clustered by the 24 RF cases with both repeats, is **-0.34% to 1.24%**. It overlaps zero: **a complete-worker CPU improvement is not established**. Stream child, capture, relay and coordinator CPU are outside this native-worker measure; this is not whole-Pi CPU, watts or prospective RF evidence.

## Distance, safety and artifacts

The prior causal-stock range annotation has 10 >=180 nm stock opportunities from three aircraft, with 13 native extras and one Stream-only extra beyond180 nm. Exact output parity preserves these counts. Coverage is too small to claim general far-range robustness or improved range. All RF was already consumed evaluation data; no candidate output becomes a training label or FR24 input.

Measured runs were nice19/core3/CPUQuota35%, finite, supervised against service PIDs, source/library/model/config/Stream ELF hashes, gain, methods, SDR loss, feeder/collector health and a processing safety margin. A conservative summed-child RSS threshold below 1 GiB was monitored independently because this kernel lacks a usable memory controller. Highest recorded supervised RSS: 976.2 MiB. Per-kernel resident memory was not independently attributed; unstripped candidate ELF size is 4,687,664 bytes versus 71,416 for rebuilt C, including Rust runtime/debug content, not a resident-RAM measure.

No live sequence library/config/model change, receiver/feeder/collector restart, SDR/mirror access, packet injection, recorder flush or persistent archive deletion. RF collection cap remains 5,000,000,000 bytes. Full source, compiler, RF, libraries, model copies, results, controls, logs and failed-harness diagnostic are SHA-256 verified and fsynced on Mac before exact owned tmpfs cleanup. Early paired failure was tuple/list metadata representation, with identical serialized records; the corrected gate retains every value, duplicate and ordering check.

**Decision:** retain C sequence in production. The Rust port is ready for further targeted optimization, but its isolated batch saving has not yet translated into a demonstrated complete-worker saving.
