#!/usr/bin/env python3
import subprocess,base64,json
from pathlib import Path
H=Path(__file__).resolve().parent;files={n:base64.b64encode((H/n).read_bytes()).decode() for n in ['capture.py','health.py']}
code='FILES='+repr(files)+'''
import pathlib,os,pwd,base64,subprocess
p=pathlib.Path('/run/adsb-async-producers-20261109-v3-code');assert not p.exists();p.mkdir();u=pwd.getpwnam('pi')
for n,b in FILES.items():(p/n).write_bytes(base64.b64decode(b))
for q in [p,*p.iterdir()]:os.chown(q,u.pw_uid,u.pw_gid)
subprocess.run(['systemd-run','--unit=adsb-async-producers-capture-20261109-v3','--uid=pi','-p','Nice=19','-p','AllowedCPUs=3','-p','CPUQuota=35%','-p','MemoryMax=512M','-p','RuntimeMaxSec=120','-p','RuntimeDirectory=adsb-async-producers-20261109-v3-capture','-p','RuntimeDirectoryPreserve=yes','env','PYTHONPATH=/home/pi/adsb-neural-rescue/src:'+str(p),'OPENBLAS_NUM_THREADS=1','OMP_NUM_THREADS=1','/home/pi/adsb-neural-rescue/.venv/bin/python',str(p/'capture.py'),'/run/adsb-async-producers-20261109-v3-capture/data'],check=True)
'''
print(subprocess.check_output(['ssh','adsb-rpi','sudo','python3','-'],input=code,text=True))
