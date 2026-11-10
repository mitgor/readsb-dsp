#!/usr/bin/env python3
"""Native Stream1090 activation and independent persistent rollback.
Only the DSP coordinator may restart; protected producers/feeders/recorder stay up.
"""
import argparse,json,hashlib,os,runpy,shutil,subprocess,time
from pathlib import Path
G=runpy.run_path('/usr/local/sbin/adsb-coherent-rust-mode')
snapshot=G['snapshot'];ROOT=Path('/home/pi/adsb-neural-rescue')
STATE=Path('/var/lib/adsb-stream1090-native/active.json');CFG=Path('/etc/default/adsb-stream1090-native.json')
MARKER=Path('/run/adsb-rescue/stream1090-native-fallback.json')
GUARD_RUNTIME=Path('/run/adsb-stream1090-native-guard-status.json')
FILES={'src/rescue/stream1090_method.py':'adapter/stream1090_method.py','src/rescue/stream1090_compare.py':'adapter/stream1090_compare.py','src/rescue/_stream1090_native.so':'native/libstream1090-native.so'}

def healthy(before,s):
 # An idle feeder need not upload aircraft when there are none to send.
 checked=s
 if int(s['fr24'].get('feed_num_ac_tracked') or 0)==0:
  checked={**s,'fr24':{**s['fr24'],'feed_last_ac_sent_time':int(time.time())}}
 return G['healthy'](before,checked)

def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def boot():return Path('/proc/sys/kernel/random/boot_id').read_text().strip()
def save(p,x):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_name(p.name+'.native-tmp')
 with tmp.open('w') as f:json.dump(x,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
 os.replace(tmp,p);fd=os.open(p.parent,os.O_RDONLY);os.fsync(fd);os.close(fd)
def atomic(p,data,record):
 p=Path(p);tmp=p.with_name(p.name+'.native-tmp')
 with tmp.open('wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
 os.chmod(tmp,record['mode']);os.chown(tmp,record['uid'],record['gid']);os.replace(tmp,p)
 fd=os.open(p.parent,os.O_RDONLY);os.fsync(fd);os.close(fd)
def capacity(s):
 a=s['crc_archive'];assert not a['error'] and a['disk_bytes']+a['ram_bytes']+16*1048576<512*1048576,'CRC cache lacks graceful-save space'
 s0=read('/run/adsb-rescue/status.json')['archive'];assert not s0['error']
 assert not s0.get('enabled') or s0['compressed_ram_bytes']+sum(p.stat().st_size for p in Path('/var/lib/adsb-rescue').glob('batch-*.jsonl.gz'))+16*1048576<512*1048576,'Main cache lacks graceful-save space'
def runtime():return read('/run/adsb-rescue/status.json')
def rollback(reason):
 if not STATE.exists():return
 state=read(STATE)
 if state['state'] not in ['active','activating','rollback_failed']:return
 # Disable native immediately; the running adapter reads this each RF window.
 save(CFG,{'backend':'executable','reason':reason})
 backup=Path(state['backup']);records=read(backup/'files.json');conflicts=[]
 for name,record in records.items():
  if name==str(CFG):continue
  p=Path(name)
  if p.exists() and sha(p) not in [state['installed_sha256'].get(name),record.get('sha256')]:
   conflicts.append(name);continue
  if record['existed']:atomic(p,(backup/record['backup']).read_bytes(),record)
  else:p.unlink(missing_ok=True)
 # Keep the explicit executable setting, including across reboot. It is ignored
 # by the restored old adapter and allows an already-loaded new one to fall back.
 need_restart=False
 try:
  s=runtime();need_restart=time.time()-s['updated_unix']>20 or not s['threads_alive']
 except Exception:need_restart=True
 if subprocess.run(['systemctl','is-active','adsb-rescue-shadow'],capture_output=True,text=True).stdout.strip()!='active':need_restart=True
 if need_restart:
  # This service alone owns the coordinator and its CRC RAM cache. Protected
  # services and the far recorder must never be restarted by this tool.
  try:capacity(snapshot())
  except Exception:
   if subprocess.run(['systemctl','is-active','adsb-rescue-shadow'],capture_output=True,text=True).stdout.strip()=='active':raise
  subprocess.run(['systemctl','restart','adsb-rescue-shadow'],check=True,timeout=120)
 state.update(state='rolled_back' if not conflicts else 'rollback_conflict',reason=reason,rolled_back_unix=time.time(),coordinator_restarted=need_restart,conflicts=conflicts);save(STATE,state)
 save(GUARD_RUNTIME,{'backend':'executable','reason':reason,'updated_unix':time.time()})

def guard():
 if not STATE.exists():return
 st=read(STATE)
 if st['state'] not in ['active','activating','rollback_failed']:return
 if st['state']=='activating':
  if time.time()>st['activation_deadline']:rollback('Activation readiness deadline expired')
  return
 try:
  s=snapshot();status=runtime();stream=status.get('stream1090',{})
  if boot()!=st['boot']:
   # Wait for normal boot readiness before establishing new process identities.
   grace=st.setdefault('reboot_deadline',time.time()+120);save(STATE,st)
   if time.time()-s['updated_unix']>20 or stream.get('backend')!='native':
    if time.time()>grace:raise RuntimeError('Native did not recover after reboot')
    return
   healthy(s,s);st.update(boot=boot(),before=s,shadow_pid=s['shadow_pid']);st.pop('reboot_deadline',None);save(STATE,st)
  healthy(st['before'],s)
  assert s['shadow_pid']==st['shadow_pid'],'Coordinator unexpectedly restarted'
  assert sha(CFG)==st['config_sha256'],'Native configuration changed'
  assert not stream.get('native_disabled_reason'),'Native per-call fallback triggered'
  assert stream.get('backend')=='native' and stream.get('requested_backend')=='native','Native backend not active'
  capture=read('/run/adsb-far-capture/status.json')
  assert capture['config']['disk_limit_bytes']==5000000000 and not capture['error'],'RF collection unhealthy'
  assert time.time()-capture['updated_unix']<30,'RF collector status stale'
  for p,h in st['installed_sha256'].items():assert sha(p)==h,'Installed native component changed'
  if st.get('bad_checks',0):
   st['bad_checks']=0;save(STATE,st)
  save(GUARD_RUNTIME,{'last_healthy_unix':time.time(),'backend':'native','bad_checks':0,'boot':boot()})
 except Exception as e:
  st['bad_checks']=st.get('bad_checks',0)+1;st['guard_error']=repr(e);save(STATE,st)
  if st['bad_checks']>=2:rollback('Guard: '+repr(e))

def activate(stage,observe):
 if STATE.exists():assert read(STATE)['state']=='rolled_back','Native activation already present'
 proof=read(stage/'results/pi-adapter.json');assert proof['windows']>=30 and proof['exact_rows_and_alignment']
 assert all(proof[k] for k in ['same_window_deadline_fallback_exact','failed_native_not_retried','native_deadline_output_rejected','checksum_failure_fallback_exact'])
 assert sha(stage/'native/libstream1090-native.so')==proof['library_sha256']
 assert sha(ROOT/'src/rescue/stream1090_method.py')==sha(stage/'stream1090_method-original.py'),'Live adapter changed since validation'
 assert sha(ROOT/'src/rescue/stream1090_shadow.py')==sha(stage/'stream1090_shadow-original.py'),'Live alignment helper changed since validation'
 before=snapshot();healthy(before,before);capacity(before)
 assert read('/run/adsb-far-capture/status.json')['config']['disk_limit_bytes']==5000000000
 backup=Path('/var/backups')/('adsb-stream1090-native-'+str(time.time_ns()));backup.mkdir(mode=0o700)
 records={};installed={}
 for i,p in enumerate([ROOT/n for n in FILES]+[CFG]):
  stat=p.stat() if p.exists() else (ROOT/'src/rescue').stat();rec={'existed':p.exists(),'backup':f'file-{i}','uid':stat.st_uid,'gid':stat.st_gid,'mode':stat.st_mode&0o777 if p.exists() else 0o644}
  if p.exists():
   shutil.copy2(p,backup/rec['backup']);rec['sha256']=sha(p)
   with (backup/rec['backup']).open('rb') as f:os.fsync(f.fileno())
  records[str(p)]=rec
 for n,source in FILES.items():installed[str(ROOT/n)]=sha(stage/source)
 save(backup/'files.json',records)
 state={'state':'activating','backup':str(backup),'before':before,'installed_sha256':installed,'activation_deadline':time.time()+180,'boot':boot()};save(STATE,state)
 try:
  for n,source in FILES.items():atomic(ROOT/n,(stage/source).read_bytes(),records[str(ROOT/n)])
  cfg={'backend':'native','library':str(ROOT/'src/rescue/_stream1090_native.so'),'library_sha256':proof['library_sha256'],'activation':str(backup),'fallback':'original executable'};save(CFG,cfg);MARKER.unlink(missing_ok=True)
  state['config_sha256']=sha(CFG);save(STATE,state);switched=time.time()
  subprocess.run(['systemctl','restart','adsb-rescue-shadow'],check=True,timeout=120)
  deadline=time.time()+80
  while time.time()<deadline:
   s=snapshot();v=runtime().get('stream1090',{})
   if s['started_unix']>switched and s['aligned_seconds']>=5 and v.get('counts',{}).get('native_successes',0)>=5:break
   time.sleep(2)
  else:raise RuntimeError('Native coordinator readiness timeout')
  state.update(state='active',shadow_pid=s['shadow_pid'],activated_unix=time.time(),last_healthy_unix=time.time());save(STATE,state)
  samples=[];start=s
  until=time.time()+observe
  while time.time()<until:
   guard();assert read(STATE)['state']=='active','Automatic rollback triggered'
   s=snapshot();samples.append(s);save(backup/'observation.json',{'samples':samples});time.sleep(5)
  end=snapshot();healthy(before,end);stream=runtime()['stream1090'];assert stream['backend']=='native' and not stream['native_disabled_reason']
  assert end['aligned_seconds']-start['aligned_seconds']>=observe*.65,'Coordinator throughput degraded'
  assert end['feed']['counts']['stock_bytes_relayed']>start['feed']['counts']['stock_bytes_relayed'],'Stock relay stalled'
  assert end['feed']['counts']['dsp_frames_relayed']>start['feed']['counts']['dsp_frames_relayed'],'DSP relay stalled'
  save(backup/'result.json',{'activated':True,'before':before,'after':end,'stream1090':stream,'protected_pids_unchanged':end['pids']==before['pids'],'source':'extended native C++ repair/trust with unchanged downstream validation','observe_seconds':observe})
  print(json.dumps({'activated':True,'backup':str(backup),'protected_pids_unchanged':True,'native_successes':stream['counts']['native_successes']}))
 except BaseException as e:
  rollback('Activation: '+repr(e));raise

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('action',choices=['activate','guard','rollback','status']);p.add_argument('--stage',type=Path);p.add_argument('--observe',type=int,default=120);p.add_argument('--reason',default='manual');a=p.parse_args()
 if a.action=='activate':activate(a.stage,a.observe)
 elif a.action=='guard':guard()
 elif a.action=='rollback':rollback(a.reason)
 else:
  value=read(STATE) if STATE.exists() else {'state':'not_installed'}
  if GUARD_RUNTIME.exists():value['guard_runtime']=read(GUARD_RUNTIME)
  print(json.dumps(value))
