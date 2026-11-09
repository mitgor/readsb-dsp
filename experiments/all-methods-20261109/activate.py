#!/usr/bin/env python3
"""Enable existing DSP implementations only; leave radio/feed/collector services running."""
import subprocess,base64,json,argparse
from pathlib import Path
HERE=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--attempt',default='v1',choices=['v1','v2','v3']);p.add_argument('--exclude',nargs='*',default=[],choices=['header','sic']);a=p.parse_args()
code=r'''
import pathlib,json,hashlib,os,time,subprocess,base64,sys
D=pathlib.Path('/var/lib/adsb-all-methods-20261109');assert not D.exists(),'Already activated: inspect instead of overwrite'
s=json.loads(pathlib.Path('/run/adsb-rescue/status.json').read_text());f=json.loads(pathlib.Path('/run/adsb-rescue/feed-status.json').read_text())
assert f['holdback_s']==3 and f['stock_connected'] and f['fr24_routed']
assert s['threads_alive'] and time.time()-s['updated_unix']<10
cfg=pathlib.Path('/etc/default/adsb-rescue.json');worker=pathlib.Path('/etc/default/adsb-rescue-workers.json')
w=json.loads(worker.read_text());assert w['optimized_dsp'] and w['optimized_v3'] and w['optimized_extended'] and w['sequence_acquisition']
for directory,archive in [(pathlib.Path('/var/lib/adsb-rescue'),s['archive']),(pathlib.Path('/var/lib/adsb-rescue/crc-verification'),s['crc_verification']['archive'])]:
 occupied=sum(p.stat().st_size for p in directory.glob('batch-*.jsonl.gz'));assert not archive.get('error') and occupied+archive['compressed_ram_bytes']+8*1048576<512*1048576, 'Insufficient RAM-save headroom'
env={**os.environ,'PYTHONPATH':'/home/pi/adsb-neural-rescue/src','OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1'}
subprocess.run(['runuser','-u','pi','--','env',*[k+'='+env[k] for k in ['PYTHONPATH','OPENBLAS_NUM_THREADS','OMP_NUM_THREADS']],'/home/pi/adsb-neural-rescue/.venv/bin/python','-c',"from rescue.pulse_live import production_model;production_model('/home/pi/adsb-neural-rescue/models/pulse-discriminant.json')"],check=True,timeout=30)
D.mkdir(mode=0o700);(D/'guard.py').write_bytes(base64.b64decode(GUARD));(D/'guard.py').chmod(0o700)
def save(name,j):
 p=D/name;p.write_text(json.dumps(j,indent=2)+'\n')
 with p.open('rb') as f:os.fsync(f.fileno())
pids={u:subprocess.check_output(['systemctl','show',u,'-p','MainPID','--value'],text=True).strip() for u in ['readsb','fr24feed','adsb-rescue-shadow','adsb-rescue-feed','adsb-far-capture']}
configs=[]
for p,updates in [(cfg,{k:True for k in json.loads(cfg.read_text())}),(worker,dict(sequence_enabled=True,acquisition_enabled=True))]:
 raw=p.read_bytes();st=p.stat();backup=p.name+'.before';(D/backup).write_bytes(raw);new=json.loads(raw);new.update(updates)
 if p==cfg:
  for k in EXCLUDED:new[k]=False
 data=(json.dumps(new,indent=2)+'\n').encode();configs.append(dict(path=str(p),backup=backup,original_sha256=hashlib.sha256(raw).hexdigest(),enabled_sha256=hashlib.sha256(data).hexdigest(),mode=st.st_mode&0o777,uid=st.st_uid,gid=st.st_gid));(D/(p.name+'.enabled')).write_bytes(data)
save('before-status.json',s);save('before-relay.json',f)
state=dict(activated_unix=time.time(),configs=configs,stock_loss={k:s['health']['local'].get(k,0) for k in ['samples_lost','samples_dropped']},pids_before=pids,expected_methods={**json.loads((D/(cfg.name+'.enabled')).read_text()),'sequence':True,'acquisition':True})
save('activation.json',state)
unit=pathlib.Path('/etc/systemd/system/adsb-all-methods-budget-20261109.service');timer=unit.with_suffix('.timer');assert not unit.exists() and not timer.exists()
unit.write_text('[Unit]\nDescription=Guard all-DSP three-second production budget\nAfter=adsb-rescue-shadow.service\n[Service]\nType=oneshot\nExecStart=/usr/bin/python3 '+str(D/'guard.py')+'\nTimeoutStartSec=120\nNice=19\n')
timer.write_text('[Unit]\nDescription=Check all-DSP latency and feeder health\n[Timer]\nOnBootSec=90\nOnActiveSec=10\nOnUnitInactiveSec=10\nAccuracySec=1\n[Install]\nWantedBy=timers.target\n')
subprocess.run(['systemctl','daemon-reload'],check=True)
# Apply both switches before one worker-only restart.
for r in configs:
 p=pathlib.Path(r['path']);assert hashlib.sha256(p.read_bytes()).hexdigest()==r['original_sha256'];tmp=p.with_suffix('.all-methods-tmp');tmp.write_bytes((D/(p.name+'.enabled')).read_bytes());tmp.chmod(r['mode']);os.chown(tmp,r['uid'],r['gid']);os.replace(tmp,p)
subprocess.run(['systemctl','enable','--now',timer.name],check=True)
try:subprocess.run(['systemctl','restart','adsb-rescue-shadow'],check=True,timeout=90)
except BaseException:
 sys.path.insert(0,str(D));import guard;guard.restore(state,'activation_restart_failure');raise
print(json.dumps(dict(activated_unix=state['activated_unix'],pids_before=pids,guard=timer.name,only_shadow_restarted=True)))
'''
guard=(HERE/'guard.py').read_text()
if a.attempt!='v1':
 code=code.replace('20261109','20261109-'+a.attempt);guard=guard.replace('20261109','20261109-'+a.attempt)
script='GUARD='+repr(base64.b64encode(guard.encode()).decode())+'\nEXCLUDED='+repr(a.exclude)+'\n'+code
print(subprocess.check_output(['ssh','adsb-rpi','sudo','python3','-'],input=script,text=True,timeout=150))
