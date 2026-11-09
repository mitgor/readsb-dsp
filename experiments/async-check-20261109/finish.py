#!/usr/bin/env python3
import subprocess,tarfile,io,json,hashlib,os
from pathlib import Path
D=Path('/Users/mit/Documents/!project/adsb-neural-rescue/results/async-check-20261109');D.mkdir(parents=True,exist_ok=True)
code=r'''
import pathlib,subprocess,tarfile,io,json,hashlib,sys
assert subprocess.run(['systemctl','is-active','--quiet','adsb-async-check-20261109-v2']).returncode!=0
root=pathlib.Path('/run/adsb-async-check-20261109-v2');assert (root/'data/probe.json').exists()
files={str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}
for unit in ['adsb-async-check-20261109','adsb-async-check-20261109-v2','adsb-async-unit-check-20261109']:
 files['journals/'+unit+'.txt']=subprocess.check_output(['journalctl','-u',unit,'--no-pager','-o','cat'])
m={n:dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest()) for n,b in files.items()};files['manifest.json']=json.dumps(m,indent=2).encode();out=io.BytesIO()
with tarfile.open(fileobj=out,mode='w:gz') as t:
 for n,b in files.items():
  i=tarfile.TarInfo(n);i.size=len(b);i.mode=0o600;t.addfile(i,io.BytesIO(b))
sys.stdout.buffer.write(out.getvalue())
'''
b=subprocess.check_output(['ssh','adsb-rpi','sudo','python3','-'],input=code.encode());p=D/'evidence.tar.gz';assert not p.exists();p.write_bytes(b);p.chmod(0o600)
with p.open('rb') as f:os.fsync(f.fileno())
with tarfile.open(fileobj=io.BytesIO(b)) as t:
 m=json.load(t.extractfile('manifest.json'))
 for n,r in m.items():
  raw=t.extractfile(n).read();assert len(raw)==r['bytes'] and hashlib.sha256(raw).hexdigest()==r['sha256'];assert not n.startswith('/') and '..' not in Path(n).parts
  dest=D/'files'/n;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
  with dest.open('rb') as f:os.fsync(f.fileno())
r=dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest(),verified_members=len(m),files=m);(D/'receipt.json').write_text(json.dumps(r,indent=2)+'\n')
for d in [D,*[p for p in D.rglob('*') if p.is_dir()]]:
 fd=os.open(d,os.O_RDONLY);os.fsync(fd);os.close(fd)
print(json.dumps({k:v for k,v in r.items() if k!='files'}))
