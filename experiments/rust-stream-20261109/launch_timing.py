"""Wait for clean owned final experiment, then start protected production-ELF timing."""
from pathlib import Path
import io,tarfile,subprocess,shlex,json,time
H=Path(__file__).parent;b=io.BytesIO()
with tarfile.open(fileobj=b,mode='w') as t:
 for n in ['timing.py','pi_timing.sh','run_timing.py','protected_health.py']:t.add(H/n,arcname=n)
code='''from pathlib import Path
import tarfile,sys
D=Path('/dev/shm/adsb-rust-stream-20261109/code-timing');D.mkdir()
with tarfile.open(fileobj=sys.stdin.buffer,mode='r|') as t:
 for m in t:
  assert m.isfile() and len(Path(m.name).parts)==1
  p=D/m.name;p.write_bytes(t.extractfile(m).read());p.chmod(m.mode)
'''
subprocess.run(['ssh','adsb-rpi','sudo python3 -c '+shlex.quote(code)],input=b.getvalue(),check=True)
end=time.monotonic()+600
while True:
 code='''import json,subprocess
from pathlib import Path
D=Path('/dev/shm/adsb-rust-stream-20261109');active=subprocess.run(['systemctl','is-active','--quiet','adsb-rust-stream-final-20261109']).returncode==0
if not active:
 p=json.loads((D/'protected-final.private.json').read_text());assert p['error'] is None and p['before']==p['after'];assert json.loads((D/'pi-final.json').read_text())['exact_full_output']
print(json.dumps({'active':active}))
'''
 x=json.loads(subprocess.check_output(['ssh','adsb-rpi','sudo','python3','-'],input=code,text=True))
 if not x['active']:break
 assert time.monotonic()<end,'Finite wait';time.sleep(10)
print('Final comparison closed cleanly; starting actual-production timing.',flush=True)
subprocess.run(['ssh','adsb-rpi','sudo','systemd-run','--unit=adsb-rust-stream-timing-20261109','--property=WorkingDirectory=/dev/shm/adsb-rust-stream-20261109','--property=Nice=19','--property=AllowedCPUs=3','--property=CPUQuota=35%','--property=MemoryMax=1G','--property=RuntimeMaxSec=1700','/usr/bin/python3','/dev/shm/adsb-rust-stream-20261109/code-timing/run_timing.py','/dev/shm/adsb-rust-stream-20261109'],check=True)
