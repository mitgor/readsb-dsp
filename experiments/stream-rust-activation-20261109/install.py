"""Deploy only the checksum-validated Stream ELF, keeping exact rollback bytes."""
from pathlib import Path
import json,hashlib,tarfile,base64,subprocess
H=Path(__file__).parent;P=Path('/Users/mit/Documents/!project/adsb-neural-rescue/results/rust-stream-20261109');D=P.parent/'stream-rust-activation-20261109';D.mkdir(exist_ok=False)
r=json.loads((P/'target-receipt.json').read_text());h=hashlib.sha256()
with (P/'target-evidence.private.tar').open('rb') as f:
 while b:=f.read(1024*1024):h.update(b)
assert h.hexdigest()==r['sha256'];proof=json.loads((P/'pi-final.json').read_text());health=json.loads((P/'protected-complete.private.json').read_text());assert proof['exact_full_output'] and health['error'] is None
with tarfile.open(P/'target-evidence.private.tar') as t:raw=t.extractfile('build-v3/stream-rust').read()
assert hashlib.sha256(raw).hexdigest()==proof['binary_hashes']['rust'];(D/'candidate').write_bytes(raw)
script='RAW='+repr(base64.b64encode(raw).decode())+'\nCONTROL='+repr((H/'control.py').read_text())+'\nPROOF='+repr(proof)+'\nHEALTH='+repr(health)+'\n'+r'''
from pathlib import Path
import json,base64,hashlib,os,time,subprocess
D=Path('/var/lib/adsb-stream-rust-20261109');B=Path('/home/pi/stream1090-shadow/build/stream1090');assert not D.exists() and not B.is_symlink()
assert hashlib.sha256(B.read_bytes()).hexdigest()==PROOF['binary_hashes']['original']
for p,h in HEALTH['after']['hashes'].items():assert hashlib.sha256(Path(p).read_bytes()).hexdigest()==h,'Production source/config/model changed '+p
D.mkdir(mode=0o700);(D/'control.py').write_text(CONTROL);(D/'original').write_bytes(B.read_bytes());(D/'candidate').write_bytes(base64.b64decode(RAW));assert hashlib.sha256((D/'candidate').read_bytes()).hexdigest()==PROOF['binary_hashes']['rust'];(D/'proof.json').write_text(json.dumps(PROOF)+'\n');st=B.stat();(D/'active.json').write_text(json.dumps(dict(state='prepared',prepared_unix=time.time(),before_sha256=PROOF['binary_hashes']['original'],after_sha256=PROOF['binary_hashes']['rust'],mode=st.st_mode&0o777,uid=st.st_uid,gid=st.st_gid,scope='Only Stream1090 ELF. Every live producer remains running; each next RF process execs the new binary.'))+'\n')
for p in D.iterdir():
 with p.open('rb') as f:os.fsync(f.fileno())
fd=os.open(D,os.O_RDONLY);os.fsync(fd);os.close(fd)
units={
'adsb-stream-rust-20261109.service':'[Unit]\nDescription=Guard Rust Stream1090 executable\n[Service]\nType=oneshot\nExecStart=/usr/bin/python3 '+str(D/'control.py')+' check\nTimeoutStartSec=180\nNice=19\n',
'adsb-stream-rust-20261109.timer':'[Unit]\nDescription=Monitor Rust Stream1090\n[Timer]\nOnBootSec=90\nOnActiveSec=10\nOnUnitInactiveSec=10\nAccuracySec=1\n[Install]\nWantedBy=timers.target\n',
'adsb-stream-rust-rollback-20261109.service':'[Unit]\nDescription=Restore previous Stream1090 ELF\n[Service]\nType=oneshot\nExecStart=/usr/bin/python3 '+str(D/'control.py')+' rollback --reason activation_unit_failed\nTimeoutStartSec=180\n',
'adsb-stream-rust-activate-20261109.service':'[Unit]\nDescription=Observe validated Stream1090 Rust hot swap\nOnFailure=adsb-stream-rust-rollback-20261109.service\n[Service]\nType=oneshot\nExecStart=/usr/bin/python3 '+str(D/'control.py')+' activate --observe 300\nTimeoutStartSec=600\n'}
for n,s in units.items():
 p=Path('/etc/systemd/system')/n;assert not p.exists();p.write_text(s)
subprocess.run(['systemctl','daemon-reload'],check=True);print('Prepared binary-only activation, exact original backup, no service restart.')
'''
print(subprocess.check_output(['ssh','adsb-rpi','sudo','python3','-'],input=script,text=True,timeout=60));subprocess.run(['ssh','adsb-rpi','sudo','systemctl','start','--no-block','adsb-stream-rust-activate-20261109'],check=True)
