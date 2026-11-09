"""Publish only aggregate parity/cost evidence; retain private RF/provenance."""
from pathlib import Path
import json,statistics,html
D=Path('/Users/mit/Documents/!project/adsb-neural-rescue/results/rust-stream-20261109');O=Path(__file__).resolve().parents[2]/'validation/rust-stream-20261109';O.mkdir(parents=True,exist_ok=True)
p=json.loads((D/'pi-final.json').read_text());t=json.loads((D/'pi-production-timing.json').read_text());m=json.loads((D/'mac-final.json').read_text());live=json.loads((D/'live-cpu-comparison.json').read_text());h=json.loads((D/'protected-complete.private.json').read_text());prior=json.loads((D/'protected-final.private.json').read_text());ht=json.loads((D/'protected-complete.private.json').read_text());old=json.loads((D.parent/'stream-windows-20261109/pi-comparison-final.json').read_text())['variants']['1000-strict']
for check in [h,ht]:assert check['error'] is None and check['before']==check['after']
assert p['exact_full_output'] and t['all_raw_output_exact'] and p['state_parity']['all_registers_crc_df_masks_exact'] and p['state_parity']['state_updates']==1200000
assert len(p['cases'])==24 and len(t['trials'])==7
assert all(len(set(x['sha256'] for x in c['modes'].values()))==1 for c in p['cases'])
assert p['binary_hashes']==t['binary_sha256']
summary=dict(production_changed=False,hardware='Current receiver: Raspberry Pi 5 / Cortex-A76; not Pi 4',live_core_percent=live['core_percent'],live_interval_s=live['wall_s'],port_scope='Stream1090 eight-stream shift-register/CRC update kernel only; surrounding decoder remains C++',state_parity=p['state_parity'],RF_seconds=24,raw_output_byte_exact=True,controls=p['controls'],pi_CPU=t,pi_kernel_saving_percent=p['median_kernel_cpu_saving_percent'],pi_decoder_RSS=p['isolated_decoder_rss'],mac_CPU_saving_percent=m['median_cpu_saving_percent'],protected_unchanged=True,max_owned_test_RSS_MiB=max(x['rss_kib'] for x in h['checks']+ht['checks']+prior['checks'])/1024,corpus_preserved_extras=dict(full_union=old['full_pipeline_extras'],stream_incremental=old['stream_incremental_extras'],distance_bins=old['bins'],lost=0,added=0),target_receipt=json.loads((D/'target-receipt.json').read_text()),limits=['Historical regression corpus; ten distant stock packets from three aircraft, one distant Stream-only extra. No fresh range-improvement claim.','Exact raw output means the prior full-pipeline corpus union is preserved; this task did not replay every unrelated producer again.','Live CPU attribution is exclusive and excludes shared frontend overhead; kernel savings are not whole-Pi savings.','Peak RSS samples are three full decoder invocations per binary through the small C launcher; raw wait4 spawn RSS retained privately.'])
(O/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
rows='\n'.join(f'| {label} | {live["core_percent"][key]:.2f}% |' for key,label in [('stream1090','Stream1090'),('sequence','Pulse sequence'),('pulse','C pulse discriminant filter')])
cpu='\n'.join(f'| {label} | {t["median_CPU_s"][key]:.4f} | {t["median_CPU_s"][key]/24:.5f} | {p["isolated_decoder_rss"][key]["max_kib"]/1024:.2f} |' for key,label in [('original','Actual production C++ ELF'),('c','Rebuilt C++ control'),('rust','Rust kernel + unchanged C++ decoder')])
text=f'''# Stream1090 Rust kernel comparison — 9 November 2026

Production remains unchanged. Stream1090 was the most CPU-expensive of the three requested methods in a simultaneous {live['wall_s']:.1f}-second live sample:

| Method | CPU as % of one core |
|---|---:|
{rows}

These are exclusive attributed method costs, including the Stream child, excluding shared frontend/coordination. They are not whole-system percentages or an ablation. The current physical receiver is a Pi 5 (Cortex-A76), not a Pi 4.

## Port and parity

Ported the eight-stream `ShiftRegisters::shiftInNewBits` frame-shift/56-bit-CRC/112-bit-CRC/handled-format-mask recurrence from Stream1090 C++ to Rust 1.99.1, with explicit ARM NEON. This is a kernel substitution, not a rewrite of the complete Stream1090 decoder. Filtering, resampling, trust/cache, repairs, timestamps and output logic remain C++. No live library or binary was replaced.

- 1,200,000 update steps: every register, both CRC arrays and handled-format mask bit-exact across zero, one, alternating, random and seeded-extreme states.
- 24 historical RF seconds: byte-for-byte complete output parity between the actual production binary, rebuilt C++ and Rust candidate. Payloads, timestamps, RSSI and ordering agree.
- DC, clipping and deterministic RF-noise controls match exactly; no relaxed CRC, trust or guard settings.
- Five alternating C++/Rust whole-decoder trials, seven additional counterbalanced production/C++/Rust trials, and seven ABI-matched kernel trials. Every timed output rechecked.

## Pi performance

Median child CPU seconds per 24 RF seconds; isolated decoder RSS is the maximum of three separate measurements per binary:

| Binary | CPU seconds | CPU seconds / RF second | Peak RSS MiB |
|---|---:|---:|---:|
{cpu}

Rust uses **{t['median_rust_saving_vs_production_percent']:.2f}% less CPU versus the actual production Stream1090 binary**, and {t['median_rust_saving_vs_control_percent']:.2f}% less versus the rebuilt C++ control (median paired trial reductions). The standalone update kernel saves {p['median_kernel_cpu_saving_percent']:.2f}% in ABI-matched microbenchmarks, including identical deterministic bit-generation overhead. End-to-end measurements include FFI calls, process startup and all unchanged C++ stages. Mac whole-Stream reduction was {m['median_cpu_saving_percent']:.2f}% and does not substitute for target evidence. Timing variance and raw trials are retained in summary.json.

RSS excludes the inherited Python launch high-water, which inflated raw Linux wait4 RSS; the separate small-launcher measurement avoids attributing that to Stream1090. Gprof is diagnostic only: it forces the update out of line and cannot supply production speed percentages.

## Preserved packet recovery and limits

Exact Stream output preserves the prior corpus comparison's **34 Stream-only additions** and **403 complete-union extras**, with **zero added or lost packets**. The prior complete native pipeline comparison was subsequently checked for Rust coherent/acquisition parity. We did not rerun every unrelated producer in this task.

| Distance | Stock opportunities | Full-union extras | Stream-only extras |
|---|---:|---:|---:|
| <180 nm | 2,191 | 324 | 31 |
| 180–200 nm | 9 | 10 | 1 |
| 200–250 nm | 1 | 4 | 0 |
| Unknown | 53 | 65 | 2 |

Only ten distant stock opportunities from three aircraft, including one Stream-only distant extra: sufficient for those regression checks, insufficient to claim general far-range robustness or improved range. These are already consumed historical evaluation RF, not prospective data or training labels.

## Protected operation and evidence

All tests ran in owned tmpfs, nice 19, core 3, 35% CPU quota and finite runtime. A conservative summed-process RSS ceiling below 1 GiB was checked independently because this kernel lacks a working memory controller. Highest recorded supervised RSS was {summary['max_owned_test_RSS_MiB']:.1f} MiB, including compilation/launcher context; raw launch RSS is conservative. FR24, readsb, DSP, relay, ADS-B Exchange and collection retained PIDs; production source/library/model/config hashes, methods, 38.6 dB gain, SDR-loss counters and 5,000,000,000-byte capture cap remained unchanged. No live RF tap, packet injection, recorder flush, production restart or persistent archive deletion.

The full source/RF/toolchain/binary/results/log bundle was checksum-verified and fsynced on Mac before exact owned tmpfs cleanup. Development failures and early slower ports are preserved separately. The final implementation makes polynomial deltas explicit compile-time constants, avoiding repeated fixed computation in the initial Rust port. No decoder thresholds or model decisions were tuned to this RF.

Reproducible code: experiments/rust-stream-20261109. Private evidence: adsb-neural-rescue/results/rust-stream-20261109. Candidate is **not enabled**.
'''
(O/'report.md').write_text(text);(O/'report.html').write_text('<!doctype html><meta charset="utf-8"><title>Stream1090 Rust benchmark</title><style>body{max-width:1050px;margin:40px auto;padding:20px;background:#101b29;color:#dfebf7;font:16px/1.6 system-ui}pre{white-space:pre-wrap}</style><pre>'+html.escape(text)+'</pre>')
print(json.dumps(dict(saving_vs_production=t['median_rust_saving_vs_production_percent'],kernel_saving=p['median_kernel_cpu_saving_percent'],RSS=p['isolated_decoder_rss'],production_unchanged=True),indent=2))
