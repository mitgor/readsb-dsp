#!/usr/bin/env python3
import subprocess,tarfile,io,json,hashlib,os
from pathlib import Path
D=Path('/Users/mit/Documents/!project/adsb-neural-rescue/results/async-producers-20261109/live-observer');D.mkdir(parents=True,exist_ok=True)
code=r'''
import pathlib,subprocess,json,tarfile,io,hashlib,sys
unit='adsb-async-producers-observer-20261109-v2';assert subprocess.run(['systemctl','is-active','--quiet',unit]).returncode!=0
root=pathlib.Path('/run/'+unit+'/data');assert (root/'result.json').exists();files={p.name:p.read_bytes() for p in root.iterdir() if p.is_file()}
for u in ['adsb-async-producers-capture-20261109','adsb-async-producers-capture-20261109-v2','adsb-async-producers-capture-20261109-v3','adsb-async-producers-observer-20261109','adsb-async-producers-observer-20261109-v2']:
 files['journals/'+u+'.txt']=subprocess.check_output(['journalctl','-u',u,'--no-pager','-o','cat'])
m={n:dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest()) for n,b in files.items()};files['transfer.json']=json.dumps(m,indent=2).encode();out=io.BytesIO()
with tarfile.open(fileobj=out,mode='w:gz') as t:
 for n,b in files.items():i=tarfile.TarInfo(n);i.size=len(b);i.mode=0o600;t.addfile(i,io.BytesIO(b))
sys.stdout.buffer.write(out.getvalue())
'''
b=subprocess.check_output(['ssh','adsb-rpi','sudo','python3','-'],input=code.encode(),timeout=90);p=D/'evidence.tar.gz';assert not p.exists();p.write_bytes(b)
with p.open('rb') as f:os.fsync(f.fileno())
with tarfile.open(fileobj=io.BytesIO(b)) as t:
 m=json.load(t.extractfile('transfer.json'))
 for n,r in m.items():
  assert not n.startswith('/') and '..' not in Path(n).parts
  raw=t.extractfile(n).read();assert len(raw)==r['bytes'] and hashlib.sha256(raw).hexdigest()==r['sha256'];p=D/'files'/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
  with p.open('rb') as f:os.fsync(f.fileno())
r=dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest(),files=m);(D/'receipt.json').write_text(json.dumps(r,indent=2)+'\n')
for d in [D,*[p for p in D.rglob('*') if p.is_dir()]]:
 fd=os.open(d,os.O_RDONLY);os.fsync(fd);os.close(fd)
print('Observer evidence verified',len(m),len(b))
