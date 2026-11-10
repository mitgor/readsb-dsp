"""Finite target replay; supervisor can terminate only its isolated child."""
import os,json,subprocess,time,signal,hashlib
from pathlib import Path
R=Path(os.environ['PHASE_BENCH_ROOT']);OUT=R/'results';OUT.mkdir(exist_ok=True)
exec((R/'protected-prefix.py').read_text(),globals())
base=snap();healthy(base,base);samples=[];child=None
# Verify all staged inputs, including exact current production library copies.
for name,digest in json.loads((R/'stage-manifest.json').read_text()).items():assert hashlib.sha256((R/name).read_bytes()).hexdigest()==digest,name
for x in (R/'runtime/rescue').iterdir():
 live=Path('/home/pi/adsb-neural-rescue/src/rescue')/x.name
 if x.suffix in ['.py','.so'] and not x.name.startswith('._'):assert hashlib.sha256(x.read_bytes()).hexdigest()==hashlib.sha256(live.read_bytes()).hexdigest(),x.name
assert hashlib.sha256((R/'bin/batch.so').read_bytes()).hexdigest()=='70d715dabe1ea2c6623002c9b47d4cb94f1b8a25197ba3f0d203b7b872e86103'
# This is the previously activated native baseline. Production's guard has
# already restored the executable; do not change that choice for a benchmark.
live_mode=Path('/etc/default/adsb-stream1090-native.json').read_bytes()

def run(cmd,log):
 global child
 with (OUT/log).open('w') as f:
  child=subprocess.Popen([str(x) for x in cmd],stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
  while child.poll() is None:
   time.sleep(2);s=snap();healthy(base,s);samples.append(s)
  assert child.returncode==0,'Owned command failed: '+log
 healthy(base,snap())
try:
 py='/home/pi/adsb-neural-rescue/.venv/bin/python'
 run([py,R/'code/controls.py','--dedup',R/'bin/dedup.so','--output',OUT/'controls.json'],'controls.stdout')
 run([py,R/'code/benchmark.py','--capture',R/'capture','--batch',R/'bin/batch.so','--incremental',R/'bin/incremental.so','--dedup',R/'bin/dedup.so','--output',OUT/'pi.json'],'benchmark.stdout')
 after=snap();healthy(base,after);assert Path('/etc/default/adsb-stream1090-native.json').read_bytes()==live_mode
 (OUT/'health.private.json').write_text(json.dumps(dict(before=base,after=after,samples=samples,production_actions=[],hardware=Path('/proc/device-tree/model').read_bytes().rstrip(b'\0').decode()),indent=2)+'\n')
except BaseException as e:
 if child is not None and child.poll() is None:os.killpg(child.pid,signal.SIGTERM)
 (OUT/'failed.private.json').write_text(json.dumps(dict(error=repr(e),before=base,samples=samples,production_actions=[]),indent=2)+'\n');raise
