"""Reconcile verified saves, reserve RF, then qualify same-transmission labels."""
from pathlib import Path
import json,os,subprocess
R=Path('/Users/mit/Documents/!project/adsb-neural-rescue');O=R/'results/daily-20261110-manual-save';files={};runs=[]
for p in sorted(O.glob('offload-*.json')):
 d=json.loads(p.read_text());assert d.get('completed_unix');runs.append(p.name)
 for r in d['files']:
  assert r['mac_verified_durable'] and r['remote_deleted'];k=r['path'],r['sha256'];assert k not in files;files[k]=r
m={'files':list(files.values()),'runs':runs,'verified_bytes':sum(x['bytes'] for x in files.values()),'deleted_bytes':sum(x['bytes'] for x in files.values()),'policy':'User-requested RF RAM save; exact byte/SHA-verified durable backup before remote identity/hash recheck and deletion. Fresh archive retained until stable-age guard passed.'}
with (O/'combined-input-manifest.json').open('w') as f:json.dump(m,f,indent=2);f.flush();os.fsync(f.fileno())
subprocess.run(['python3',str(O/'audit.py')],check=True,stdout=(O/'audit-console.json').open('w'),cwd=R)
py='/Users/mit/Documents/Codex/2026-09-30/i-have-a-flightradar24-service-on/work/adsb-neural/.venv/bin/python';teacher='/Users/mit/Documents/Codex/2026-09-30/i-have-a-flightradar24-service-on/work/adsb-neural/readsb-reference/readsb'
for x in json.loads((O/'new-data-audit.json').read_text())['archives']:
 p=Path(x['path']);out=O/(p.name+'.qualified.jsonl.gz')
 with (O/(p.name+'.qualifier-console.json')).open('w') as f:subprocess.run([py,'scripts/collection/qualify_far_training.py',str(p),'--readsb',teacher,'--raw-root',str(R/'data/raw'),'--output',str(out)],check=True,stdout=f,cwd=R,env=dict(os.environ,PYTHONPATH='src',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1'))
with (O/'receiver-after.private.json').open('wb') as f:subprocess.run(['ssh','-o','ConnectTimeout=8','adsb-rpi','sudo -n python3 -'],input=(O/'snapshot_remote.py').read_bytes(),stdout=f,check=True)
subprocess.run([py,str(O/'finalize_ledger.py')],cwd=R,check=True)
