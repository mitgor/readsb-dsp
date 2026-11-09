#!/usr/bin/env python3
"""Recorded final target staging: executable root-owned tmpfs, not noexec /run."""
import subprocess,base64
from pathlib import Path
H=Path(__file__).resolve().parent
files={n:base64.b64encode((H/n).read_bytes()).decode() for n in ['integration.py','replay.py','protected.py','health.py','test_integration.py']}
code='FILES='+repr(files)+'''
import pathlib,shutil,os,base64,subprocess
old=pathlib.Path('/run/adsb-async-producers-replay-20261109');stage=pathlib.Path('/dev/shm/adsb-async-producers-replay-code-20261109')
assert old.exists() and not stage.exists(),'Preserve existing attempts; prepare a new owned stage'
shutil.copytree(old,stage,symlinks=True,ignore=shutil.ignore_patterns('jobs-*','__pycache__','*.private.json','pi*.json'))
h=stage/'experiments/async-producers-20261109'
for n,b in FILES.items():(h/n).write_bytes(base64.b64decode(b))
for p in [stage,*stage.rglob('*')]:
 if not p.is_symlink():os.chown(p,0,0);p.chmod(0o755 if p.is_dir() or p.name=='stream1090' else 0o644)
subprocess.run(['systemd-run','--unit=adsb-async-producers-replay-20261109-v4','-p','Nice=19','-p','AllowedCPUs=3','-p','CPUQuota=35%','-p','MemoryMax=1G','-p','RuntimeMaxSec=480','env','PYTHONPATH='+str(stage/'src')+':'+str(h),'OPENBLAS_NUM_THREADS=1','OMP_NUM_THREADS=1','/home/pi/adsb-neural-rescue/.venv/bin/python',str(h/'protected.py'),str(stage),str(old)],check=True)
'''
print(subprocess.check_output(['ssh','adsb-rpi','sudo','python3','-'],input=code,text=True))
