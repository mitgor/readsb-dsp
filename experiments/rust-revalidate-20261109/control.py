"""Single coherent/acquisition release owner, bounded observation and exact C rollback."""
import argparse,ctypes,fcntl,hashlib,json,os,subprocess,time,urllib.request
from pathlib import Path
from policy import assess
ROOT=Path('/home/pi/adsb-neural-rescue');D=Path('/var/lib/adsb-rust-kernels-20261109');R=Path('/run/adsb-rust-kernels-20261109');T='adsb-rust-kernels-20261109.timer';PREVIOUS='adsb-async-live-20261109.timer'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def save(p,j):
 p.parent.mkdir(parents=True,exist_ok=True);temp=p.with_suffix('.tmp');temp.write_text(json.dumps(j,indent=2)+'\n');os.replace(temp,p)
 if str(p).startswith('/var/'):
  with p.open('rb') as f:os.fsync(f.fileno())
  fd=os.open(p.parent,os.O_RDONLY);os.fsync(fd);os.close(fd)
def call(*a):return subprocess.run(a,check=True,timeout=120,stdout=subprocess.DEVNULL)
def pid(u):return int(subprocess.check_output(['systemctl','show',u,'-p','MainPID','--value'],text=True).strip())
def snapshot():
 s=read('/run/adsb-rescue/status.json');f=read('/run/adsb-rescue/feed-status.json');c=read('/run/adsb-far-capture/status.json');stats=read('/run/readsb/stats.json');m=json.load(urllib.request.urlopen('http://127.0.0.1:8754/monitor.json',timeout=4));pids={u:pid(u) for u in ['readsb','fr24feed','adsb-rescue-feed','adsb-far-capture','adsbexchange-feed']};counts=s['workers'].get('completed_by_pid',{});loss=stats['total']['local'];worker=s['workers']
 return dict(unix=time.time(),shadow_pid=pid('adsb-rescue-shadow'),receiver_pid=pids['readsb'],protected_pids=pids,started_unix=s['started_unix'],updated_unix=s['updated_unix'],feed_updated_unix=f['updated_unix'],threads_alive=s['threads_alive'],completed=sum(counts.values()),iq_packets=sum(s.get('capture_transport',{}).get(k,0) for k in ['sent','dropped']),aligned=s.get('counts',{}).get('aligned_seconds',0),processed=s.get('counts',{}).get('processed_seconds',0),submitted=worker.get('submitted_jobs',0),pending=worker['pending_jobs'],processing_s=(s.get('max_recent_processing_s') or 0)+(s.get('stream1090',{}).get('last_wall_s') or 0),gain=stats.get('gain_db'),methods=s['method_switches'],worker_config=worker['config'],worker_roles=worker['role_by_pid'],stock_connected=f['stock_connected'],fr24_routed=f['fr24_routed'],asynchronous=f.get('asynchronous',False),holdback_s=f['holdback_s'],fr24_connected=m.get('feed_status')=='connected' and str(m.get('rx_connected'))=='1',fr24_last_upload=m.get('feed_last_ac_sent_time'),tracked_aircraft=m.get('feed_num_ac_tracked'),capture_error=c.get('error'),capture_cap=c['disk_limit_bytes'],samples={k:loss.get(k,0) for k in ['samples_lost','samples_dropped']},temperature_c=int(Path('/sys/class/thermal/thermal_zone0/temp').read_text())/1000,stock_bytes=f['counts'].get('stock_bytes_relayed',0),extras=f['counts'].get('dsp_frames_relayed',0),coherent_extras=f['counts'].get('relayed_coherent',0),acquisition_extras=f['counts'].get('relayed_acquisition',0),late_stock_duplicates=f.get('dedup',{}).get('late_stock_after_extra_race',0),cache_evictions=f.get('dedup',{}).get('capacity_evictions',0),outbox_overflow=s.get('async_output',{}).get('published',{}).get('outbox_overflow',0),config_hashes={p:sha(p) for p in ['/etc/default/readsb','/etc/fr24feed.ini','/etc/default/adsb-rescue.json','/etc/default/adsb-rescue-workers.json','/etc/default/adsb-far-capture.json']})
def atomic(p,raw,meta):
 temp=p.with_suffix('.rust-tmp');temp.write_bytes(raw);temp.chmod(meta['mode']);os.chown(temp,meta['uid'],meta['gid']);os.replace(temp,p)
def mapped(s):
 out={}
 for worker,role in s['worker_roles'].items():
  if role!='coherent':continue
  lines=Path('/proc/'+worker+'/maps').read_text().splitlines();expected=['_coherent.so']
  if s['methods'].get('coherent') and s['worker_config'].get('coherent_pair_retry'):expected.append('_coherent_pair.so')
  if s['methods'].get('acquisition'):expected.append('_acquisition_rust.so')
  for name in expected:
   p=ROOT/'src/rescue'/name;inode=str(p.stat().st_ino);assert any(len(v:=l.split())>=6 and v[4]==inode and v[5]==str(p) for l in lines),'Wrong live kernel mapping '+name
  out[worker]=expected
 assert out,'No coherent-role workers';return out
def markers():
 out={}
 for name,symbol in [('_coherent.so','rescue_coherent_backend'),('_coherent_pair.so','rescue_coherent_backend'),('_acquisition_rust.so','rescue_acquisition_backend')]:
  lib=ctypes.CDLL(str(ROOT/'src/rescue'/name));f=getattr(lib,symbol);f.restype=ctypes.c_char_p;out[name]=f().decode();assert out[name].startswith('rust-1.99.1/')
 return out
def owns(state,allow_before=False):
 return all((sha(r['path']) if Path(r['path']).is_file() else None) in ([r['after_sha256'],r['before_sha256']] if allow_before else [r['after_sha256']]) for r in state['files'])
def restore(reason):
 state=read(D/'active.json')
 if state['state'] not in ['active','activating','restoring','rollback_failed']:return
 if not owns(state,True):state.update(state='superseded_by_external_change',reason=reason);save(D/'active.json',state);call('systemctl','disable','--now',T);return
 state.update(state='restoring',reason=reason,restoring_unix=time.time());save(D/'active.json',state)
 try:
  for r in state['files']:
   p=Path(r['path'])
   if r['before'] is None:p.unlink(missing_ok=True)
   else:
    raw=(D/r['before']).read_bytes();assert hashlib.sha256(raw).hexdigest()==r['before_sha256'];atomic(p,raw,r)
  call('systemctl','restart','adsb-rescue-shadow')
  state.update(state='rolled_back',rolled_back_unix=time.time());save(D/'active.json',state)
  if state.get('previous_guard_enabled'):call('systemctl','enable','--now',PREVIOUS)
  call('systemctl','disable','--now',T);save(R/'guard.json',dict(state='rolled_back',reason=reason,unix=time.time()))
 except BaseException as e:state.update(state='rollback_failed',error=repr(e));save(D/'active.json',state);raise

def monitor(activation=False):
 state=read(D/'active.json')
 if state['state'] in ['rollback_failed','restoring']:restore('retry_incomplete_rollback');return
 if state['state'] not in ['active','activating']:return
 if not owns(state):
  if state['state']=='activating' and time.time()-state['activated_unix']<120:return
  restore('kernel_files_changed');return
 prev=read(R/'guard.json') if (R/'guard.json').exists() else {};s=snapshot();result=assess(s,prev,time.time());bad=prev.get('consecutive_failures',0)+1 if result['reasons'] else 0;result.update(unix=time.time(),state='degraded' if bad else 'healthy',consecutive_failures=bad)
 if not result['startup_grace']:
  try:result['mapped']=mapped(s);result['backend_markers']=markers()
  except Exception as e:result['reasons'].append(str(e));bad=prev.get('consecutive_failures',0)+1;result['consecutive_failures']=bad;result['state']='degraded'
 save(R/'guard.json',result)
 if bad:
  # Keep full evidence on the first failure, and the last healthy/progress record.
  save(D/('failure-'+str(time.time_ns())+'.json'),dict(previous=prev,current=result))
  if bad>=3:restore(';'.join(result['reasons']))
 return result

def activate(observe):
 state=read(D/'active.json');assert state['state']=='prepared';proof=read(D/'proof.json');assert proof['parity_passed'] and proof['stability_passed'];before=snapshot();assert before['asynchronous'] and before['fr24_connected'] and not assess(before,None,time.time())['reasons'];assert all(sha(r['path'])==r['before_sha256'] if r['before'] else not Path(r['path']).exists() for r in state['files'])
 s=read('/run/adsb-rescue/status.json')
 for sub,archive in [('',s['archive']),('/crc-verification',s['crc_verification']['archive'])]:
  total=sum(p.stat().st_size for p in Path('/var/lib/adsb-rescue'+sub).glob('batch-*.jsonl.gz'));assert not archive.get('error') and total+archive['compressed_ram_bytes']+8*1048576<512*1048576,'No clean-save headroom'
 state.update(state='activating',activated_unix=time.time(),before=before);save(D/'active.json',state);call('systemctl','enable','--now',T);call('systemctl','disable','--now',PREVIOUS)
 for u in ['adsb-coherent-rust-guard.service','adsb-rust-methods-guard.service']:call('systemctl','disable','--now',u)
 try:
  for r in state['files']:atomic(Path(r['path']),(D/r['candidate']).read_bytes(),r)
  assert owns(state);marker=markers();restart=time.time();call('systemctl','restart','adsb-rescue-shadow')
  for _ in range(100):
   s=snapshot()
   if s['started_unix']>=restart and s['completed']>20 and s['gain']==before['gain'] and s['fr24_connected']:break
   time.sleep(1)
  else:raise RuntimeError('Rust startup timed out')
  first=s;began=time.monotonic();samples=[];save(R/'guard.json',assess(s,None,time.time()))
  while True:
   s=snapshot();assert s['protected_pids']==before['protected_pids'],'Protected PID changed';assert s['config_hashes']==before['config_hashes'] and s['methods']==before['methods'] and s['gain']==before['gain'] and s['samples']==before['samples'];record=monitor(True);assert record is not None and not record['reasons'],record;record['mapped']=mapped(s);samples.append(record);save(R/'observation.json',dict(started_unix=restart,samples=samples))
   if time.monotonic()-began>=observe:break
   time.sleep(10)
  assert s['completed']>first['completed']+observe*4 and s['aligned']>first['aligned']+observe*.5,'Sustained RF processing/alignment fell'
  assert s['stock_bytes']>first['stock_bytes'] and s['coherent_extras']>first['coherent_extras'] and s['extras']>first['extras'],'Forwarding did not progress';assert s['acquisition_extras']>first['acquisition_extras'],'Acquisition output did not progress'
  state.update(state='active',verified_unix=time.time(),observation_seconds=time.monotonic()-began,markers=marker,protected_pids_unchanged=True);save(D/'active.json',state);save(D/'live-observation.json',dict(first=first,last=s,samples=samples));print(json.dumps(dict(state='active',observe_seconds=state['observation_seconds'],backend_markers=marker,protected_pids_unchanged=True)))
 except BaseException as e:restore('activation_failure: '+repr(e));raise

def main():
 p=argparse.ArgumentParser();p.add_argument('action',choices=['activate','check','rollback','status']);p.add_argument('--observe',type=int,default=300);p.add_argument('--reason',default='manual');a=p.parse_args();R.mkdir(parents=True,exist_ok=True)
 if a.action=='status':print(json.dumps(dict(release=read(D/'active.json'),guard=read(R/'guard.json') if (R/'guard.json').exists() else None),indent=2));return
 with (R/'lock').open('w') as f:
  try:fcntl.flock(f,fcntl.LOCK_EX|(fcntl.LOCK_NB if a.action=='check' else 0))
  except BlockingIOError:return
  if a.action=='activate':assert a.observe>=180;activate(a.observe)
  elif a.action=='rollback':restore(a.reason)
  else:
   try:
    monitor()
    (R/'error.json').unlink(missing_ok=True)
   except Exception as e:
    previous=read(R/'error.json') if (R/'error.json').exists() else {};count=previous.get('consecutive',0)+1;save(R/'error.json',dict(unix=time.time(),error=repr(e),consecutive=count))
    if count>=3:restore('health_snapshot_failure: '+repr(e))
if __name__=='__main__':main()
