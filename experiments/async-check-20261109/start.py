#!/usr/bin/env python3
import subprocess,tarfile,io,base64
from pathlib import Path
R=Path(__file__).resolve().parents[2];D='/run/adsb-async-check-20261109-v2'
# Read current receiver source into an isolated snapshot; no production modification.
code="import pathlib,tarfile,io,sys\nb=io.BytesIO()\nwith tarfile.open(fileobj=b,mode='w:gz') as t:\n for p in pathlib.Path('/home/pi/adsb-neural-rescue/src/rescue').glob('*.py'):t.add(p,arcname='src/rescue/'+p.name)\nsys.stdout.buffer.write(b.getvalue())"
b=subprocess.check_output(['ssh','adsb-rpi','python3','-'],input=code.encode());out=io.BytesIO()
with tarfile.open(fileobj=out,mode='w:gz') as t:
 with tarfile.open(fileobj=io.BytesIO(b)) as old:
  for p in old.getmembers():t.addfile(p,old.extractfile(p))
 for source,name in [(R/'experiments/async-check-20261109/probe.py','probe.py'),*[(p,'experiments/async-relay-20261030/'+p.name) for p in (R/'experiments/async-relay-20261030').glob('*.py')],(R/'experiments/latency-publication-20261030/prototype.py','experiments/latency-publication-20261030/prototype.py')]:
  raw=source.read_bytes();i=tarfile.TarInfo(name);i.size=len(raw);t.addfile(i,io.BytesIO(raw))
script="import pathlib,tarfile,io,base64\np=pathlib.Path("+repr(D)+");assert not p.exists();p.mkdir()\nwith tarfile.open(fileobj=io.BytesIO(base64.b64decode("+repr(base64.b64encode(out.getvalue()).decode())+"))) as t:t.extractall(p,filter='data')\n"
# Pi Python3.11 may not expose extraction filters: validate explicit regular paths first.
script=script.replace("t.extractall(p,filter='data')","\n for m in t.getmembers():\n  assert m.isfile() and not m.name.startswith('/') and '..' not in pathlib.Path(m.name).parts\n  q=p/m.name;q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(t.extractfile(m).read())")
script+='\nimport os,pwd\nu=pwd.getpwnam("pi")\nfor q in [p,*p.rglob("*")]:os.chown(q,u.pw_uid,u.pw_gid)\n'
subprocess.run(['ssh','adsb-rpi','sudo','python3','-'],input=script,text=True,check=True)
py='/home/pi/adsb-neural-rescue/.venv/bin/python';env=['env','PYTHONPATH='+D+'/src:'+D+'/experiments/async-relay-20261030','OPENBLAS_NUM_THREADS=1','OMP_NUM_THREADS=1','PROBE_DIR='+D+'/data']
unit=['sudo','systemd-run','--unit=adsb-async-check-20261109-v2','--uid=pi','-p','Nice=19','-p','AllowedCPUs=3','-p','CPUQuota=35%','-p','MemoryMax=256M','-p','RuntimeMaxSec=120',*env,py,D+'/probe.py']
subprocess.run(['ssh','adsb-rpi',*unit],check=True)
print('Started finite isolated read-only relay probe; production routing unchanged.')
