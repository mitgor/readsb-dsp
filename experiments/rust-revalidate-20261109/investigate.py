"""Archived service journal and old watchdog audit; never mutate receiver."""
from pathlib import Path
import struct,json,subprocess,hashlib,datetime,collections,os
R=Path('/Users/mit/Documents/!project/adsb-neural-rescue');O=R/'results/rust-revalidate-20261109';source=R/'incidents/fr24-drop-20261027/private/live-20261030/journal-export.bin';raw=source.read_bytes();at=0;fields={};records=[]
while at<len(raw):
 end=raw.find(b'\n',at)
 if end<0:break
 line=raw[at:end];at=end+1
 if not line:
  try:t=int(fields.get('__REALTIME_TIMESTAMP',b'0'))/1e6
  except ValueError:t=0
  units={fields.get('_SYSTEMD_UNIT',b''),fields.get('UNIT',b'')}
  if 1793314800<t<1793316300 and any(b'rust' in u or u in [b'readsb.service',b'adsb-rescue-shadow.service'] for u in units):records.append(dict(unix=t,utc=datetime.datetime.fromtimestamp(t,datetime.timezone.utc).isoformat(),units=[u.decode() for u in units],message=fields.get('MESSAGE',b'').decode(errors='replace')))
  fields={};continue
 if b'=' in line:k,v=line.split(b'=',1);fields[k.decode(errors='replace')]=v
 else:
  n=struct.unpack_from('<Q',raw,at)[0];at+=8;value=raw[at:at+n];at+=n;assert raw[at:at+1]==b'\n';at+=1;fields[line.decode(errors='replace')]=value
code='''from pathlib import Path
import json,subprocess
out={}
for name,p in [('coherent_state','/var/lib/adsb-coherent-rust/active.json'),('methods_state','/var/lib/adsb-rust-methods/active.json')]:out[name]=json.loads(Path(p).read_text())
for name,p in [('coherent_helper','/usr/local/sbin/adsb-coherent-rust-mode'),('methods_helper','/usr/local/sbin/adsb-rust-methods-mode')]:out[name]=Path(p).read_text()
print(json.dumps(out))
'''
current=json.loads(subprocess.check_output(['ssh','adsb-rpi','sudo','python3','-'],input=code,text=True));(O/'old-release-evidence.private.json').write_text(json.dumps(current,indent=2)+'\n');(O/'old-rollback-journal.json').write_text(json.dumps(records,indent=2)+'\n')
h=json.loads((R/'results/fr24-drop-20261030/history.json').read_text());rrd=[dict(unix=t,local_accepted_per_second=v) for t,v in h['rrd']['local_accepted'] if 1793314800<t<1793316300]
report=dict(coherent_rollback_unix=current['coherent_state']['rolled_back_unix'],acquisition_rollback_unix=current['methods_state']['rolled_back_unix'],recorded_reason=current['coherent_state']['reason'],service_restart_first_unix=next(r['unix'] for r in records if r['message'].startswith('Stopping adsb-rescue-shadow')),readsb_stop_or_restart_in_window=any('readsb.service' in r['units'] and ('Stopping ' in r['message'] or 'Started ' in r['message']) for r in records),recorded_rust_panic_or_segfault=any('panicked at' in r['message'] or 'segfault' in r['message'] for r in records),rrd=rrd,old_watchdog_fault='Conflates lack of aligned_seconds increment with lack of RF computation; no input/completion snapshots persisted on failure. Two independent guards can restore/restart concurrently.',conclusion='Both guards deliberately restored C after three failed alignment-progress checks. Low-level cause not recoverable from preserved evidence; no service-log Rust crash demonstrated. Incoming readsb traffic continued. Do not claim this proves either a Rust bug or a false alarm.',source_journal_sha256=hashlib.sha256(raw).hexdigest())
(O/'rollback-investigation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
