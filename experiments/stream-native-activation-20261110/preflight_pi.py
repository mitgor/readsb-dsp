"""Owned saved-RF adapter check. Never controls a production service."""
import os,json,subprocess,time,signal
from pathlib import Path
R=Path(os.environ['PHASE_BENCH_ROOT']);OUT=R/'results';OUT.mkdir(exist_ok=True)
exec((R/'protected-prefix.py').read_text(),globals())
base=snap();healthy(base,base);samples=[];child=None

def run(cmd,name):
 global child
 with (OUT/name).open('w') as f:
  child=subprocess.Popen([str(x) for x in cmd],stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
  while child.poll() is None:
   time.sleep(3);s=snap();healthy(base,s);samples.append(s)
  assert child.returncode==0,'Owned preflight failed: '+name
try:
 common=['c++','-O3','-std=c++20','-ffast-math','-mcpu=cortex-a76','-DSTATS_ENABLED=0','-DSTREAM1090_MIN_SNR=2.5','-DSTREAM1090_PREAMBLE_GATE=1','-DSTREAM1090_PREAMBLE_THRESHOLD=1.2','-fPIC']
 run(common+['-c',R/'native/native.cpp','-o',R/'native/native.o'],'compile.stdout')
 run(['c++','-shared',R/'native/native.o','-o',R/'native/libstream1090-native.so'],'link.stdout')
 run(['c++','-O2','-std=c++20',R/'fenv_load.cpp','-ldl','-o',R/'bin/fenv-load'],'fenv-build.stdout')
 run([R/'bin/fenv-load',R/'native/libstream1090-native.so'],'fenv.stdout')
 py='/home/pi/adsb-neural-rescue/.venv/bin/python'
 run([py,R/'code/adapter_parity.py','--source',R/'adapter','--prepared',R/'prepared','--original',R/'stream1090_method-original.py','--original-helper',R/'stream1090_shadow-original.py','--library',R/'native/libstream1090-native.so','--binary',R/'bin/stream1090','--output',OUT/'pi-adapter.json','--work',R/'test-work'],'parity.stdout')
 (OUT/'protected.private.json').write_text(json.dumps({'before':base,'after':snap(),'samples':samples,'production_actions':[]},indent=2))
except BaseException as e:
 if child is not None and child.poll() is None:os.killpg(child.pid,signal.SIGTERM)
 (OUT/'failed.private.json').write_text(json.dumps({'error':repr(e),'samples':samples},indent=2));raise
