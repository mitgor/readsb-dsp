"""After successful C/Rust replay, compare rebuilt optimized C in the same pipeline."""
from pathlib import Path
import subprocess,json,time,io,tarfile,shlex
H=Path(__file__).parent;b=io.BytesIO()
with tarfile.open(fileobj=b,mode='w') as t:
 for n in ['pi_optimized.sh','run_optimized.py','protected_health.py']:t.add(H/n,arcname=n)
code='''from pathlib import Path
import tarfile,sys
D=Path('/dev/shm/adsb-rust-sequence-20261109/code-optimized');D.mkdir()
with tarfile.open(fileobj=sys.stdin.buffer,mode='r|') as t:
 for m in t:
  assert m.isfile() and len(Path(m.name).parts)==1
  p=D/m.name;p.write_bytes(t.extractfile(m).read());p.chmod(m.mode)
'''
subprocess.run(['ssh','adsb-rpi','sudo python3 -c '+shlex.quote(code)],input=b.getvalue(),check=True)
end=time.monotonic()+600
while True:
 code='''from pathlib import Path
import subprocess,json
D=Path('/dev/shm/adsb-rust-sequence-20261109');active=subprocess.run(['systemctl','is-active','--quiet','adsb-rust-sequence-20261109']).returncode==0
if not active:
 h=json.loads((D/'protected.private.json').read_text());assert h['error'] is None and h['before']==h['after'];assert (D/'full-rust.private.json').exists()
print(json.dumps({'active':active}))
'''
 x=json.loads(subprocess.check_output(['ssh','adsb-rpi','sudo','python3','-'],input=code,text=True))
 if not x['active']:break
 assert time.monotonic()<end;time.sleep(5)
subprocess.run(['ssh','adsb-rpi','sudo','systemd-run','--unit=adsb-rust-sequence-opt-20261109','--property=WorkingDirectory=/dev/shm/adsb-rust-sequence-20261109','--property=Nice=19','--property=AllowedCPUs=3','--property=CPUQuota=35%','--property=MemoryMax=1G','--property=RuntimeMaxSec=800','/usr/bin/python3','/dev/shm/adsb-rust-sequence-20261109/code-optimized/run_optimized.py','/dev/shm/adsb-rust-sequence-20261109'],check=True)
