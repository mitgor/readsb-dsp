#!/usr/bin/env python3
import subprocess,io,tarfile,base64
from pathlib import Path
R=Path(__file__).resolve().parents[2];out=io.BytesIO()
with tarfile.open(fileobj=out,mode='w:gz') as t:
 files=[(R/'experiments/async-producers-20261109/observe_live.py','observe.py'),(R/'experiments/async-producers-20261109/health.py','health.py'),*[(p,'experiments/async-relay-20261030/'+p.name) for p in (R/'experiments/async-relay-20261030').glob('*.py')],(R/'experiments/latency-publication-20261030/prototype.py','experiments/latency-publication-20261030/prototype.py')]
 for p,n in files:
  raw=p.read_bytes();i=tarfile.TarInfo(n);i.size=len(raw);t.addfile(i,io.BytesIO(raw))
code='B='+repr(base64.b64encode(out.getvalue()).decode())+'''
import pathlib,os,pwd,tarfile,io,base64,subprocess
p=pathlib.Path('/run/adsb-async-producers-observer-20261109-v2/code');assert not p.exists();p.mkdir(parents=True);u=pwd.getpwnam('pi')
with tarfile.open(fileobj=io.BytesIO(base64.b64decode(B))) as t:
 for m in t.getmembers():
  assert m.isfile() and not m.name.startswith('/') and '..' not in pathlib.Path(m.name).parts
  q=p/m.name;q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(t.extractfile(m).read())
for q in [p.parent,p,*p.rglob('*')]:os.chown(q,u.pw_uid,u.pw_gid)
subprocess.run(['systemd-run','--unit=adsb-async-producers-observer-20261109-v2','--uid=pi','-p','Nice=19','-p','AllowedCPUs=3','-p','CPUQuota=35%','-p','MemoryMax=512M','-p','RuntimeMaxSec=180','env','PYTHONPATH=/home/pi/adsb-neural-rescue/src:'+str(p)+':'+str(p/'experiments/async-relay-20261030'),'OPENBLAS_NUM_THREADS=1','OMP_NUM_THREADS=1','/home/pi/adsb-neural-rescue/.venv/bin/python',str(p/'observe.py')],check=True)
'''
print(subprocess.check_output(['ssh','adsb-rpi','sudo','python3','-'],input=code,text=True))
