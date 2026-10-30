#!/usr/bin/env python3
"""Adopt an active stock-only trial without reconnecting FR24. Fixed48h extension."""
import json,time,runpy,signal,subprocess,argparse,os
from pathlib import Path
D=Path('/var/lib/adsb-fr24-stock-trial-20261030');R=Path('/run/adsb-fr24-stock-trial-20261030')
def check_progress(previous,current,old_progress,new_progress):
 assert new_progress>old_progress,'DSP RF processing stalled'
 assert current['stock']['samples_processed']>previous['stock']['samples_processed'],'SDR processing stalled'
 if current['stock']['messages']>previous['stock']['messages']:
  assert current['relay']['counts']['stock_bytes_relayed']>previous['relay']['counts']['stock_bytes_relayed'],'Relay stalled with active traffic'

def main():
 old=runpy.run_path(str(D/'trial.py'));plan=json.loads((D/'extension.json').read_text());state=json.loads((D/'state.json').read_text())
 assert plan['new_restore_unix']==plan['old_restore_unix']+172800
 if args.restore:
  # If the controller deliberately changed intent, original restore respects it.
  old['restore']('extended_trial_independent_deadline');return
 resume=D/'extended-pre-resume.json'
 before=json.loads((resume if resume.exists() else D/'pre-extension-status.json').read_text());assert before['state']=='stock_test_running' and not before['completed']
 baseline=before['baseline'];s=old['snapshot']();old['health'](baseline,s,True);expected_pid=s['fr24_pid']
 assert state['original_host']==old['ctl']['DSP'] and state['guard_timer_active']
 report=dict(before,state='stock_test_running',completed=False,planned_restore_unix=plan['new_restore_unix'],extension=plan,monitor_revision=2,adopted_samples=0,monitor_adopted_unix=time.time(),error=None)
 until=time.monotonic()+max(0,plan['new_restore_unix']-time.time());previous=s;last_hour=0
 def stop(sig,frame):raise RuntimeError('Extended monitor interrupted:'+str(sig))
 signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
 try:
  while time.monotonic()<until:
   s=old['snapshot']();old['health'](baseline,s,False);assert s['fr24_pid']==expected_pid,'Unexpected FR24 restart'
   f=s['fr24'];assert f['cfg_host']==old['ctl']['STOCK'] and f['feed_status']=='connected' and str(f['rx_connected'])=='1','FR24 connection/route changed'
   assert f['msg_ring_full']=='false' and str(f['timing_is_valid'])=='1','FR24 ring/time unhealthy'
   tracked=int(f['feed_num_ac_tracked'])
   if tracked>0:assert time.time()-int(f['feed_last_ac_sent_time'] or 0)<120,'FR24 sends stale with active aircraft'
   else:report['quiet_aircraft_samples']=report.get('quiet_aircraft_samples',0)+1
   progress=json.loads(Path('/run/adsb-rescue/status.json').read_text())['counts'].get('processed_seconds',0)
   if report['adopted_samples']>0:
    check_progress(previous,s,previous_progress,progress)
   previous_progress=progress
   assert len(report['samples'])<4000,'Finite sample cap'
   report['samples'].append(s);report['adopted_samples']=report.get('adopted_samples',0)+1;report['remaining_seconds']=max(0,int(until-time.monotonic()));report['updated_unix']=time.time();old['save'](R/'extended-status.json',report)
   hour=int(time.time()//3600)
   if hour!=last_hour:
    with (D/'extended-hourly.jsonl').open('a') as f:f.write(json.dumps(dict(unix=s['unix'],fr24=s['fr24'],stock=s['stock'],planned_restore_unix=plan['new_restore_unix']))+'\n');f.flush();os.fsync(f.fileno())
    last_hour=hour
   previous=s;time.sleep(min(60,max(0,until-time.monotonic())))
  report.update(state='completed',completed=True)
 except BaseException as e:report.update(state='aborted_restoring',error=repr(e));raise
 finally:
  report['restoration']=old['restore']('extended_completed' if report['completed'] else report.get('error','interrupted'));report['closed_unix']=time.time();old['save'](R/'extended-status.json',report);old['save'](D/'extended-result.json',report,0o600)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--restore',action='store_true');args=p.parse_args();main()
