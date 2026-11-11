#!/usr/bin/env python3
"""Activate only the rescue coordinator; independent rollback leaves feeders up."""
import argparse,fcntl,json,os,runpy,shutil,subprocess,time
from pathlib import Path
G=runpy.run_path('/usr/local/sbin/adsb-stream1090-native-mode')
ROOT=Path('/home/pi/adsb-neural-rescue/src/rescue');STATE=Path('/var/lib/adsb-stream1090-lowlatency/active.json');CFG=Path('/etc/default/adsb-stream1090-lowlatency.json');RUN=Path('/run/adsb-stream1090-lowlatency-guard.json');STATUS=Path('/run/adsb-rescue/status.json');MARKER=Path('/run/adsb-rescue/lowlatency-error.json')
read,save,sha,atomic,boot,snapshot,healthy,capacity=(G[k] for k in ('read','save','sha','atomic','boot','snapshot','healthy','capacity'))
CORE=['__init__.py','bindings.py','cold_start.py','completion_bridge.py','final_cache.py','native_admission.py','shared_energy.py']
LIBS=['batch','incremental','admission','dedup']

def restart():subprocess.run(['systemctl','restart','adsb-rescue-shadow'],check=True,timeout=90)
def capture():
 c=read('/run/adsb-far-capture/status.json');assert c['config']['disk_limit_bytes']==5000000000 and not c['error'] and time.time()-c['updated_unix']<30,'RF capture unhealthy';return c

def check(st,s):
 healthy(st['before'],s);capture();assert s['shadow_pid']==st['shadow_pid'],'Coordinator restarted';assert sha(CFG)==st['config_sha256'],'Low-latency configuration changed'
 for p,h in st['installed'].items():assert sha(p)==h,'Component changed: '+p
 low=read(STATUS).get('lowlatency',{});assert low.get('enabled') and low.get('backend')=='incremental_native' and not low.get('last_error'),'Incremental path fell back'
 assert low['iq_pending']<64,'Incremental input backlog';return low

def rollback(reason):
 if not STATE.exists():return
 st=read(STATE)
 if st['state'] not in ['active','activating','rollback_failed']:return
 save(CFG,dict(enabled=False,reason=reason));b=Path(st['backup']);p=ROOT/'shadow.py';rec=read(b/'original.json')
 if p.exists() and sha(p) not in [rec['sha256'],st['installed'][str(p)]]:
  st.update(state='rollback_conflict',reason=reason);save(STATE,st);return
 atomic(p,(b/'shadow.py').read_bytes(),rec)
 # The running module observes disabled configuration within one second and
 # uses the untouched original executable. Restart only if it is unhealthy.
 try:s=snapshot();dead=not s['threads_alive'] or time.time()-s['updated_unix']>20
 except Exception:dead=True
 if dead:restart()
 st.update(state='rolled_back',reason=reason,rolled_back_unix=time.time(),coordinator_restarted=dead);save(STATE,st);save(RUN,dict(backend='executable',reason=reason,updated_unix=time.time()))

def diagnostics(snapshot, error):
 result=dict(unix=time.time(),error=repr(error))
 try:
  result.update(dsp_status_age_s=time.time()-snapshot['updated_unix'],relay_status_age_s=time.time()-snapshot['feed_updated_unix'])
  result['native']=read(STATUS).get('lowlatency',{})
 except Exception as exc:result['diagnostic_error']=repr(exc)
 return result

def guard():
 if not STATE.exists():return
 st=read(STATE)
 if st['state']=='activating':
  if time.time()>st['deadline']:rollback('Activation readiness deadline expired')
  return
 if st['state']!='active':return
 try:
  s=snapshot()
  if boot()!=st['boot']:
   assert s['config_sha256']==st['before']['config_sha256'],'Configuration changed on reboot'
   st.update(before=s,shadow_pid=s['shadow_pid'],boot=boot());check(st,s);save(STATE,st)
  low=check(st,s);c=low['counts']['native_seconds'];previous=read(RUN) if RUN.exists() else {}
  if previous.get('boot')==st['boot'] and previous.get('backend')=='incremental_native':
   assert c>previous['native_seconds'],'No incremental RF progress'
  if st.get('bad_checks'):st['bad_checks']=0;save(STATE,st)
  save(RUN,dict(backend='incremental_native',boot=st['boot'],native_seconds=c,updated_unix=time.time(),bad_checks=0))
 except Exception as exc:
  st['bad_checks']=st.get('bad_checks',0)+1;st['guard_error']=repr(exc);st['guard_diagnostics']=diagnostics(locals().get('s',{}),exc);save(STATE,st)
  if st['bad_checks']>=2:rollback('Guard: '+repr(exc))

def activate(stage,observe):
 assert not STATE.exists() or read(STATE)['state']=='rolled_back','Activation already present'
 assert not CFG.exists() or not read(CFG).get('enabled'),'Low-latency config already enabled'
 assert read('/etc/default/adsb-stream1090-native.json')['backend']=='executable','Existing Stream1090 fallback changed'
 proof=read(stage/'results/integration.json');assert proof['all_passed'] and proof['retained']==79 and proof['recorded_union']==210 and proof['fall_back_on_disabled_config'] and proof['incomplete_window_retires']
 manifest=read(stage/'manifest.json')
 files={ROOT/'shadow.py':'runtime/rescue/shadow.py',ROOT/'lowlatency_stream.py':'runtime/rescue/lowlatency_stream.py'}
 files.update({ROOT/'latency_core'/n:'runtime/rescue/latency_core/'+n for n in CORE});files.update({ROOT/'latency_core'/(n+'.so'):'bin/'+n+'.so' for n in LIBS})
 for dst,n in files.items():assert sha(stage/n)==manifest[n],n
 if not STATE.exists():assert all(not p.exists() for p in files if p!=ROOT/'shadow.py'),'Unowned low-latency files already present'
 assert sha(ROOT/'shadow.py')==manifest['shadow-original.py'],'Live source changed during preflight'
 old=ROOT/'shadow.py';s=old.stat();rec=dict(uid=s.st_uid,gid=s.st_gid,mode=s.st_mode&0o777,sha256=sha(old));before=snapshot();healthy(before,before);capacity(before);cap_before=capture()
 backup=Path('/var/backups')/('adsb-stream1090-lowlatency-'+str(time.time_ns()));backup.mkdir(mode=0o700);atomic(backup/'shadow.py',old.read_bytes(),rec);save(backup/'original.json',rec)
 if CFG.exists():shutil.copy2(CFG,backup/'previous-config.json')
 installed={str(p):manifest[n] for p,n in files.items()};st=dict(state='activating',backup=str(backup),before=before,installed=installed,boot=boot(),deadline=time.time()+160);save(STATE,st)
 try:
  for dst,n in files.items():dst.parent.mkdir(exist_ok=True);atomic(dst,(stage/n).read_bytes(),rec)
  assert before['worker_config']['cpus']=='2-3','Unexpected DSP core profile'
  cfg=dict(enabled=True,cpus=[2,3],**{n:dict(path=str(ROOT/'latency_core'/(n+'.so')),sha256=manifest['bin/'+n+'.so']) for n in LIBS});save(CFG,cfg);MARKER.unlink(missing_ok=True);st['config_sha256']=sha(CFG);save(STATE,st);switched=time.time();restart()
  until=time.time()+90
  while time.time()<until:
   try:s=snapshot()
   except (KeyError,TypeError):time.sleep(2);continue
   low=read(STATUS).get('lowlatency',{})
   if MARKER.exists():raise RuntimeError('Incremental readiness error: '+read(MARKER)['error'])
   if s['started_unix']>=switched and s['mean_latency_s'] is not None and low.get('enabled') and low['counts'].get('native_seconds',0)>=5 and low['counts'].get('shared_energy_blocks',0)>=80:break
   time.sleep(2)
  else:raise RuntimeError('Incremental readiness deadline expired')
  st.update(state='active',shadow_pid=s['shadow_pid'],activated_unix=time.time(),bad_checks=0);save(STATE,st);initial=check(st,s);obs_start=s;samples=[];until=time.time()+observe
  while time.time()<until:
   s=snapshot();v=check(st,s);samples.append(dict(snapshot=s,lowlatency=v));time.sleep(5)
  end=snapshot();final=check(st,end);cap_after=capture();assert final['counts']['native_seconds']-initial['counts']['native_seconds']>=observe*.65,'Incremental throughput degraded'
  assert end['feed']['counts']['stock_bytes_relayed']>obs_start['feed']['counts']['stock_bytes_relayed'],'Stock relay stalled'
  save(backup/'observation.json',dict(before=before,after=end,capture_before=cap_before,capture_after=cap_after,samples=samples,final=final,observe_seconds=observe));save(RUN,dict(backend='incremental_native',boot=st['boot'],native_seconds=final['counts']['native_seconds'],updated_unix=time.time(),bad_checks=0))
  print(json.dumps(dict(active=True,backup=str(backup),native_seconds=final['counts']['native_seconds'],shared_energy_blocks=final['counts']['shared_energy_blocks'],outbox_frames=final['counts'].get('outbox_frames',0),protected_pids_unchanged=True)),flush=True)
 except BaseException as exc:rollback('Activation: '+repr(exc));raise

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('action',choices=['activate','rollback','guard','status']);p.add_argument('--stage',type=Path);p.add_argument('--observe',type=int,default=90);p.add_argument('--reason',default='manual');a=p.parse_args()
 with open('/run/adsb-stream1090-lowlatency-mode.lock','a') as lock:
  try:fcntl.flock(lock,fcntl.LOCK_EX|(fcntl.LOCK_NB if a.action=='guard' else 0))
  except BlockingIOError:raise SystemExit(0)
  if a.action=='activate':activate(a.stage,a.observe)
  elif a.action=='rollback':rollback(a.reason)
  elif a.action=='guard':guard()
  else:print(json.dumps(read(STATE) if STATE.exists() else {'state':'not_installed'}))
