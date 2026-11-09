#!/usr/bin/env python3
import subprocess,tarfile,io,json,hashlib,os
from pathlib import Path
P=Path('/Users/mit/Documents/!project/adsb-neural-rescue');D=P/'data/raw/async-producers-20261109';D.mkdir(parents=True,exist_ok=True)
code=r'''
import pathlib,json,tarfile,io,hashlib,sys,subprocess
root=pathlib.Path('/home/pi/adsb-neural-rescue');files={}
for ver in ['v2','v3']:
 d=pathlib.Path('/run/adsb-async-producers-20261109-'+ver+'-capture/data')
 assert subprocess.run(['systemctl','is-active','--quiet','adsb-async-producers-capture-20261109-'+ver]).returncode!=0
 for p in d.iterdir():
  if p.is_file():files['capture-'+ver+'/'+p.name]=p
for p in (root/'src/rescue').iterdir():
 if p.is_file() and p.suffix in ['.py','.so','.c','.h','.rs']:files['runtime/src/rescue/'+p.name]=p
for name in ['tiny-fp32.onnx','pulse-sequence.json','pulse-discriminant.json','candidates/dsp-20261025/tiny-rf-v1.onnx','candidates/improvement-raw-20261027/tiny-rf-v1.onnx']:files['runtime/models/'+name]=root/'models'/name
files['runtime/stream1090']=pathlib.Path('/home/pi/stream1090-shadow/build/stream1090')
for name,p in [('runtime/worker-config.json','/etc/default/adsb-rescue-workers.json'),('runtime/method-config.json','/etc/default/adsb-rescue.json'),('runtime/receiver.private.json','/run/readsb/receiver.json')]:files[name]=pathlib.Path(p)
manifest={n:dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for n,p in files.items()}
b=io.BytesIO()
with tarfile.open(fileobj=b,mode='w') as t:
 for name,p in files.items():t.add(p,arcname=name,recursive=False)
 raw=json.dumps(manifest,indent=2).encode();i=tarfile.TarInfo('transfer-manifest.json');i.size=len(raw);t.addfile(i,io.BytesIO(raw))
sys.stdout.buffer.write(b.getvalue())
'''
b=subprocess.check_output(['ssh','adsb-rpi','sudo','python3','-'],input=code.encode(),timeout=120);archive=D/'evidence.tar';assert not archive.exists();archive.write_bytes(b);archive.chmod(0o600)
with archive.open('rb') as f:os.fsync(f.fileno())
with tarfile.open(fileobj=io.BytesIO(b)) as t:
 manifest=json.load(t.extractfile('transfer-manifest.json'))
 for n,row in manifest.items():
  raw=t.extractfile(n).read();assert len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256'];assert not n.startswith('/') and '..' not in Path(n).parts
  p=D/'files'/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw);p.chmod(0o700 if n=='runtime/stream1090' else 0o600)
  with p.open('rb') as f:os.fsync(f.fileno())
intervals=[]
for ver,name in [('v2','error.json'),('v3','capture.private.json')]:
 data=json.loads((D/'files'/('capture-'+ver)/name).read_text())
 for c in data['cases']:intervals.append(dict(epoch=int(c['epoch']),sample_start=int(c['first']),sample_count=int(c['sample_count'])))
reservation=P/'data/raw/long-validation-async-producers-20261109/reserved-intervals.json';reservation.parent.mkdir(parents=True,exist_ok=True);assert not reservation.exists();reservation.write_text(json.dumps(dict(schema='long-validation-v1',evaluation_only=True,captures=intervals),indent=2)+'\n')
for p in [reservation]:
 with p.open('rb') as f:os.fsync(f.fileno())
for d in [D,reservation.parent,*[p for p in D.rglob('*') if p.is_dir()]]:
 fd=os.open(d,os.O_RDONLY);os.fsync(fd);os.close(fd)
r=dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest(),members_verified=len(manifest),reserved_intervals=len(intervals));(D/'receipt.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
