"""Finite isolated target build/tests; owns only its subprocess group and tmpfs."""
import os,json,subprocess,time,signal,hashlib
from pathlib import Path
R=Path(os.environ['PHASE_BENCH_ROOT']);OUT=R/'results';OUT.mkdir(exist_ok=True)
exec((R/'protected-prefix.py').read_text(),globals())
base=snap();healthy(base,base);samples=[];child=None
for name,digest in json.loads((R/'stage-manifest.json').read_text()).items():assert hashlib.sha256((R/name).read_bytes()).hexdigest()==digest,name
for x in (R/'runtime/rescue').iterdir():
 live=Path('/home/pi/adsb-neural-rescue/src/rescue')/x.name
 if x.suffix in ['.py','.so'] and not x.name.startswith('._'):assert hashlib.sha256(x.read_bytes()).hexdigest()==hashlib.sha256(live.read_bytes()).hexdigest(),x.name
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
 for name,digest in [('rustc.tar.xz','acdcdfe09ae1f103aa9a2b7f88903a9588bc2e99288af10e6fbf5514e2e49f25'),('rust-std.tar.xz','e25668477083d6a9ddb87b9beb9c00742225f38233ccb4bfba3afa7a07427f52')]:assert hashlib.sha256((R/name).read_bytes()).hexdigest()==digest,name
 (R/'toolchain').mkdir(exist_ok=True);(R/'tmp').mkdir(exist_ok=True)
 run(['tar','-xJf',R/'rustc.tar.xz','--strip-components=2','-C',R/'toolchain','rustc-1.99.1-aarch64-unknown-linux-gnu/rustc'],'compiler-extract.stdout')
 run(['tar','-xJf',R/'rust-std.tar.xz','--strip-components=2','-C',R/'toolchain','rust-std-1.99.1-aarch64-unknown-linux-gnu/rust-std-aarch64-unknown-linux-gnu'],'std-extract.stdout')
 rust=R/'toolchain/bin/rustc';run([rust,'--edition=2021','--crate-type','cdylib','-C','opt-level=3','-C','panic=abort',R/'code/native_admission.rs','-o',R/'bin/admission.so'],'build.stdout')
 py='/home/pi/adsb-neural-rescue/.venv/bin/python'
 run([py,R/'code/shared_energy_tests.py'],'shared-controls.stdout')
 run([py,R/'code/native_admission_tests.py','--library',R/'bin/admission.so','--capture',R/'capture','--output',OUT/'admission-controls.json'],'admission-controls.stdout')
 run([py,R/'code/completion_bridge_tests.py','--library',R/'bin/admission.so','--output',OUT/'completion-controls.json'],'completion-controls.stdout')
 run([py,R/'code/cold_start_tests.py'],'cold-controls.stdout')
 run([py,R/'code/benchmark.py','--capture',R/'capture','--batch',R/'bin/batch.so','--incremental',R/'bin/incremental.so','--dedup',R/'bin/dedup.so','--admission',R/'bin/admission.so','--repeats','2','--output',OUT/'pi.json'],'benchmark.stdout')
 after=snap();healthy(base,after);assert Path('/etc/default/adsb-stream1090-native.json').read_bytes()==live_mode
 (OUT/'health.private.json').write_text(json.dumps(dict(before=base,after=after,samples=samples,production_actions=[],hardware=Path('/proc/device-tree/model').read_bytes().rstrip(b'\0').decode()),indent=2)+'\n')
except BaseException as e:
 if child is not None and child.poll() is None:os.killpg(child.pid,signal.SIGTERM)
 (OUT/'failed.private.json').write_text(json.dumps(dict(error=repr(e),before=base,samples=samples,production_actions=[]),indent=2)+'\n');raise
