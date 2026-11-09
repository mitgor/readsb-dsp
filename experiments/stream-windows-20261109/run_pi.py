"""Owned finite lower-priority benchmark; abort only child on protected health change."""
import subprocess,json,time,sys,os,signal
from pathlib import Path
from protected_health import snapshot
D=Path(sys.argv[1]);before=snapshot();commands=[['baseline.py','--stage',str(D),'--output',str(D/'pi-baseline.private.json')],['bench_stream.py','--input',str(D/'input'),'--binary',str(D/'stream1090'),'--output',str(D/'pi-stream.private.json'),'--pace']];
if '--stream-only' in sys.argv:commands=[['bench_stream.py','--input',str(D/'input'),'--binary',str(D/'stream1090'),'--output',str(D/'pi-stream-unique-100.private.json'),'--pace','--cores','100']]
checks=[];error=None
try:
 for cmd in commands:
  with (D/(cmd[0]+'.log')).open('w') as log:
   child=subprocess.Popen(['/home/pi/adsb-neural-rescue/.venv/bin/python',str(D/'code'/cmd[0]),*cmd[1:]],stdout=log,stderr=log,start_new_session=True,env={**os.environ,'PYTHONPATH':str(D/'src'),'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1'});deadline=time.monotonic()+700
   try:
    while child.poll() is None:
     time.sleep(3);current=snapshot();assert current==before,'Protected state changed'
     s=json.loads(Path('/run/adsb-rescue/status.json').read_text());processing=(s.get('max_recent_processing_s') or 0)+(s.get('stream1090',{}).get('last_wall_s') or 0);checks.append(dict(unix=time.time(),processing_s=processing));assert processing<2.3,'Production safety margin'
     assert time.monotonic()<deadline,'Finite benchmark timeout'
    assert child.returncode==0,(cmd[0],child.returncode)
   finally:
    if child.poll() is None:os.killpg(child.pid,signal.SIGTERM);child.wait(timeout=20)
except BaseException as e:error=repr(e);raise
finally:
 (D/'protected.private.json').write_text(json.dumps(dict(before=before,after=snapshot(),checks=checks,error=error),indent=2)+'\n')
