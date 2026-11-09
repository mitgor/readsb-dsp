"""Redacted activation/rollback report from preserved live observation."""
from pathlib import Path
import json,html
D=Path('/Users/mit/Documents/!project/adsb-neural-rescue/results/stream-rust-activation-20261109');O=Path(__file__).resolve().parents[2]/'validation/stream-rust-activation-20261109';O.mkdir(parents=True,exist_ok=True);a=json.loads((D/'active.private.json').read_text());g=json.loads((D/'guard.private.json').read_text());o=json.loads((D/'observation.private.json').read_text());first,last=o['first'],o['last'];assert a['state']=='active' and g['state']=='healthy';assert first['protected_pids']==last['protected_pids'] and first['shadow_pid']==last['shadow_pid'];assert first['config_hashes']==last['config_hashes'] and first['methods']==last['methods'] and first['worker_config']==last['worker_config'] and first['gain']==last['gain'] and first['samples']==last['samples']
s=dict(state='active',observation_seconds=a['observed_seconds'],before_sha256=a['before_sha256'],after_sha256=a['after_sha256'],verified_live_exec_samples=len(o['child_evidence']),stream_RF_seconds=last['stream_rf']-first['stream_rf'],stream_extras_forwarded=last['stream_relay']-first['stream_relay'],stock_bytes_forwarded=last['stock_bytes']-first['stock_bytes'],all_production_PIDs_unchanged=True,models_methods_configs_gain_unchanged=True,SDR_loss_unchanged=True,capture_cap_bytes=last['capture_cap'],gain=last['gain'],automatic_rollback=True,receipt=json.loads((D/'receipt.json').read_text()))
(O/'summary.json').write_text(json.dumps(s,indent=2)+'\n');text=f'''# Rust Stream1090 activation — November 9–10, 2026

Rust Stream1090's validated eight-stream shift-register/CRC kernel is active. The surrounding C++ decoder and guards remain unchanged. Previously measured median total Stream CPU reduction: 13.61% on the current Pi 5. No pulse-sequence Rust deployment is included.

The ELF was replaced atomically at the existing executable path. Each RF-second job starts a fresh process, so no receiver, DSP coordinator, relay, feeder, ADS-B Exchange or collector restart was necessary. The next spawned job used Rust; an already-running old job could finish normally.

The {a['observed_seconds']:.1f}-second observation passed. {s['stream_RF_seconds']} RF seconds were processed and {s['stream_extras_forwarded']} Stream extras forwarded while stock forwarding continued. {s['verified_live_exec_samples']} live process observations confirmed the installed candidate inode at the actual executable path. Forwarded extras show activity, not new recoveries versus C. All production PIDs, models, configuration, switches, 38.6 dB gain and sample-loss counters stayed unchanged. The RF cap remains 5,000,000,000 bytes.

One Stream-specific persistent timer checks receiver/feeder/collector health, input and worker progress, Stream errors/progress, queues, processing margin and binary ownership every ten seconds. Three repeated unsafe observations restore exact saved C++ bytes atomically. No producer restart is needed for rollback either. Unexpected human binary edits are preserved and supersede this release. The prior coherent/acquisition guard stays active and retains ownership of its libraries.

The activation has a systemd failure fallback and exact binary backup; two rollback tests passed (byte restoration without any service restart; preserving external human edits). Full live observations, original/candidate ELF, control and dependency sources, units, journals and checksum receipt are durably saved in the private results directory. No recorder flush or archive deletion occurred.

Status: `sudo python3 /var/lib/adsb-stream-rust-20261109/control.py status`

Manual rollback: `sudo python3 /var/lib/adsb-stream-rust-20261109/control.py rollback`

Finite live validation supports this activation; the persistent guard remains enabled. Public files contain no RF, credentials or sharing key.
'''
(O/'report.md').write_text(text);(O/'report.html').write_text('<!doctype html><meta charset="utf-8"><title>Stream Rust activation</title><style>body{max-width:1000px;margin:40px auto;padding:20px;background:#101b29;color:#dfebf7;font:16px/1.6 system-ui}pre{white-space:pre-wrap}</style><pre>'+html.escape(text)+'</pre>');print(json.dumps(s,indent=2))
