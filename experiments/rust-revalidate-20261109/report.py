"""Generate credential-free deployment summary from privately preserved evidence."""
from pathlib import Path
import json,html
D=Path('/Users/mit/Documents/!project/adsb-neural-rescue/results/rust-revalidate-20261109');O=Path(__file__).resolve().parents[2]/'validation/rust-revalidate-20261109';O.mkdir(parents=True,exist_ok=True)
p=json.loads((D/'proof.json').read_text());a=json.loads((D/'activation.private.json').read_text());g=json.loads((D/'final-guard.private.json').read_text());v=json.loads((D/'live-observation.private.json').read_text());first,last=v['first'],v['last'];i=json.loads((D/'rollback-investigation.json').read_text())
assert a['state']=='active' and g['state']=='healthy'
deltas={k:last[k]-first[k] for k in ['completed','aligned','stock_bytes','extras','coherent_extras','acquisition_extras']}
summary=dict(state=a['state'],verified_unix=a['verified_unix'],observation_seconds=a['observation_seconds'],guard=g['state'],backend_markers=g['backend_markers'],mapped_workers=g['mapped'],proof={k:v for k,v in p.items() if k not in ['validation_snapshot']},live=dict(counter_deltas=deltas,protected_pids_unchanged=first['protected_pids']==last['protected_pids'],config_hashes_unchanged=first['config_hashes']==last['config_hashes'],sample_loss_unchanged=first['samples']==last['samples'],gain=last['gain'],processing_proxy_s=[min(x['snapshot']['processing_s'] for x in v['samples']),max(x['snapshot']['processing_s'] for x in v['samples'])],capture_cap_bytes=last['capture_cap'],fr24_connected=last['fr24_connected'],capture_error=last['capture_error']),historical_rollback={k:i[k] for k in ['recorded_reason','conclusion','source_journal_sha256']},target_receipt=json.loads((D/'target-receipt.json').read_text()),activation_receipt=json.loads((D/'activation-receipt.json').read_text()))
(O/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
text=f'''# Rust coherent and acquisition reactivation — 9 November 2026

Rust ordinary coherent, paired coherent and acquisition scoring/selection are active. Both coherent workers map the installed Rust libraries. Gain remains 38.6 dB. Only the DSP coordinator was restarted; readsb, FR24, the relay, ADS-B Exchange and the RF collector retained their PIDs. Neural models, switches and feeder routing were preserved. EM was not changed.

## Why the previous release rolled back

At 30 October 00:19:35 CET, two legacy watchdogs restored C after three failures of an assertion that aligned RF seconds must advance. The recorded reason was `{i['recorded_reason']}`. That assertion did not distinguish input silence, alignment inactivity and computation failure. Both guards could restore/restart concurrently. No Rust panic or segmentation fault was found in the preserved service records. The underlying cause cannot be established; neither a Rust defect nor a false alarm is proven. Preserved binary journal SHA-256: `{i['source_journal_sha256']}`.

## Pi validation

| Check | Result |
|---|---|
| Coherent recorded windows | {p['coherent_windows']:,}; every output array bit-exact against C |
| Coherent augmentation | 8,192 phase/amplitude cases and 500 peak cases per branch |
| Acquisition | 1,201 scoring/selection cases; budgets 1/8/16/64/256; tie fallback and noise controls |
| Full enabled native pipeline | 24 RF seconds, six Rust cycles; all raw candidates, guarded events, decisions and alignment audits identical |
| Persistent-worker soak | {p['rust_soak_wall_s']:.1f} seconds wall; {p['rust_RF_seconds']} RF seconds |
| Live observation | {a['observation_seconds']:.1f} seconds; healthy guard, unchanged protected services/configurations/sample-loss counters |
| Rollback/policy tests | Seven tests passed on Mac and Pi; exact C restoration, coordinator-only restart, human edits preserved |

| Kernel | CPU reduction versus C |
|---|---:|
| Ordinary coherent | {p['coherent_ordinary_saving_percent']:.2f}% |
| Paired coherent | {p['coherent_pair_saving_percent']:.2f}% |
| Acquisition, budget 16 | {p['acquisition_selector_saving_percent']:.2f}% |

These are isolated kernel savings, not whole-Pi savings. Full worker CPU changed by {p['worker_CPU_change_percent']:.2f}% in this finite replay; one C cycle versus six Rust cycles makes that descriptive rather than a precise system energy estimate. The 24 seconds are historical regression RF, not fresh range evidence. This is a parity deployment, not a claim of additional detections. Unmodified Stream1090 retains original-first output.

Live observation produced {deltas['coherent_extras']:,} coherent and {deltas['acquisition_extras']:,} acquisition extras while stock forwarding continued. These are production counter increments, not evidence of an advantage over C. Processing proxy ranged {summary['live']['processing_proxy_s'][0]:.3f}–{summary['live']['processing_proxy_s'][1]:.3f} seconds, below the 3-second limit. Collector cap remains 5,000,000,000 bytes; no persistent archive deletion or forced recorder flush occurred.

## Rollback and evidence

One coordinated persistent guard replaces the competing legacy Rust guards and temporarily owns the prior async profile guard's safety checks. It distinguishes RF-input, worker-completion and alignment progress, records failure snapshots, checks actual mapped libraries and rolls back after repeated unsafe conditions. Alignment inactivity with healthy input/work is an advisory. The guard also checks processing budget, sample loss, relay, FR24, collection and queues. It respects unexpected human changes instead of overwriting them. The old rollback records remain intact, with successor pointers.

Status: `sudo python3 /var/lib/adsb-rust-kernels-20261109/control.py status`

Manual rollback: `sudo python3 /var/lib/adsb-rust-kernels-20261109/control.py rollback`

Complete isolated source/model/RF/results bundle and deployed C rollback bytes, live observations, units and journals are checksum-verified and fsynced on the Mac in the private results directory. Public summary contains no raw RF, sharing keys or credentials. Receipt hashes and reproducible scripts are retained. Stability evidence is finite; the persistent guard remains enabled.
'''
(O/'report.md').write_text(text)
(O/'report.html').write_text('<!doctype html><meta charset="utf-8"><title>Rust reactivation</title><style>body{max-width:1050px;margin:40px auto;padding:20px;background:#101b29;color:#dfebf7;font:16px/1.6 system-ui}pre{white-space:pre-wrap}</style><pre>'+html.escape(text)+'</pre>')
print(json.dumps(summary['live'],indent=2))
