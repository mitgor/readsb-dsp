"""Prepare exact C rollback and guarded optional activation after completed proof."""
from pathlib import Path
import subprocess,json,base64,hashlib
C=Path(__file__).resolve().parents[2];R=Path('/Users/mit/Documents/!project/adsb-neural-rescue');O=R/'results/rust-revalidate-20261109';proof=json.loads((O/'proof.json').read_text());assert proof['parity_passed'] and proof['stability_passed']
files={n:base64.b64encode(p.read_bytes()).decode() for n,p in {'_coherent.so':C/'experiments/rust-live/.work/pi-release/_coherent.so','_coherent_pair.so':C/'experiments/rust-live/.work/pi-release/_coherent_pair.so','_acquisition_rust.so':C/'experiments/rust-methods-live/.work/pi-candidate/_acquisition_rust.so','coherent_extended_opt.py':C/'src/rescue/coherent_extended_opt.py'}.items()}
control=(C/'experiments/rust-revalidate-20261109/control.py').read_text();policy=(C/'experiments/rust-revalidate-20261109/policy.py').read_text()
code=r'''
from pathlib import Path
import json,hashlib,base64,os,subprocess
P=Path;D=P('/var/lib/adsb-rust-kernels-20261109');assert not D.exists();ROOT=P('/home/pi/adsb-neural-rescue/src/rescue');before=PROOF['validation_snapshot'];assert PROOF['parity_passed'] and PROOF['stability_passed']
for p,h in before['hashes'].items():assert hashlib.sha256(P(p).read_bytes()).hexdigest()==h,'Validated source/config/model changed: '+p
for name,h in PROOF['current_reference_hashes'].items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==h
D.mkdir(mode=0o700);(D/'control.py').write_text(CONTROL);(D/'policy.py').write_text(POLICY);(D/'proof.json').write_text(json.dumps(PROOF,indent=2)+'\n');records=[]
for i,(name,b64) in enumerate(FILES.items()):
 p=ROOT/name;assert not p.is_symlink();raw=base64.b64decode(b64);assert hashlib.sha256(raw).hexdigest()==PROOF['candidate_hashes'][name];candidate=str(i)+'.candidate';(D/candidate).write_bytes(raw);meta=p.stat() if p.exists() else p.parent.stat();old=None;oldsha=None
 if p.exists():old=str(i)+'.before';(D/old).write_bytes(p.read_bytes());oldsha=hashlib.sha256(p.read_bytes()).hexdigest()
 records.append(dict(path=str(p),before=old,before_sha256=oldsha,after_sha256=hashlib.sha256(raw).hexdigest(),candidate=candidate,mode=meta.st_mode&0o777 if old else 0o755,uid=meta.st_uid,gid=meta.st_gid))
oldenabled=subprocess.check_output(['systemctl','is-enabled','adsb-async-live-20261109.timer'],text=True).strip()=='enabled';legacy={u:subprocess.run(['systemctl','is-enabled','--quiet',u]).returncode==0 for u in ['adsb-coherent-rust-guard.service','adsb-rust-methods-guard.service']}
state=dict(state='prepared',files=records,previous_guard_enabled=oldenabled,legacy_guards_enabled=legacy,proof_sha256=hashlib.sha256((D/'proof.json').read_bytes()).hexdigest(),prepared_unix=__import__('time').time(),scope='Coherent ordinary/pair Rust and acquisition scorer/selector only. EM, sequence, pulse, Stream1090, models/configs/flags unchanged.')
(D/'active.json').write_text(json.dumps(state,indent=2)+'\n')
for p in D.iterdir():
 with p.open('rb') as f:os.fsync(f.fileno())
fd=os.open(D,os.O_RDONLY);os.fsync(fd);os.close(fd)
units={
'adsb-rust-kernels-20261109.service':'[Unit]\nDescription=Guard Rust coherent/acquisition kernels\n[Service]\nType=oneshot\nExecStart=/usr/bin/python3 '+str(D/'control.py')+' check\nTimeoutStartSec=180\nNice=19\n',
'adsb-rust-kernels-20261109.timer':'[Unit]\nDescription=Monitor Rust kernel release and progress\n[Timer]\nOnBootSec=90\nOnActiveSec=10\nOnUnitInactiveSec=10\nAccuracySec=1\n[Install]\nWantedBy=timers.target\n',
'adsb-rust-kernels-rollback-20261109.service':'[Unit]\nDescription=Restore C kernels after activation failure\n[Service]\nType=oneshot\nExecStart=/usr/bin/python3 '+str(D/'control.py')+' rollback --reason activation_unit_failed\nTimeoutStartSec=180\n',
'adsb-rust-kernels-activate-20261109.service':'[Unit]\nDescription=Validated Rust kernel activation with initial stability observation\nOnFailure=adsb-rust-kernels-rollback-20261109.service\n[Service]\nType=oneshot\nExecStart=/usr/bin/python3 '+str(D/'control.py')+' activate --observe 300\nTimeoutStartSec=600\n'}
for n,text in units.items():
 p=P('/etc/systemd/system')/n;assert not p.exists();p.write_text(text)
subprocess.run(['systemctl','daemon-reload'],check=True)
# Preserve historical rollback records; add explicit successor pointers instead.
for dirname in ['/var/lib/adsb-coherent-rust','/var/lib/adsb-rust-methods']:
 p=P(dirname)/'successor-20261109.json';assert not p.exists();p.write_text(json.dumps(dict(current_release=str(D/'active.json'),status_command='sudo python3 '+str(D/'control.py')+' status'))+'\n')
print(json.dumps(dict(prepared=True,backup=str(D),files=[r['path'] for r in records])))
'''
script='PROOF='+repr(proof)+'\nFILES='+repr(files)+'\nCONTROL='+repr(control)+'\nPOLICY='+repr(policy)+'\n'+code
print(subprocess.check_output(['ssh','adsb-rpi','sudo','python3','-'],input=script,text=True,timeout=60))
subprocess.run(['ssh','adsb-rpi','sudo','systemctl','start','--no-block','adsb-rust-kernels-activate-20261109.service'],check=True)
