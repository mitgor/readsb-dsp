#!/usr/bin/env python3
"""Finite FR24 stock-only baseline; decoder, relay and collection stay running."""
import argparse,json,time,os,runpy,fcntl,hashlib,subprocess,urllib.request,signal,math
from pathlib import Path
D=Path('/var/lib/adsb-fr24-stock-trial-20261103');R=Path('/run/adsb-fr24-stock-trial-20261103');STATE=D/'state.json'
ctl=runpy.run_path('/usr/local/sbin/adsb-rescue-feed')
PROTECTED=('readsb','adsb-rescue-shadow','adsb-rescue-feed','adsb-far-capture','adsbexchange-feed')
CONFIGS=('/etc/default/readsb','/etc/default/adsb-rescue.json','/etc/default/adsb-rescue-workers.json','/etc/default/adsb-far-capture.json')
def active(u):return subprocess.run(['systemctl','is-active','--quiet',u]).returncode==0
def save(p,v,mode=0o644):
 p.parent.mkdir(parents=True,exist_ok=True);t=p.with_suffix('.tmp');t.write_text(json.dumps(v,indent=2)+'\n');t.chmod(mode);t.replace(p)
def pid(u):return int(subprocess.check_output(['systemctl','show',u,'-p','MainPID','--value'],text=True).strip())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def snapshot():
 m=json.load(urllib.request.urlopen('http://127.0.0.1:8754/monitor.json',timeout=4));s=json.loads(Path('/run/readsb/stats.json').read_text());d=json.loads(Path('/run/adsb-rescue/status.json').read_text());f=json.loads(Path('/run/adsb-rescue/feed-status.json').read_text());c=json.loads(Path('/run/adsb-far-capture/status.json').read_text())
 return dict(unix=time.time(),pids={u:pid(u) for u in PROTECTED},fr24_pid=pid('fr24feed'),configs={p:sha(p) for p in CONFIGS},gain_db=s['gain_db'],methods=d['method_switches'],stock=dict(messages=s['total']['messages'],positions=s['total']['position_count_total'],**{k:s['total']['local'][k] for k in ('samples_processed','samples_lost','samples_dropped')}),fr24={k:m.get(k) for k in ('cfg_host','num_messages','feed_num_ac_tracked','feed_status','rx_connected','msg_ring_full','timing_is_valid','feed_last_ac_sent_time','feed_last_connected_time')},dsp=dict(pid=pid('adsb-rescue-shadow'),started_unix=d['started_unix'],updated_unix=d['updated_unix'],threads_alive=d['threads_alive'],aligned_seconds=d['counts'].get('aligned_seconds',0)),relay=dict(pid=f['pid'],updated_unix=f['updated_unix'],stock_connected=f['stock_connected'],counts={k:f['counts'].get(k,0) for k in ('stock_records_received','stock_bytes_relayed','dsp_frames_relayed','relayed_coherent','relayed_neural')}),capture=dict(updated_unix=c['updated_unix'],config=c['config'],error=c['error'],counts=c['counts'],next_flush_unix=c['next_flush_unix']))
def locked():
 f=open('/run/lock/adsb-rescue-feed-control.lock','w');fcntl.flock(f,fcntl.LOCK_EX);return f
def restore(reason):
 if not STATE.exists():return
 st=json.loads(STATE.read_text());lock=locked()
 try:
  current_intent=ctl['intent']();target=st['original_host'] if current_intent==st['original_intent'] else (ctl['DSP'] if current_intent=='dsp' else ctl['STOCK'])
  ctl['route'](target);ctl['mark'](target==ctl['DSP']);ctl['publish']('long_stock_trial_restore',ctl['health']())
 finally:lock.close()
 if st['guard_timer_active']:subprocess.run(['systemctl','start','adsb-rescue-feed-guard.timer'],check=True)
 value=dict(unix=time.time(),reason=reason,host=ctl['host'](ctl['CONFIG'].read_text()),intent=ctl['intent'](),guard_active=active('adsb-rescue-feed-guard.timer'))
 save(D/'restoration.json',value);save(R/'restoration.json',value);return value
def health(b,s,check_feeder=True):
 assert s['pids']==b['pids'],'Protected decoder/relay/collection/other feeder process changed'
 assert all(s['pids'].values()),'Protected service stopped'
 assert s['configs']==b['configs'] and s['gain_db']==b['gain_db'] and s['methods']==b['methods'],'Decoder/capture configuration changed'
 assert s['dsp']['threads_alive'] and time.time()-s['dsp']['updated_unix']<20,'DSP stale'
 assert s['relay']['stock_connected'] and time.time()-s['relay']['updated_unix']<10,'Relay unhealthy'
 assert time.time()-s['capture']['updated_unix']<20 and not s['capture']['error'],'Capture unhealthy'
 assert s['capture']['config']==b['capture']['config'],'Capture policy changed'
 assert s['stock']['samples_lost']==b['stock']['samples_lost'] and s['stock']['samples_dropped']==b['stock']['samples_dropped'],'SDR loss/drop changed'
 assert not active('adsb-coherent-rust-guard') and not active('adsb-rust-methods-guard'),'Routing-dependent watchdog became active; restoring combined before proceeding'
 assert ctl['intent']()=='dsp','Concurrent manual routing intent changed'
 if check_feeder:
  assert s['fr24']['cfg_host']==ctl['STOCK'],'FR24 input changed externally'
  assert s['fr24']['feed_status']=='connected' and str(s['fr24']['rx_connected'])=='1','FR24 disconnected'
  assert s['fr24']['msg_ring_full']=='false','FR24 input ring full'
  if int(s['fr24']['feed_num_ac_tracked'] or 0)>0:assert time.time()-int(s['fr24']['feed_last_ac_sent_time'] or 0)<120,'FR24 sends stale with active aircraft'
  assert str(s['fr24']['timing_is_valid'])=='1','FR24 time invalid'
def stop_handler(sig,frame):raise RuntimeError('Finite trial interrupted: signal '+str(sig))
def install_deadlines(deadline):
 for suffix,delay in [('deadline',120),('safety',600)]:
  stamp=time.strftime('%Y-%m-%d %H:%M:%S UTC',time.gmtime(deadline+delay))
  unit='adsb-fr24-stock-24h-'+suffix+'-20261103'
  subprocess.run(['systemd-run','--unit='+unit,'--on-calendar='+stamp,'--timer-property=AccuracySec=1s','/usr/bin/python3',str(D/'trial.py'),'--restore'],check=True)
 save(D/'deadline-receipt.json',dict(deadline_unix=deadline,independent_restore_delays_s=[120,600],reboot_policy='Normal enabled routing guard restores combined on reboot; experiment ends early.'))
def run(seconds):
 assert seconds==86400,'Duration must be 24 hours'
 assert not STATE.exists(),'A trial state already exists; preserve it'
 b=snapshot();assert ctl['intent']()=='dsp' and ctl['host'](ctl['CONFIG'].read_text())==ctl['DSP'];health(b,b,False)
 assert b['capture']['config']['disk_limit_bytes']==5000000000
 D.mkdir(mode=0o700,exist_ok=True);R.mkdir(mode=0o755,exist_ok=True)
 state=dict(original_host=ctl['DSP'],original_intent='dsp',guard_timer_active=active('adsb-rescue-feed-guard.timer'),duration_seconds=seconds,baseline=b,started_unix=time.time(),policy='Route-only; readsb/DSP/relay/capture/ADSBExchange remain running. Preserve DSP intent and restore on completion/error/timeout/reboot via normal enabled routing guard.')
 save(STATE,state,0o600);save(D/'original-fr24feed.ini.json',{'text':ctl['CONFIG'].read_text()},0o600)
 report=dict(state='starting',samples=[],completed=False,baseline=b)
 try:
  subprocess.run(['systemctl','stop','adsb-rescue-feed-guard.timer','adsb-rescue-feed-guard.service'],check=True)
  lock=locked()
  try:ctl['route'](ctl['STOCK']);ctl['mark'](False);ctl['publish']('finite_24h_stock_trial',ctl['health']())
  finally:lock.close()
  started=time.time();measure_start=started+120;deadline=started+seconds;until=time.monotonic()+deadline-started;report.update(state='stock_test_running',stock_started_unix=started,measurement_start_unix=measure_start,planned_restore_unix=deadline,excluded_startup_seconds=120,cloud_rule='Use complete UTC hourly buckets fully contained after120s settling and before restoration; do not equate local sends with cloud credit.')
  install_deadlines(deadline)
  save(D/'schedule.json',{k:report[k] for k in ['stock_started_unix','measurement_start_unix','planned_restore_unix','excluded_startup_seconds','cloud_rule']});save(R/'status.json',report)
  expected_fr24_pid=None;previous=b;last_print=started
  while time.monotonic()<until:
   s=snapshot();settled=time.time()-started>=120;health(b,s,settled)
   if settled:
    if expected_fr24_pid is None:expected_fr24_pid=s['fr24_pid']
    assert s['fr24_pid']==expected_fr24_pid,'Unexpected FR24 restart during measured baseline'
    assert s['stock']['samples_processed']>previous['stock']['samples_processed'],'SDR processing stalled'
    if s['stock']['messages']>previous['stock']['messages']:assert s['relay']['counts']['stock_bytes_relayed']>previous['relay']['counts']['stock_bytes_relayed'],'Relay stalled with active traffic'
   report['samples'].append(s);report['remaining_seconds']=max(0,int(until-time.monotonic()));report['updated_unix']=time.time();save(R/'status.json',report)
   if time.time()-last_print>=3600:print(json.dumps({'remaining_seconds':report['remaining_seconds'],'samples':len(report['samples']),'stock_messages':s['stock']['messages']-b['stock']['messages']}),flush=True);last_print=time.time()
   if len(report['samples'])%720==0:save(D/'checkpoint.json',report,0o600)
   previous=s;time.sleep(min(60,max(0,until-time.monotonic())))
  report.update(completed=True,state='completed')
 except BaseException as e:report.update(state='aborted_restoring',error=repr(e));raise
 finally:
  report['restoration']=restore('completed' if report['completed'] else report.get('error','interrupted'));report['closed_unix']=time.time()
  try:report['final']=snapshot()
  except Exception as e:report['final_snapshot_error']=repr(e)
  save(R/'status.json',report);save(D/'result.json',report,0o600)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--restore',action='store_true');p.add_argument('--seconds',type=int,default=86400);a=p.parse_args()
 if a.restore:restore('independent_completion_or_timeout_guard')
 else:
  signal.signal(signal.SIGTERM,stop_handler);signal.signal(signal.SIGINT,stop_handler);run(a.seconds)
