#!/usr/bin/env python3
import pathlib,subprocess,tarfile,io,json,hashlib,os
P=pathlib.Path('/Users/mit/Documents/!project/adsb-neural-rescue');D=P/'results/async-producers-20261109/target';D.mkdir(parents=True,exist_ok=True)
code=r'''
import pathlib,subprocess,json,hashlib,tarfile,io,sys
assert subprocess.run(['systemctl','is-active','--quiet','adsb-async-producers-replay-20261109-v4']).returncode!=0,'Replay still running'
root=pathlib.Path('/run/adsb-async-producers-replay-20261109');stage=pathlib.Path('/dev/shm/adsb-async-producers-replay-code-20261109');assert (root/'pi-v4.json').exists()
files={p.name:p.read_bytes() for p in root.glob('*.json')}
for p in (stage/'experiments/async-producers-20261109').iterdir():
 if p.is_file():files['sources/'+p.name]=p.read_bytes()
hashes={str(p.relative_to(stage)):hashlib.sha256(p.read_bytes()).hexdigest() for folder in ['src/rescue','models'] for p in (stage/folder).rglob('*') if p.is_file() and p.suffix in ['.py','.so','.onnx','.json']};files['source-model-hashes.json']=json.dumps(hashes,indent=2).encode()
for u in ['adsb-async-producers-replay-20261109','adsb-async-producers-replay-20261109-v2','adsb-async-producers-replay-20261109-v3','adsb-async-producers-replay-20261109-v4','adsb-async-producers-tests-20261109','adsb-async-producers-tests-20261109-v2']:
 files['journals/'+u+'.txt']=subprocess.check_output(['journalctl','-u',u,'--no-pager','-o','cat'])
m={n:dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest()) for n,b in files.items()};files['manifest.json']=json.dumps(m,indent=2).encode();out=io.BytesIO()
with tarfile.open(fileobj=out,mode='w:gz') as t:
 for n,b in files.items():i=tarfile.TarInfo(n);i.size=len(b);i.mode=0o600;t.addfile(i,io.BytesIO(b))
sys.stdout.buffer.write(out.getvalue())
'''
b=subprocess.check_output(['ssh','adsb-rpi','sudo','python3','-'],input=code.encode(),timeout=60);archive=D/'evidence.tar.gz';assert not archive.exists();archive.write_bytes(b)
with archive.open('rb') as f:os.fsync(f.fileno())
with tarfile.open(fileobj=io.BytesIO(b)) as t:
 m=json.load(t.extractfile('manifest.json'))
 for n,r in m.items():
  raw=t.extractfile(n).read();assert len(raw)==r['bytes'] and hashlib.sha256(raw).hexdigest()==r['sha256'];assert not n.startswith('/') and '..' not in pathlib.Path(n).parts
  p=D/'files'/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
  with p.open('rb') as f:os.fsync(f.fileno())
hashes=json.loads((D/'files/source-model-hashes.json').read_text());raw=P/'data/raw/async-producers-20261109/files/runtime'
for n,h in hashes.items():
 p=raw/n
 if p.exists():assert hashlib.sha256(p.read_bytes()).hexdigest()==h,'Target runtime differs from captured baseline: '+n
r=dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest(),members_verified=len(m),captured_runtime_matches=True);(D/'receipt.json').write_text(json.dumps(r,indent=2)+'\n')
for d in [D,*[p for p in D.rglob('*') if p.is_dir()]]:
 fd=os.open(d,os.O_RDONLY);os.fsync(fd);os.close(fd)
print(json.dumps(r))
