"""Install one exact Pi-validated pulse ELF, preserving exact C rollback bytes."""
from pathlib import Path
import json,hashlib,subprocess,base64
H=Path(__file__).parent;P=Path('/Users/mit/Documents/!project/adsb-neural-rescue/results/rust-pulse-20261110');O=P.parent/'pulse-rust-activation-20261110';proof=json.loads((P/'proof.json').read_text());results=json.loads((P/'target-results.private.json').read_text());assert proof['parity_passed'] and proof['safe_to_activate'];raw=(P/'candidate.so').read_bytes();assert hashlib.sha256(raw).hexdigest()==proof['libraries']['rust'];assert not O.exists() or not list(O.iterdir());O.mkdir(exist_ok=True);(O/'candidate.so').write_bytes(raw)
script='RAW='+repr(base64.b64encode(raw).decode())+'\nPROOF='+repr(proof)+'\nHEALTH='+repr(results['protected.private.json'])+'\nCONTROL='+repr((H/'control.py').read_text())+'\n'+r'''
from pathlib import Path
import json,hashlib,base64,os,subprocess,time
D=Path('/var/lib/adsb-pulse-rust-20261110');p=Path('/home/pi/adsb-neural-rescue/src/rescue/_pulse_discriminant.so');assert not D.exists() and not p.is_symlink()
for name,h in HEALTH['after']['hashes'].items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==h,'Validated source/model/config changed '+name
assert hashlib.sha256(p.read_bytes()).hexdigest()==PROOF['libraries']['actual'];assert hashlib.sha256(Path('/home/pi/adsb-neural-rescue/models/pulse-discriminant.json').read_bytes()).hexdigest()==PROOF['model_sha256']
D.mkdir(mode=0o700);(D/'control.py').write_text(CONTROL);(D/'proof.json').write_text(json.dumps(PROOF,indent=2)+'\n');(D/'original.so').write_bytes(p.read_bytes());candidate=base64.b64decode(RAW);assert hashlib.sha256(candidate).hexdigest()==PROOF['libraries']['rust'];(D/'candidate.so').write_bytes(candidate);meta=p.stat();r=dict(path=str(p),before='original.so',before_sha256=PROOF['libraries']['actual'],after_sha256=PROOF['libraries']['rust'],candidate='candidate.so',mode=meta.st_mode&0o777,uid=meta.st_uid,gid=meta.st_gid);(D/'active.json').write_text(json.dumps(dict(state='prepared',prepared_unix=time.time(),files=[r],scope='Only scalar/bank pulse-discriminant library. Existing Python loader/model and all other algorithms preserved.'))+'\n')
for f in D.iterdir():
 with f.open('rb') as h:os.fsync(h.fileno())
fd=os.open(D,os.O_RDONLY);os.fsync(fd);os.close(fd)
units={
'adsb-pulse-rust-20261110.service':'[Unit]\nDescription=Guard Rust pulse discriminant\n[Service]\nType=oneshot\nExecStart=/usr/bin/python3 '+str(D/'control.py')+' check\nTimeoutStartSec=180\nNice=19\n',
'adsb-pulse-rust-20261110.timer':'[Unit]\nDescription=Monitor Rust pulse progress and health\n[Timer]\nOnBootSec=90\nOnActiveSec=5\nOnUnitInactiveSec=5\nAccuracySec=1\n[Install]\nWantedBy=timers.target\n',
'adsb-pulse-rust-rollback-20261110.service':'[Unit]\nDescription=Restore exact C pulse library\n[Service]\nType=oneshot\nExecStart=/usr/bin/python3 '+str(D/'control.py')+' rollback --reason activation_unit_failed\nTimeoutStartSec=180\n',
'adsb-pulse-rust-activate-20261110.service':'[Unit]\nDescription=Activate validated Rust pulse filter\nOnFailure=adsb-pulse-rust-rollback-20261110.service\n[Service]\nType=oneshot\nExecStart=/usr/bin/python3 '+str(D/'control.py')+' activate --observe 300\nTimeoutStartSec=600\n'}
for n,text in units.items():
 f=Path('/etc/systemd/system')/n;assert not f.exists();f.write_text(text)
subprocess.run(['systemctl','daemon-reload'],check=True);print('Prepared one validated pulse library with exact C rollback; no settings changes.')
'''
print(subprocess.check_output(['ssh','adsb-rpi','sudo','python3','-'],input=script,text=True,timeout=60));subprocess.run(['ssh','adsb-rpi','sudo','systemctl','start','--no-block','adsb-pulse-rust-activate-20261110'],check=True)
