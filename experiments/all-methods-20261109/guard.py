#!/usr/bin/env python3
"""Owned all-method profile guard. Restores only untouched, recorded DSP configs."""
import json,time,hashlib,subprocess,os,fcntl
from pathlib import Path
D=Path('/var/lib/adsb-all-methods-20261109');R=Path('/run/adsb-all-methods-20261109');R.mkdir(exist_ok=True)
TIMER='adsb-all-methods-budget-20261109.timer'
def save(p,j):
 t=p.with_suffix('.tmp');t.write_text(json.dumps(j,indent=2)+'\n');os.replace(t,p)
def read(p):return json.loads(Path(p).read_text())
def sha(b):return hashlib.sha256(b).hexdigest()
def budget_reason(s):
 # Worker result latency includes its queue; Stream1090 follows that stage.
 # Keep300ms margin to the relay's independent hard3-second admission deadline.
 a=s.get('max_recent_processing_s');b=s.get('stream1090',{}).get('last_wall_s',0) or 0
 if a is not None and a+b>=2.7:return 'processing_margin_exceeded'
 if not s.get('threads_alive',False):return 'worker_thread_unhealthy'
 return None
def owned(state):return all(sha(Path(r['path']).read_bytes())==r['enabled_sha256'] for r in state['configs'])
def restore(state,reason):
 if not owned(state):save(D/'outcome.json',dict(result='superseded_by_external_config',reason=reason,unix=time.time()));subprocess.run(['systemctl','disable','--now',TIMER],check=True);return
 for r in state['configs']:
  p=Path(r['path']);raw=(D/r['backup']).read_bytes();assert sha(raw)==r['original_sha256'];tmp=p.with_suffix('.guard-tmp');tmp.write_bytes(raw);tmp.chmod(r['mode']);os.chown(tmp,r['uid'],r['gid']);os.replace(tmp,p)
 subprocess.run(['systemctl','restart','adsb-rescue-shadow'],check=True,timeout=90)
 save(D/'outcome.json',dict(result='restored_previous_profile',reason=reason,unix=time.time()))
 subprocess.run(['systemctl','disable','--now',TIMER],check=True)
def check():
 state=read(D/'activation.json')
 if (D/'outcome.json').exists():return
 if not owned(state):restore(state,'external_config_change');return
 now=time.time()
 try:s=read('/run/adsb-rescue/status.json');feed=read('/run/adsb-rescue/feed-status.json')
 except Exception:
  if now-state['activated_unix']>90:restore(state,'missing_status')
  return
 if s.get('started_unix',0)<state['activated_unix']:
  if now-state['activated_unix']>90:restore(state,'startup_timeout')
  return
 if now-s.get('updated_unix',0)>20:restore(state,'stale_worker_status');return
 reason=budget_reason(s)
 local=s.get('health',{}).get('local',{})
 if any(local.get(k,0)>state.get('stock_loss',{}).get(k,0) for k in ['samples_lost','samples_dropped']):reason='stock_sample_loss_increased'
 if reason:restore(state,reason);return
 if any(s.get('method_switches',{}).get(k)!=v for k,v in state['expected_methods'].items()):restore(state,'incomplete_method_activation');return
 prev=read(R/'status.json') if (R/'status.json').exists() else {}
 unhealthy=not(feed.get('stock_connected') and feed.get('fr24_routed'))
 # Avoid rolling back for a single transient WAN/route handover.
 import urllib.request
 try:
  m=json.load(urllib.request.urlopen('http://127.0.0.1:8754/monitor.json',timeout=3));unhealthy |= not(m.get('feed_status')=='connected' and str(m.get('rx_connected'))=='1')
 except Exception:unhealthy=True
 count=prev.get('unhealthy_checks',0)+1 if unhealthy else 0
 record=dict(unix=now,unhealthy_checks=count,worker_max_s=s.get('max_recent_processing_s'),stream_last_s=s.get('stream1090',{}).get('last_wall_s'),pending_jobs=s.get('workers',{}).get('pending_jobs'),result='monitoring',processing_limit_s=3,rollback_margin_s=.3)
 save(R/'status.json',record)
 if count>=3:restore(state,'sustained_feed_unhealthy')
if __name__=='__main__':
 with (R/'lock').open('w') as f:
  fcntl.flock(f,fcntl.LOCK_EX);check()
