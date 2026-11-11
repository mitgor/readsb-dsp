#!/usr/bin/python3
"""Persistent guarded arrival-order activation. No SDR, models or collector changes."""
import argparse,hashlib,json,os,runpy,shutil,subprocess,time,fcntl
from pathlib import Path
G=runpy.run_path('/usr/local/sbin/adsb-stream1090-lowlatency-mode')
ROOT=Path('/home/pi/adsb-neural-rescue/src/rescue')
STATE=Path('/var/lib/adsb-arrival-relay/active.json');CFG=Path('/etc/default/adsb-relay-arrival.json')
RUN=Path('/run/adsb-arrival-relay-guard.json')
NAMES=['feed.py','arrival_feed.py','arrival_output.py','async_dedup.py','async_immediate.py']
read,save,sha=G['read'],G['save'],G['sha']
def atomic_copy(source, destination):
 old=destination.stat() if destination.exists() else (ROOT/'feed.py').stat()
 G['atomic'](destination,source.read_bytes(),dict(uid=old.st_uid,gid=old.st_gid,mode=old.st_mode&0o777))
def ctl(*args):subprocess.run(['systemctl',*args],check=True,timeout=45)
def update_native_pid():
 st=read(G['STATE'])
 if st['state']=='active':
  st['before']['pids']['adsb-rescue-feed']=G['snapshot']()['pids']['adsb-rescue-feed'];save(G['STATE'],st)
def ready():
 s=read('/run/adsb-rescue/feed-status.json');assert time.time()-s['updated_unix']<6 and s['stock_connected'],'Relay readiness'
 return s
def check(st):
 snap=G['snapshot']();G['healthy'](st['before'],snap);G['capture']()
 status=ready();assert status['holdback_s']==0 and not status.get('fault'),'Arrival output unhealthy'
 for name,h in st['installed'].items():assert sha(ROOT/name)==h,'Relay component changed: '+name
 assert sha(CFG)==st['config_sha256'],'Arrival config changed'
 return snap,status
def rollback(reason):
 if not STATE.exists():return
 st=read(STATE)
 if st['state'] not in ['active','activating']:return
 save(CFG,dict(enabled=False,reason=reason))
 # Restore the exact original relay; preserve unrelated concurrent edits.
 p=ROOT/'feed.py';rec=st['original_feed_sha256']
 if sha(p) not in [st['installed']['feed.py'],rec]:
  st.update(state='rollback_conflict',reason=reason);save(STATE,st);return
 atomic_copy(Path(st['backup'])/'feed.py',p);ctl('restart','adsb-rescue-feed')
 st.update(state='rolled_back',reason=reason,rolled_back_unix=time.time());save(STATE,st)
 update_native_pid();save(RUN,dict(state='rolled_back',reason=reason,updated_unix=time.time()))
def guard():
 if not STATE.exists():return
 st=read(STATE)
 if st['state']=='activating':
  if time.time()>st['deadline']:rollback('Activation readiness deadline')
  return
 if st['state']!='active':return
 try:
  native=read(G['STATE'])
  if native['state']=='activating' and time.time()<native['deadline']:
   relay=ready();G['capture']()
   save(RUN,dict(state='waiting_for_authorized_native_startup',updated_unix=time.time(),native_deadline=native['deadline'],stock_connected=relay['stock_connected']))
   return

  # Reboot alone changes service identities. Require the same config/components,
  # then establish new process baselines after normal services have become ready.
  boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
  rebooted=boot!=st['boot']
  if rebooted:
   current=G['snapshot']();G['healthy'](current,current)
   assert current['config_sha256']==st['before']['config_sha256'],'Configuration changed on boot'
   st.update(before=current,boot=boot)
  snap,status=check(st)
  if st.get('bad_checks',0) or rebooted:
   st['bad_checks']=0;save(STATE,st)
  save(RUN,dict(state='active',updated_unix=time.time(),holdback_s=0,stock_bytes=status['counts'].get('stock_bytes_relayed',0),extras=status['counts'].get('dsp_frames_relayed',0),dsp_status_age_s=time.time()-snap['updated_unix'],relay_status_age_s=time.time()-snap['feed_updated_unix']))
 except Exception as exc:
  st['bad_checks']=st.get('bad_checks',0)+1;st['error']=repr(exc);save(STATE,st)
  save(RUN,dict(state='unhealthy',updated_unix=time.time(),bad_checks=st['bad_checks'],error=repr(exc)))
  if st['bad_checks']>=2:rollback('Guard: '+repr(exc))
def activate(stage,observe):
 assert not STATE.exists() or read(STATE)['state']=='rolled_back','Arrival activation already present'
 before=G['snapshot']();G['healthy'](before,before);G['capture']();manifest=read(stage/'manifest.json')
 for name in NAMES:assert sha(stage/'arrival'/name)==manifest['arrival/'+name],name
 backup=Path('/var/backups')/('adsb-arrival-'+str(time.time_ns()));backup.mkdir(mode=0o700)
 shutil.copy2(ROOT/'feed.py',backup/'feed.py')
 st=dict(state='activating',before=before,boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),backup=str(backup),original_feed_sha256=sha(ROOT/'feed.py'),installed={name:sha(stage/'arrival'/name) for name in NAMES},deadline=time.time()+90)
 save(STATE,st)
 try:
  ctl('stop','adsb-stream1090-lowlatency-guard.timer','adsb-stream1090-lowlatency-guard.service')
  for name in NAMES:atomic_copy(stage/'arrival'/name,ROOT/name)
  save(CFG,dict(enabled=True,policy='arrival_order',dedup_seconds=5,max_extra_age_seconds=3));st['config_sha256']=sha(CFG);save(STATE,st)
  ctl('restart','adsb-rescue-feed');end=time.time()+60
  while time.time()<end:
   try:
    current=G['snapshot']();expected=dict(before,pids=dict(before['pids']));expected['pids']['adsb-rescue-feed']=current['pids']['adsb-rescue-feed'];G['healthy'](expected,current);assert ready()['holdback_s']==0;break
   except Exception:time.sleep(1)
  else:raise RuntimeError('Arrival relay readiness timeout')
  st.update(state='active',before=current,bad_checks=0,activated_unix=time.time());save(STATE,st);update_native_pid()
  until=time.time()+observe
  while time.time()<until:check(st);time.sleep(5)
  guard();print(json.dumps(dict(active=True,holdback_s=0,backup=str(backup))),flush=True)
 except BaseException as exc:rollback('Activation: '+repr(exc));raise
 finally:ctl('start','adsb-stream1090-lowlatency-guard.timer')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('action',choices=['activate','guard','rollback']);p.add_argument('--stage',type=Path);p.add_argument('--observe',type=int,default=90);p.add_argument('--reason',default='manual');a=p.parse_args()
 with open('/run/adsb-arrival-relay.lock','a') as f:
  try:fcntl.flock(f,fcntl.LOCK_EX|(fcntl.LOCK_NB if a.action=='guard' else 0))
  except BlockingIOError:raise SystemExit(0)
  if a.action=='activate':activate(a.stage,a.observe)
  elif a.action=='guard':guard()
  else:rollback(a.reason)
