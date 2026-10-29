#!/usr/bin/env python3
"""Guarded collector-only upgrade. Never restart stock/DSP/relay/feeders."""
import hashlib,json,os,runpy,shutil,subprocess,sys,time
from pathlib import Path
ROOT=Path('/home/pi/adsb-neural-rescue');stage=Path(sys.argv[1]);out=stage/'activation.json';mode=runpy.run_path('/usr/local/sbin/adsb-coherent-rust-mode');before=mode['snapshot']();mode['healthy'](before,before);capture=json.loads(Path('/run/adsb-far-capture/status.json').read_text());assert not capture['saving'] and not capture['error'];assert capture['disk_bytes']+capture['ram_bytes']+4*1024**2<5000000000
files=[ROOT/'src/rescue'/n for n in ['far_capture.py','far_training.py','capture_schedule.py','burst_ledger.py']]+[Path('/etc/default/adsb-far-capture.json')];backup=Path('/var/backups')/('adsb-far-training-'+str(time.time_ns()));backup.mkdir(mode=0o700);records={}
for i,p in enumerate(files):
 s=p.stat() if p.exists() else p.parent.stat();r=dict(existed=p.exists(),mode=(s.st_mode&0o777) if p.exists() else 0o644,uid=s.st_uid,gid=s.st_gid,name=f'file-{i}')
 if p.exists():shutil.copy2(p,backup/r['name']);r['sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
 records[str(p)]=r
(backup/'files.json').write_text(json.dumps(records,indent=2)+'\n');report=dict(before=before,capture_before=capture,backup=str(backup),samples=[],activated=False)
def save():out.write_text(json.dumps(report,indent=2)+'\n');(backup/'activation.json').write_text(json.dumps(report,indent=2)+'\n')
def atomic(p,data,r):
 temp=p.with_name(p.name+'.far-new');temp.write_bytes(data);os.chmod(temp,r['mode']);os.chown(temp,r['uid'],r['gid']);os.replace(temp,p)
def restore():
 subprocess.run(['systemctl','stop','adsb-far-capture'],check=True,timeout=120)
 for name,r in records.items():
  p=Path(name)
  if r['existed']:atomic(p,(backup/r['name']).read_bytes(),r)
  else:p.unlink(missing_ok=True)
 subprocess.run(['systemctl','start','adsb-far-capture'],check=True,timeout=30)
save()
try:
 # Stop only capture; its existing finally path bulk-saves its current RAM first.
 previous=set(Path('/var/lib/adsb-far-capture').glob('capture-*.tar'));subprocess.run(['systemctl','stop','adsb-far-capture'],check=True,timeout=120)
 assert subprocess.check_output(['systemctl','show','adsb-far-capture','-p','Result','--value'],text=True).strip()=='success'
 saved=set(Path('/var/lib/adsb-far-capture').glob('capture-*.tar'))-previous
 if capture['ram_bytes']:assert saved,'Old collector RAM did not produce a saved archive; stop upgrade'
 report['shutdown_saved_files']=[dict(path=str(p),bytes=p.stat().st_size) for p in saved]
 for p in files[:-1]:atomic(p,(stage/'src/rescue'/p.name).read_bytes(),records[str(p)])
 cfg=json.loads((backup/records[str(files[-1])]['name']).read_text());cfg.update(threshold_nm=180.,continuous_ram_bytes=128*1024**2);assert cfg['disk_limit_bytes']==5000000000 and cfg['flush_seconds']==43200 and cfg['ram_limit_bytes']==256*1024**2;atomic(files[-1],(json.dumps(cfg,indent=2)+'\n').encode(),records[str(files[-1])])
 switched=time.time();subprocess.run(['systemctl','start','adsb-far-capture'],check=True,timeout=30)
 for _ in range(45):
  s=json.loads(Path('/run/adsb-far-capture/status.json').read_text())
  if s.get('updated_unix',0)>switched and s.get('far_training',{}).get('enabled'):break
  time.sleep(1)
 else:raise RuntimeError('New capture never became ready')
 expected=dict(before);expected['pids']=dict(before['pids']);expected['pids']['adsb-far-capture']=mode['pid']('adsb-far-capture');start=time.time()
 while True:
  current=mode['snapshot']();mode['healthy'](expected,current);assert current['shadow_pid']==before['shadow_pid'],'Working decoder restarted';s=json.loads(Path('/run/adsb-far-capture/status.json').read_text());assert time.time()-s['updated_unix']<6 and not s['error'];assert s['config']['disk_limit_bytes']==5000000000 and s['config']['threshold_nm']==180 and s['capture_schedule']['enabled'] and s['far_training']['enabled'];assert s['ram_bytes']<=s['ram_limit_bytes'];report['samples'].append(dict(health=current,capture=s));save()
  if time.time()-start>=90:break
  time.sleep(10)
 assert s['counts'].get('tap_samples_received',0)>0 and s['packet_ledger']['streams']['stock']['connected'] and s['packet_ledger']['streams']['unified']['connected'];report['activated']=True;report['source_sha256']={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files};save();print(json.dumps(dict(activated=True,backup=str(backup),protected_pids_unchanged_except_collector=True,training=s['far_training']['counts'])))
except BaseException as error:
 report['error']=repr(error);save();restore();report['rolled_back']=True;save();raise
