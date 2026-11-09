"""Redacted kernel and full-pipeline evidence; no production sequence activation."""
from pathlib import Path
import json,html,statistics
D=Path('/Users/mit/Documents/!project/adsb-neural-rescue/results/rust-sequence-20261109');O=Path(__file__).resolve().parents[2]/'validation/rust-sequence-20261109';O.mkdir(parents=True,exist_ok=True);p=json.loads((D/'proof.json').read_text());m=json.loads((D/'mac-spread/benchmark.json').read_text());b=p['paired_full_pipeline'];assert p['parity_passed'] and b['all_raw_and_guarded_events_exact'];summary={**p,'mac_sequence_CPU_reduction_percent':m['median_saving_percent'],'target_receipt':json.loads((D/'target-receipt.json').read_text()),'decision':'Production sequence remains C. Rust kernel is faster in isolation; complete worker CPU improvement not established by paired interval.','hardware':'Pi 5 / Cortex-A76; no Pi 4 performance claim.'};(O/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
rows='\n'.join(f'| {label} | {p["kernel_median_cpu_s"][key]:.6f} | {p["kernel_median_cpu_s"][key]/p["windows"]*1e6:.2f} |' for key,label in [('actual','Exact live optimized-v3 C library'),('c','Rebuilt current optimized C'),('rust','Rust pulse-sequence port')])
full='\n'.join(f'| {mode} | {cpu:.6f} |' for mode,cpu in p['full_native_worker_CPU_per_RF_second'].items())
ci=b['cluster_bootstrap_95_percent_interval'];text=f'''# Rust pulse-sequence comparison — November 9–10, 2026

Production sequence remains on C. Rust Stream1090 was activated separately with rollback; that is the only authorized production change in this task. All sequence work was isolated and began after Stream activation, with its new ELF included in protected fingerprints.

## Sequence batch benchmark

The Rust port covers prepared pulse templates, gain, optimized repeated-template four-state forward/backward sequence detection, traceback, confidences, carrier fallback and bounded CRC repair. The generic non-repeated-template fallback is retained. No C decoder is called; existing validated Rust helpers and platform libm are reused, without fast math or altered decisions.

Target is the current **Pi 5 / Cortex-A76**, not a Pi 4. Nine counterbalanced trials with six repetitions per mode use 3,840 chronological halo-preserving candidate windows, spread over 24 historical RF seconds. Median CPU seconds per 3,840-window batch:

| Implementation | CPU seconds | Microseconds / window |
|---|---:|---:|
{rows}

Rust reduces sequence batch CPU by **{p['kernel_saving_vs_optimized_C_percent']:.2f}% versus rebuilt optimized C**, and {p['kernel_saving_vs_actual_C_percent']:.2f}% versus the exact live C library. The live library still calls libc qsort for its noise quantile; rebuilt C already uses the validated typed finite sort. Saved disassembly distinguishes them. Rust uses its existing sort_unstable quantile helper. This is an implementation comparison, not proof that a language alone causes the difference. Mac batch saving was {m['median_saving_percent']:.2f}%.

Timing includes identical Python allocation/FFI overhead, with initialization/two warmups excluded. This batch is only part of dashboard sequence CPU, which also includes shared screening and carrier fitting.

## Parity and controls

Every logit, confidence, row byte, repair bit, validity flag and return code matched **bit-exactly** across Rust, optimized C and the exact live C library. Tests cover 35 pulse models, 3,840 recorded windows, finite/NaN carrier seeds, generic-template fallback, invalid bounds/empty batches and 128 phase/amplitude/fractional-timing perturbations. Zero/DC and 64 noise windows yield zero valid packets. The 36 valid recorded-window outputs are not 36 new unique transmissions beyond the pipeline.

Complete current native pipeline replays, including all enabled neural/DSP branches and original-first stock/address/alignment/admission guards, matched all raw candidates, guarded packets and decisions across all three implementations. Native extras remain **369**, with no added or lost packet. Combining the unchanged, previously byte-validated Stream output preserves the same **403-extra** frozen corpus union.

## Complete worker CPU: much smaller, uncertain benefit

Initial one-pass native-worker timings, retained for audit:

| Sequence library | CPU seconds / RF second |
|---|---:|
{full}

Those sequential passes also showed material variation in unchanged neural/energy stages, so they do not establish a whole-pipeline speedup.

A second comparison keeps the **same four persistent workers**, all other libraries, templates and RF fixed. Only the sequence batch ABI switches between optimized C and Rust, at a quiescent complete-RF boundary. Two warm RF seconds precede 48 timed RF seconds per mode, counterbalanced by case and repeat. Every raw/guarded event, stock alignment and admission decision is checked against the frozen serialized output contract on every invocation.

| Paired mode | Complete native-worker CPU / RF second |
|---|---:|
| Optimized C sequence | {b['worker_CPU_per_RF_second']['optimized_C']:.6f} |
| Rust sequence | {b['worker_CPU_per_RF_second']['rust']:.6f} |

Observed complete-worker reduction: **{b['worker_CPU_reduction_percent']:.2f}%**. A descriptive 95% bootstrap interval, clustered by the 24 RF cases with both repeats, is **{ci[0]:.2f}% to {ci[1]:.2f}%**. It overlaps zero: **a complete-worker CPU improvement is not established**. Stream child, capture, relay and coordinator CPU are outside this native-worker measure; this is not whole-Pi CPU, watts or prospective RF evidence.

## Distance, safety and artifacts

The prior causal-stock range annotation has 10 >=180 nm stock opportunities from three aircraft, with 13 native extras and one Stream-only extra beyond180 nm. Exact output parity preserves these counts. Coverage is too small to claim general far-range robustness or improved range. All RF was already consumed evaluation data; no candidate output becomes a training label or FR24 input.

Measured runs were nice19/core3/CPUQuota35%, finite, supervised against service PIDs, source/library/model/config/Stream ELF hashes, gain, methods, SDR loss, feeder/collector health and a processing safety margin. A conservative summed-child RSS threshold below 1 GiB was monitored independently because this kernel lacks a usable memory controller. Highest recorded supervised RSS: {p['max_recorded_RSS_MiB']:.1f} MiB. Per-kernel resident memory was not independently attributed; unstripped candidate ELF size is {p['library_sizes']['rust']:,} bytes versus {p['library_sizes']['c']:,} for rebuilt C, including Rust runtime/debug content, not a resident-RAM measure.

No live sequence library/config/model change, receiver/feeder/collector restart, SDR/mirror access, packet injection, recorder flush or persistent archive deletion. RF collection cap remains 5,000,000,000 bytes. Full source, compiler, RF, libraries, model copies, results, controls, logs and failed-harness diagnostic are SHA-256 verified and fsynced on Mac before exact owned tmpfs cleanup. Early paired failure was tuple/list metadata representation, with identical serialized records; the corrected gate retains every value, duplicate and ordering check.

**Decision:** retain C sequence in production. The Rust port is ready for further targeted optimization, but its isolated batch saving has not yet translated into a demonstrated complete-worker saving.
'''
(O/'report.md').write_text(text);(O/'report.html').write_text('<!doctype html><meta charset="utf-8"><title>Rust sequence comparison</title><style>body{max-width:1050px;margin:40px auto;padding:20px;background:#101b29;color:#dfebf7;font:16px/1.6 system-ui}pre{white-space:pre-wrap}</style><pre>'+html.escape(text)+'</pre>');print(json.dumps(dict(kernel_saving=p['kernel_saving_vs_optimized_C_percent'],paired_worker_saving=b['worker_CPU_reduction_percent'],interval=ci,production_sequence='C'),indent=2))
