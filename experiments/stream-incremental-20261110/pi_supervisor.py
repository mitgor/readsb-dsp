"""Finite isolated incremental comparison; never changes production controls."""
import os,json,subprocess,time,signal
from pathlib import Path
R=Path(os.environ['PHASE_BENCH_ROOT']);OUT=R/'results';OUT.mkdir(exist_ok=True)
exec((R/'protected-prefix.py').read_text(),globals())
base=snap();healthy(base,base);samples=[];child=None

def run(cmd,log):
 global child
 with (OUT/log).open('w') as f:
  child=subprocess.Popen([str(x) for x in cmd],stdout=f,stderr=subprocess.STDOUT,start_new_session=True);bad=0
  while child.poll() is None:
   time.sleep(3)
   try:s=snap();healthy(base,s);samples.append(s);bad=0
   except Exception:
    bad+=1
    if bad>=2:raise
  assert child.returncode==0,'Owned command failed: '+log
 healthy(base,snap())
try:
 flags=['c++','-O3','-std=c++20','-ffast-math','-mcpu=cortex-a76','-DSTATS_ENABLED=0','-DSTREAM1090_MIN_SNR=2.5','-DSTREAM1090_PREAMBLE_GATE=1','-DSTREAM1090_PREAMBLE_THRESHOLD=1.2','-fPIC','-I'+str(R/'native')]
 run(flags+['-c',R/'native/incremental.cpp','-o',R/'native/incremental.o'],'build.stdout')
 run(['c++','-shared',R/'native/incremental.o','-o',R/'native/incremental.so'],'link.stdout')
 py='/home/pi/adsb-neural-rescue/.venv/bin/python';batch=R/'bin/current-native.so';inc=R/'native/incremental.so'
 run([py,R/'code/controls.py','--batch',batch,'--incremental',inc,'--output',OUT/'controls.json','--fixture-dir',R/'fixtures'],'controls.stdout')
 run(['c++','-O1','-g','-std=c++20','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I'+str(R/'native'),R/'native/incremental.cpp',R/'code/sanitize.cpp','-ldl','-o',R/'bin/sanitize'],'sanitize-build.stdout')
 run([R/'bin/sanitize',inc,R/'fixtures/boundary.uc8'],'sanitize.stdout')
 run([py,R/'code/benchmark.py','--root',R,'--batch',batch,'--incremental',inc,'--output',OUT/'pi.json','--paced-windows','8'],'benchmark.stdout')
 (OUT/'protected.private.json').write_text(json.dumps({'before':base,'after':snap(),'samples':samples,'production_actions':[]},indent=2)+'\n')
except BaseException as e:
 if child is not None and child.poll() is None:os.killpg(child.pid,signal.SIGTERM)
 (OUT/'failed.private.json').write_text(json.dumps({'error':repr(e),'samples':samples},indent=2)+'\n');raise
