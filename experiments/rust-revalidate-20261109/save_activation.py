"""Preserve deployed rollback bytes, live observation, units and private journal."""
from pathlib import Path
import subprocess,json,hashlib,os,tarfile,io
D=Path('/Users/mit/Documents/!project/adsb-neural-rescue/results/rust-revalidate-20261109')
code=r'''
from pathlib import Path
import json,subprocess,tarfile,io,hashlib,sys
D=Path('/var/lib/adsb-rust-kernels-20261109');R=Path('/run/adsb-rust-kernels-20261109')
a=json.loads((D/'active.json').read_text());g=json.loads((R/'guard.json').read_text());assert a['state']=='active' and g['state']=='healthy' and not g['reasons']
files={str(p):p.read_bytes() for root in [D,R] for p in root.rglob('*') if p.is_file()}
for p in Path('/etc/systemd/system').glob('adsb-rust-kernels-*20261109*'):
 if p.is_file():files[str(p)]=p.read_bytes()
for x in ['adsb-coherent-rust','adsb-rust-methods']:
 p=Path('/var/lib')/x/'successor-20261109.json';files[str(p)]=p.read_bytes()
units=['adsb-rust-kernels-activate-20261109','adsb-rust-kernels-20261109','adsb-rust-kernels-rollback-20261109','adsb-rescue-shadow']
files['journal.txt']=subprocess.check_output(['journalctl','--since','@'+str(int(a['activated_unix'])-30),'--no-pager','-o','short-iso-precise']+sum((['-u',u] for u in units),[]))
files['timer-state.txt']=subprocess.check_output(['systemctl','show','adsb-rust-kernels-20261109.timer','-p','ActiveState','-p','UnitFileState'])
b=io.BytesIO();manifest={}
with tarfile.open(fileobj=b,mode='w') as t:
 for n,raw in files.items():
  n=n.lstrip('/');i=tarfile.TarInfo(n);i.size=len(raw);t.addfile(i,io.BytesIO(raw));manifest[n]={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
 raw=json.dumps(manifest).encode();i=tarfile.TarInfo('manifest.json');i.size=len(raw);t.addfile(i,io.BytesIO(raw))
sys.stdout.buffer.write(b.getvalue())
'''
raw=subprocess.check_output(['ssh','adsb-rpi','sudo','python3','-'],input=code.encode(),timeout=60)
p=D/'activation-evidence.private.tar';p.write_bytes(raw);p.chmod(0o600)
with tarfile.open(fileobj=io.BytesIO(raw)) as t:
 m=json.load(t.extractfile('manifest.json'))
 for n,v in m.items():
  b=t.extractfile(n).read();assert len(b)==v['bytes'] and hashlib.sha256(b).hexdigest()==v['sha256']
 for n,dest in [('var/lib/adsb-rust-kernels-20261109/active.json','activation.private.json'),('var/lib/adsb-rust-kernels-20261109/live-observation.json','live-observation.private.json'),('run/adsb-rust-kernels-20261109/guard.json','final-guard.private.json')]:
  (D/dest).write_bytes(t.extractfile(n).read())
receipt={'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'members':len(m),'verified':True}
(D/'activation-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
for f in D.iterdir():
 if f.is_file():
  with f.open('rb') as h:os.fsync(h.fileno())
fd=os.open(D,os.O_RDONLY);os.fsync(fd);os.close(fd)
print(json.dumps(receipt))
