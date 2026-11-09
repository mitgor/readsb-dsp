"""Persistent async activation health guard; restore only owned settings/drop-ins."""
import json,time,hashlib,subprocess,os,fcntl,urllib.request
from pathlib import Path
D=Path('/var/lib/adsb-async-live-20261109');R=Path('/run/adsb-async-live-20261109');T='adsb-async-live-20261109.timer'
def read(p):return json.loads(Path(p).read_text())
def sha(raw):return hashlib.sha256(raw).hexdigest()
def save(p,j):
 tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(j,indent=2)+'\n');os.replace(tmp,p)
def call(*a):return subprocess.run(a,check=True,stdout=subprocess.DEVNULL,timeout=100)
def owned(s):return all(Path(r['path']).is_file() and sha(Path(r['path']).read_bytes())==r['after_sha256'] for r in s['changes'])
def restore(s,reason):
 if not all((sha(Path(r['path']).read_bytes()) if Path(r['path']).is_file() else None) in (r['after_sha256'],r['before_sha256']) for r in s['changes']):
  save(D/'outcome.json',dict(result='superseded_by_external_change',reason=reason,unix=time.time()));call('systemctl','disable','--now',T);return
 call('systemctl','stop','adsb-rescue-feed-guard.timer')
 for r in s['changes']:
  p=Path(r['path'])
  if r['before'] is None:p.unlink(missing_ok=True)
  else:
   raw=(D/r['before']).read_bytes();assert sha(raw)==r['before_sha256'];tmp=p.with_suffix('.restore');tmp.write_bytes(raw);tmp.chmod(r['mode']);os.chown(tmp,r['uid'],r['gid']);os.replace(tmp,p)
 call('systemctl','daemon-reload')
 # Receiver, feeder and far-capture processes remain untouched.
 call('systemctl','restart','adsb-rescue-feed')
 call('systemctl','restart','adsb-rescue-shadow')
 for u,enabled in s['prior_timers'].items():
  if enabled:call('systemctl','enable','--now',u)
 save(D/'outcome.json',dict(result='restored_previous_pipeline',reason=reason,unix=time.time()));call('systemctl','disable','--now',T)
def check():
 s=read(D/'activation.json');now=time.time()
 if (D/'outcome.json').exists():return
 grace=now-s['activated_unix']<100
 if not owned(s):
  if not grace:restore(s,'external_change')
  return
 try:
  w=read('/run/adsb-rescue/status.json');f=read('/run/adsb-rescue/feed-status.json');c=read('/run/adsb-far-capture/status.json');m=json.load(urllib.request.urlopen('http://127.0.0.1:8754/monitor.json',timeout=3))
  if w['started_unix']<s['activated_unix'] or f['started_unix']<s['activated_unix']:
   if not grace:restore(s,'startup_timeout')
   return
  reasons=[]
  if now-w['updated_unix']>25 or now-f['updated_unix']>10:reasons.append('stale_status')
  if not w.get('threads_alive') or not w.get('async_output',{}).get('enabled'):reasons.append('producer_unhealthy')
  if not f.get('asynchronous') or f['holdback_s']!=0:reasons.append('wrong_relay_mode')
  if w['method_switches']!=s['methods']:reasons.append('method_mismatch')
  if c['disk_limit_bytes']!=5000000000 or c.get('error'):reasons.append('collection_unhealthy')
  health=w.get('health',{});local=health.get('local',{})
  if health.get('gain_db')!=s['gain']:reasons.append('gain_changed')
  if any(local.get(k,0)>s['stock_loss'].get(k,0) for k in ['samples_lost','samples_dropped']):reasons.append('sample_loss_increased')
  # Keep the original three-second safety budget with 300 ms margin.
  processing=(w.get('max_recent_processing_s') or 0)+(w.get('stream1090',{}).get('last_wall_s') or 0)
  if processing>=2.7:reasons.append('processing_budget')
  if w.get('async_output',{}).get('published',{}).get('outbox_overflow',0):reasons.append('outbox_overflow')
  if f.get('dedup',{}).get('capacity_evictions',0):reasons.append('dedup_capacity')
  if f.get('dedup',{}).get('late_stock_after_extra_race',0):reasons.append('late_stock_duplicate')
  for unit,pid in s['protected_pids'].items():
   current=subprocess.check_output(['systemctl','show',unit,'-p','MainPID','--value'],text=True).strip()
   if current=='0' or (Path('/proc/sys/kernel/random/boot_id').read_text().strip()==s.get('boot_id') and current!=pid):reasons.append('protected_pid_changed_'+unit)
  unhealthy=not(f['stock_connected'] and f['fr24_routed'] and m['feed_status']=='connected' and str(m['rx_connected'])=='1')
  previous=read(R/'status.json') if (R/'status.json').exists() else {};bad=previous.get('unhealthy_checks',0)+1 if unhealthy else 0
  record=dict(unix=now,result='monitoring',processing_s=processing,unhealthy_checks=bad,reasons=reasons,extras=f.get('counts',{}).get('dsp_frames_relayed',0),stock_bytes=f.get('counts',{}).get('stock_bytes_relayed',0),SIC=w['method_switches']['sic'],async_output=w['async_output'])
  save(R/'status.json',record)
  if not grace and (reasons or bad>=3):restore(s,','.join(reasons) or 'sustained_feeder_unhealthy')
 except Exception as e:
  save(R/'error.json',dict(unix=now,error=type(e).__name__+': '+str(e)))
  if not grace:restore(s,'health_check_failed')
if __name__=='__main__':
 import sys
 R.mkdir(exist_ok=True)
 with (R/'lock').open('w') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  if '--restore' in sys.argv:restore(read(D/'activation.json'),'manual_rollback')
  else:check()
