"""Finalize this immutable collection/qualification run, without training below trigger."""
from pathlib import Path
import json,hashlib,os,html,subprocess,urllib.request,datetime
R=Path('/Users/mit/Documents/!project/adsb-neural-rescue');C=Path(__file__).resolve().parents[2];O=R/'results/companion-20261109-evening';V=C/'validation/companion-20261109-evening';V.mkdir(exist_ok=False)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,j):
 with p.open('w') as f:json.dump(j,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
 fd=os.open(p.parent,os.O_RDONLY);os.fsync(fd);os.close(fd)
b=json.loads((O/'receiver-before.private.json').read_text());a=json.loads((O/'receiver-after.private.json').read_text());checks={k:b[k]==a[k] for k in ['pids','methods','workers','model_sha256','source_hashes','configs','samples','gain_db','logging_enabled']};assert all(checks.values());assert a['capture']['config']['disk_limit_bytes']==5000000000
m=json.loads(next(O.glob('offload-*.json')).read_text());assert all(r['mac_verified_durable'] and r['remote_deleted'] for r in m['files']);audit=json.loads((O/'new-data-audit.json').read_text());ready=json.loads((O/'readiness.json').read_text());assert not ready['trigger'];q=json.loads(next(O.glob('*.qualification.json')).read_text());base=json.loads((O/'full-current-baseline.private.json').read_text())
s=dict(date_berlin='2026-11-09',run='companion-20261109-evening',verified_archives=len(m['files']),verified_bytes=m['verified_bytes'],verified_remote_copies_deleted=len(m['files']),qualification=q['counts'],new_unique_counts=ready['counts'],pending_since_completed_fit='daily-20261104',coverage=ready['coverage'],training_trigger=False,shortfall=ready['shortfall'],trained=False,new_candidate_benchmark_run=False,reason='23 additional qualified, deduplicated >=180nm TRAIN examples required to meet the frozen 500/100 trigger; validation, aircraft and UTC-hour coverage requirements already met.',reserved_continuous_segments=audit['reserved_continuous_segments'],quarantined_crc_iq_windows=audit['crc']['iq_verified'],baseline_methods=base['methods'],baseline_production_models=len(base['models']),protected_checks=checks,rf_cap_bytes=5000000000,forced_flush=False,live_changes=False,limitations=['Stock-derived range is quality-gated, not independent surveyed ground truth.','73 offered training snippets did not pass independent uncorrected same-transmission confirmation and remain untrusted.','Continuous RF and fixed ICAO test snippets are evaluation-only. CRC/DSP/neural predictions are not labels.','No new candidate, recovery additions/losses, CPU benchmark, controls or export result is claimed.','Active RAM is intentionally left for normal 12-hour saves; saved-archive transfer is not a full RAM snapshot.'])
for folder in [O,V]:save(folder/'summary.json',s)
text=f'''# Neural companion data update — 9 November 2026, evening

Transferred and checksum-verified **7 archives / 131,471,256 bytes (131.5 MB)** to the Mac. Files, directories and durable manifests were fsynced before rechecking exact remote identity, size, modification time, open-writer state and SHA-256. Only those seven verified Pi copies were removed. Existing Mac data and all active receiver buffers remain preserved. No flush, service restart, gain/model/switch/routing change or cap change occurred.

## Label validation

The RF archive contains **144** stock-assisted distant snippets. **71 passed** original RF/member hashes, stock Beast/payload/sample-clock matching, causal quality-gated positions and independent uncorrected decoding of that same transmission using pinned readsb SHA-256 `{q['readsb_sha256']}`. Of these, 68 are 180–200 nm and three are 200–250 nm. The other 73 remain quarantined; a matching address or later payload repetition does not qualify them.

Aircraft/payload/IQ deduplication, fixed historical split membership, prior-consumption statuses and overlapping RF exclusions were retained. New qualified examples add **45 TRAIN**, **11 VALIDATION**, and **15 fixed evaluation-only TEST** windows. All **246 continuous RF intervals** were reserved globally for evaluation before qualification. **6,168 CRC research I/Q windows** were hash-verified but remain quarantined.

| Pending since the completed November 4 fit | Windows | Aircraft | UTC hours |
|---|---:|---:|---:|
| TRAIN | 477 | 237 | 69 |
| VALIDATION | 151 | 80 | 52 |
| Fixed TEST, never fitted | 224 | 84 | 77 |

The frozen trigger requires 500 new eligible TRAIN windows from at least ten aircraft/three UTC hours, plus 100 independent VALIDATION windows from at least three aircraft. We remain **23 TRAIN windows short**. No model was retrained and no new-candidate benchmark was run. Previous models and checkpoints are retained. This run does not claim additional recovered transmissions, CPU gains or distant-range improvement.

## Full current comparison baseline recorded

The next eligible companion must beat the complete **enabled** pipeline: stock readsb plus energy, timing, soft, matched, coherent/pair retries, neural original-first three-model cascade, pulse, sequence, improved acquisition and Stream1090. Current optimized native/Rust implementations and worker settings are fingerprinted. SIC/header remain off; broad CRC CPU is retained as research overhead while its predictions remain quarantined. Relay is asynchronous with a shared five-second transmission cache and a three-second extra-age limit.

Saved private baseline metadata includes all current model, source/library and config hashes plus the Stream1090 executable hash. Future replay must use identical RF and verify sample alignment, full stock/relay/accepted-output coverage, unique additions/losses by distance, CPU, noise/clean/overlap controls, export parity, original neural and previous-best companion retention. No incomplete or already-consumed comparison will be called fresh prospective evidence.

## Continuation and preservation

Continue from this run's `learning-ledger.json`, not the earlier November 9 morning ledger. A checksum-backed pointer is saved at `data/processed/learning-ledger-current.json`. New evaluation RF reservations and all source provenance stay in the private workspace. Qualified data is retained without admitting it to fitting until the trigger and complete split audits pass.

All service PIDs, model/source/config hashes, switches, gain and stock sample-loss counters matched before/after. The 5,000,000,000-byte RF cap and 12-hour disk-save cadence are unchanged. Active RAM data was not forced to disk; further saved archives can provide the remaining examples.
'''
for folder in [O,V]:(folder/'report.md').write_text(text)
(V/'report.html').write_text('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Neural data update</title><style>body{font:17px/1.5 system-ui;max-width:1050px;margin:32px auto;padding:20px}pre{white-space:pre-wrap;font:inherit}</style><pre>'+html.escape(text)+'</pre>')
pointer=R/'data/processed/learning-ledger-current.json';assert not pointer.exists();save(pointer,dict(schema='learning-ledger-pointer-v1',ledger=str((O/'learning-ledger.json').relative_to(R)),sha256=sha(O/'learning-ledger.json'),last_completed_fit='daily-20261104',pending_train=477,pending_validation=151,updated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),predecessor='results/daily-20261109/learning-ledger.json'))
remote='/usr/share/adsb-rescue/companion-20261109-evening';subprocess.run(['ssh','adsb-rpi','sudo','mkdir','-p',remote],check=True);pub={}
for n in ['report.html','summary.json']:
 raw=(V/n).read_bytes();subprocess.run(['ssh','adsb-rpi','sudo','tee',remote+'/'+n],input=raw,stdout=subprocess.DEVNULL,check=True);assert hashlib.sha256(urllib.request.urlopen('http://192.168.2.195/neural-rescue/companion-20261109-evening/'+n).read()).hexdigest()==sha(V/n);pub[n]=sha(V/n)
save(V/'publication.json',pub)
items=[]
for p in O.iterdir():
 if p.is_file() and p.name!='artifact-manifest.json':
  with p.open('rb') as f:os.fsync(f.fileno())
  items.append(dict(path=p.name,bytes=p.stat().st_size,sha256=sha(p)))
save(O/'artifact-manifest.json',dict(artifacts=items));print(json.dumps(s))
