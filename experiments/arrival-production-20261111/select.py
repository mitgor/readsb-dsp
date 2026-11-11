#!/usr/bin/env python3
"""Explicit manual selection; no automatic reactivation after a fault."""
import argparse,json,runpy,subprocess,time
from pathlib import Path
STAGE=Path('/var/lib/adsb-arrival-relay/release')
def select(mode):
 G=runpy.run_path('/usr/local/sbin/adsb-arrival-relay-mode');N=G['G'];before=N['snapshot']();N['healthy'](before,before);N['capture']();status=G['ready']();state=G['read'](G['STATE']);cfg=G['read'](G['CFG']);target=0 if mode=='arrival_order' else 3
 if status['holdback_s']==target and bool(cfg.get('enabled'))==(target==0):return
 if mode=='ordered_3s':
  if state['state']!='active':raise RuntimeError('Arrival guard is not active; inspect current intent before switching')
  subprocess.run(['/usr/local/sbin/adsb-arrival-relay-mode','rollback','--reason','Manual ordered three-second relay selection'],check=True,timeout=90)
 else:subprocess.run(['/usr/local/sbin/adsb-arrival-relay-mode','activate','--stage',str(STAGE),'--observe','30'],check=True,timeout=140)
 deadline=time.time()+20
 while time.time()<deadline:
  try:
   now=N['snapshot']();expected=dict(before,pids=dict(before['pids']));expected['pids']['adsb-rescue-feed']=now['pids']['adsb-rescue-feed'];N['healthy'](expected,now);N['capture']();assert G['ready']()['holdback_s']==target
   assert G['read']('/etc/default/adsb-stream1090-lowlatency.json').get('enabled'),'Native default changed'
   print(json.dumps(dict(mode=mode,holdback_s=target,protected_feeders_preserved=True)));return
  except (AssertionError,KeyError,TypeError):time.sleep(1)
 raise RuntimeError('Selected relay failed health/readiness checks; inspect guard state')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('mode',choices=['arrival_order','ordered_3s']);select(p.parse_args().mode)
