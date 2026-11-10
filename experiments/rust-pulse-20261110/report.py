"""Aggregate pulse parity/CPU evidence, without raw RF or credentials."""
from pathlib import Path
import json,html
D=Path('/Users/mit/Documents/!project/adsb-neural-rescue/results/rust-pulse-20261110');O=Path(__file__).resolve().parents[2]/'validation/rust-pulse-20261110';O.mkdir(parents=True,exist_ok=True);p=json.loads((D/'proof.json').read_text());assert p['parity_passed'];summary={**p,'receipt':json.loads((D/'target-receipt.json').read_text()),'hardware':'Pi5 / Cortex-A76; no Pi4 cost claim.'};(O/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
rows='\n'.join(f'| {name} | {value:.8f} |' for name,value in p['median_cpu_s'].items());text=f'''# Rust pulse-discriminant validation — November 10, 2026

Ported the frozen eight-tap pulse discriminant and 1–8-model bank to Rust. Candidate selection, model weights/bias, ordered FP64 accumulation, FP32 outputs, normalization, partial-write/error behavior and unchanged CRC/header/address guards are retained. No new bank, model or algorithm is enabled by this port.

On the current Pi5/Cortex-A76, all logits/confidences are bit-exact against both rebuilt C and the exact live C library. Rebuilt/live C ELFs have identical SHA-256. Validation covers {p['windows']:,} chronological historical power windows spread across24 RF seconds, {p['numeric_and_error_controls']} numerical/error/bounds/partial-write controls and {p['bank_controls']} model-bank controls. Cases include zero/subnormal/large power, overflow, random weights, invalid preamble/late bit inputs, nonfinite model values and empty batches. Bank results also match independent scalar calls. The unchanged packet logic yields identical signatures for {p['packet_window_outputs']} valid window outputs; these are not unique full-pipeline additions.

Nine counterbalanced target trials, 50 calls per mode, measure CPU seconds per {p['windows']:,}-window batch, including identical Python allocation/FFI overhead:

| Library | Median CPU seconds |
|---|---:|
{rows}

Rust costs **{p['median_CPU_change_vs_actual_C_percent']:.2f}% more pulse-batch CPU** versus actual C ({p['median_CPU_change_vs_C_percent']:.2f}% versus rebuilt C paired trials). Mac was approximately neutral. This is **not a CPU-saving result**. The pulse batch is a small component; no whole-Pi/energy claim follows.

Complete current native pipeline replay over24 RF seconds, including already active Rust sequence/coherent/acquisition and enabled neural/DSP branches, matches every raw candidate, accepted packet, alignment audit and admission decision. The {p['full_native_extras']} native extras and prior403-extra native+unchanged-Stream union are preserved, with zero added or lost packets. Native-worker CPU was {p['full_worker_CPU_per_RF_second']['C']:.6f} seconds/RF-second for C and {p['full_worker_CPU_per_RF_second']['Rust']:.6f} for Rust in one sequential pass each; these are descriptive and insufficient for a precise overall cost claim.

RF is already-consumed historical regression data, not fresh prospective validation. Only ten >=180nm stock opportunities from three aircraft exist; no range-improvement or training-label claim. Experimental outputs stay quarantined.

Target work ran nice19/core3/CPUQuota35%, finite, with protected receiver/feeder/collector/Stream/source/model/config/gain/switch/loss fingerprints unchanged. A conservative summed-child RSS bound below1GiB was independently monitored because the kernel lacks an effective memory controller. Maximum recorded test RSS: {p['max_test_RSS_MiB']:.1f}MiB. No SDR/mirror access, candidate injection, service restart, forced flush or persistent archive deletion during validation.

Full source, temporary compiler, original/port libraries, model/RF inputs, controls, outputs and journals were checksum-verified and fsynced on Mac before exact owned tmpfs cleanup. Deployment is separately documented under pulse-rust-activation-20261110. Activation follows the user's explicit request if parity and live stability pass, not a claim of greater efficiency.
''';(O/'report.md').write_text(text);(O/'report.html').write_text('<!doctype html><meta charset="utf-8"><title>Rust pulse validation</title><style>body{max-width:1000px;margin:40px auto;padding:20px;background:#101b29;color:#dfebf7;font:16px/1.6 system-ui}pre{white-space:pre-wrap}</style><pre>'+html.escape(text)+'</pre>')
