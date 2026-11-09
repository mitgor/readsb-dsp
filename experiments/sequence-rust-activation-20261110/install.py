"""Install the exact tested sequence ELF and tested copied-loader overlay only."""
from pathlib import Path
import json,hashlib,tarfile,base64,subprocess
H=Path(__file__).parent;R=Path('/Users/mit/Documents/!project/adsb-neural-rescue/results');P=R/'rust-sequence-20261109';O=R/'sequence-rust-activation-20261110';O.mkdir(exist_ok=False);receipt=json.loads((P/'target-receipt.json').read_text());proof=json.loads((P/'proof.json').read_text());assert proof['parity_passed'] and proof['paired_full_pipeline']['all_raw_and_guarded_events_exact'];archive=P/'target-evidence.private.tar';h=hashlib.sha256()
with archive.open('rb') as f:
 while b:=f.read(1024*1024):h.update(b)
assert h.hexdigest()==receipt['sha256']
with tarfile.open(archive) as t:
 library=t.extractfile('build/rust.so').read();loader=t.extractfile('candidate/src/rescue/pipeline_v3.py').read();old=t.extractfile('reference/src/rescue/pipeline_v3.py').read();model_sha=hashlib.sha256(t.extractfile('models/pulse-sequence.json').read()).hexdigest();health=json.load(t.extractfile('protected-paired-v2.private.json'))
assert hashlib.sha256(library).hexdigest()==proof['library_sha256']['rust'];assert health['error'] is None;files={'_sequence_rust.so':library,'pipeline_v3.py':loader}
for n,b in files.items():(O/n).write_bytes(b)
script='FILES='+repr({n:base64.b64encode(b).decode() for n,b in files.items()})+'\nOLD_LOADER_SHA='+repr(hashlib.sha256(old).hexdigest())+'\nMODEL_SHA='+repr(model_sha)+'\nHEALTH='+repr(health)+'\nPROOF='+repr(proof)+'\nCONTROL='+repr((H/'control.py').read_text())+'\n'+r'''
from pathlib import Path
import json,hashlib,os,subprocess,base64,time
D=Path('/var/lib/adsb-sequence-rust-20261110');ROOT=Path('/home/pi/adsb-neural-rescue/src/rescue');assert not D.exists();assert not (ROOT/'_sequence_rust.so').exists()
for p,h in HEALTH['after']['hashes'].items():assert hashlib.sha256(Path(p).read_bytes()).hexdigest()==h,'Validated production source/model/config changed: '+p
assert hashlib.sha256(Path('/home/pi/adsb-neural-rescue/models/pulse-sequence.json').read_bytes()).hexdigest()==MODEL_SHA
assert hashlib.sha256((ROOT/'pipeline_v3.py').read_bytes()).hexdigest()==OLD_LOADER_SHA
assert hashlib.sha256((ROOT/'_pipeline_v3.so').read_bytes()).hexdigest()==PROOF['library_sha256']['actual']
D.mkdir(mode=0o700);(D/'control.py').write_text(CONTROL);(D/'proof.json').write_text(json.dumps(PROOF,indent=2)+'\n');records=[]
for i,(name,b64) in enumerate(FILES.items()):
 p=ROOT/name;assert not p.is_symlink();raw=base64.b64decode(b64);new=str(i)+'.candidate';(D/new).write_bytes(raw);previous=None;oldsha=None;meta=p.stat() if p.exists() else (ROOT/'pipeline_v3.py').stat()
 if p.exists():previous=str(i)+'.before';(D/previous).write_bytes(p.read_bytes());oldsha=hashlib.sha256(p.read_bytes()).hexdigest()
 records.append(dict(path=str(p),before=previous,before_sha256=oldsha,after_sha256=hashlib.sha256(raw).hexdigest(),candidate=new,mode=meta.st_mode&0o777,uid=meta.st_uid,gid=meta.st_gid))
(D/'active.json').write_text(json.dumps(dict(state='prepared',files=records,prepared_unix=time.time(),scope='Only pulse-sequence prepare/batch loader and Rust library. Optimized C other helpers and all existing Rust kernels preserved.'))+'\n')
for p in D.iterdir():
 with p.open('rb') as f:os.fsync(f.fileno())
fd=os.open(D,os.O_RDONLY);os.fsync(fd);os.close(fd)
units={
'adsb-sequence-rust-20261110.service':'[Unit]\nDescription=Guard Rust pulse sequence\n[Service]\nType=oneshot\nExecStart=/usr/bin/python3 '+str(D/'control.py')+' check\nTimeoutStartSec=180\nNice=19\n',
'adsb-sequence-rust-20261110.timer':'[Unit]\nDescription=Monitor Rust sequence progress and health\n[Timer]\nOnBootSec=90\nOnActiveSec=5\nOnUnitInactiveSec=5\nAccuracySec=1\n[Install]\nWantedBy=timers.target\n',
'adsb-sequence-rust-rollback-20261110.service':'[Unit]\nDescription=Restore exact C sequence loader\n[Service]\nType=oneshot\nExecStart=/usr/bin/python3 '+str(D/'control.py')+' rollback --reason activation_unit_failed\nTimeoutStartSec=180\n',
'adsb-sequence-rust-activate-20261110.service':'[Unit]\nDescription=Activate validated Rust pulse sequence\nOnFailure=adsb-sequence-rust-rollback-20261110.service\n[Service]\nType=oneshot\nExecStart=/usr/bin/python3 '+str(D/'control.py')+' activate --observe 300\nTimeoutStartSec=600\n'}
for name,text in units.items():
 p=Path('/etc/systemd/system')/name;assert not p.exists();p.write_text(text)
subprocess.run(['systemctl','daemon-reload'],check=True);print('Prepared exact tested loader/ELF with original rollback bytes.')
'''
print(subprocess.check_output(['ssh','adsb-rpi','sudo','python3','-'],input=script,text=True,timeout=60));subprocess.run(['ssh','adsb-rpi','sudo','systemctl','start','--no-block','adsb-sequence-rust-activate-20261110'],check=True)
