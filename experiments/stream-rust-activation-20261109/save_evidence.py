"""Preserve deployed binary/backup/control/units and live observation privately."""
from pathlib import Path
import subprocess,json,hashlib,tarfile,io,os
D=Path('/Users/mit/Documents/!project/adsb-neural-rescue/results/stream-rust-activation-20261109');assert not (D/'evidence.private.tar').exists()
code=r'''
from pathlib import Path
import subprocess,sys,tarfile,io,hashlib,json
D=Path('/var/lib/adsb-stream-rust-20261109');R=Path('/run/adsb-stream-rust-20261109');a=json.loads((D/'active.json').read_text());g=json.loads((R/'guard.json').read_text());assert a['state']=='active' and g['state']=='healthy';files={str(p):p.read_bytes() for root in [D,R] for p in root.rglob('*') if p.is_file()}
for p in Path('/etc/systemd/system').glob('adsb-stream-rust-*20261109*'):
 if p.is_file():files[str(p)]=p.read_bytes()
for n in ['control.py','policy.py']:
 p=Path('/var/lib/adsb-rust-kernels-20261109')/n;files[str(p)]=p.read_bytes()
files['journal.txt']=subprocess.check_output(['journalctl','--no-pager','-o','short-iso-precise','-u','adsb-stream-rust-activate-20261109','-u','adsb-stream-rust-20261109','-u','adsb-stream-rust-rollback-20261109']);files['timer.txt']=subprocess.check_output(['systemctl','show','adsb-stream-rust-20261109.timer','-p','ActiveState','-p','UnitFileState'])
b=io.BytesIO();m={}
with tarfile.open(fileobj=b,mode='w') as t:
 for n,raw in files.items():
  n=n.lstrip('/');i=tarfile.TarInfo(n);i.size=len(raw);t.addfile(i,io.BytesIO(raw));m[n]=dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
 raw=json.dumps(m).encode();i=tarfile.TarInfo('manifest.json');i.size=len(raw);t.addfile(i,io.BytesIO(raw))
sys.stdout.buffer.write(b.getvalue())
'''
raw=subprocess.check_output(['ssh','adsb-rpi','sudo','python3','-'],input=code.encode(),timeout=60);p=D/'evidence.private.tar';p.write_bytes(raw);p.chmod(0o600)
with tarfile.open(fileobj=io.BytesIO(raw)) as t:
 m=json.load(t.extractfile('manifest.json'))
 for n,v in m.items():
  b=t.extractfile(n).read();assert len(b)==v['bytes'] and hashlib.sha256(b).hexdigest()==v['sha256']
 for n,d in [('var/lib/adsb-stream-rust-20261109/active.json','active.private.json'),('var/lib/adsb-stream-rust-20261109/observation.json','observation.private.json'),('run/adsb-stream-rust-20261109/guard.json','guard.private.json')]: (D/d).write_bytes(t.extractfile(n).read())
receipt=dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),members=len(m),verified=True);(D/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
for p in D.iterdir():
 if p.is_file():
  with p.open('rb') as f:os.fsync(f.fileno())
fd=os.open(D,os.O_RDONLY);os.fsync(fd);os.close(fd);print(json.dumps(receipt))
