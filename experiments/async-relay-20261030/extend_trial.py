#!/usr/bin/env python3
"""Root-only monitor handover, backed up, never restarts decoder/FR24 services."""
import json,time,os,runpy,subprocess,hashlib,shutil
from pathlib import Path
D=Path('/var/lib/adsb-fr24-stock-trial-20261030');R=Path('/run/adsb-fr24-stock-trial-20261030');B=D/'extension-backup';old=runpy.run_path(str(D/'trial.py'))
def run(*args):return subprocess.check_output(args,text=True,stderr=subprocess.STDOUT)
def unit(name,*properties):
 cmd=['systemd-run','--unit='+name,'--collect']+list(properties);return cmd
B.mkdir(mode=0o700,exist_ok=False)
report=json.loads((R/'status.json').read_text());state=json.loads((D/'state.json').read_text());before=old['snapshot']();old['health'](report['baseline'],before,True)
assert report['state']=='stock_test_running' and not report['completed'] and before['fr24']['cfg_host']==old['ctl']['STOCK']
for name in ['state.json','schedule.json','trial.py']:shutil.copy2(D/name,B/name)
shutil.copy2(R/'status.json',D/'pre-extension-status.json');shutil.copy2(R/'status.json',B/'status.json')
for name in ['adsb-fr24-stock-trial-20261030.service','adsb-fr24-stock-deadline-20261030.timer','adsb-fr24-stock-safety-20261030.timer']:(B/(name+'.txt')).write_text(run('systemctl','cat',name))
plan=dict(request='User requested two more days',requested_unix=time.time(),old_restore_unix=report['planned_restore_unix'],new_restore_unix=report['planned_restore_unix']+172800,measurement_start_unix=report['measurement_start_unix'],policy='48h extension of original end, total60h measured baseline; no FR24 reconnect during monitor handover')
assert plan['new_restore_unix']==1793559600 # 2026-11-01 19:00UTC /20:00Berlin
old['save'](D/'extension.json',plan,0o600)
py='/home/pi/adsb-neural-rescue/.venv/bin/python';script=str(D/'extended_trial.py')
# Protect the handover with independent fallback before retiring old safeguards.
# Uses original restore metadata after this bounded synchronous handover completes.
run(*unit('adsb-fr24-stock-extended-deadline-20261030','--on-calendar=2026-11-01 19:02:00 UTC','--timer-property=AccuracySec=1s','--timer-property=Persistent=yes'),py,script,'--restore')
run(*unit('adsb-fr24-stock-extended-safety-20261030','--on-calendar=2026-11-01 19:10:00 UTC','--timer-property=AccuracySec=1s'),py,script,'--restore')
try:
 # Existing monitor has an immutable in-memory deadline. Stop ONLY this owned
 # monitor with its original restore temporarily targeting the already-active
 # stock route. Both finally and ExecStopPost run before systemctl stop returns.
 # This avoids any feeder restart, then restores sealed original metadata.
 hold=dict(state,original_host=old['ctl']['STOCK'],guard_timer_active=False,extension_handover=True)
 old['save'](D/'state.json',hold,0o600)
 run('systemctl','stop','adsb-fr24-stock-trial-20261030.service')
 old['save'](D/'state.json',state,0o600)
 after=old['snapshot']();old['health'](report['baseline'],after,True)
 assert before['fr24_pid']==after['fr24_pid'],'FR24 restarted during handover'
 run(*unit('adsb-fr24-stock-extended-20261030','--property=Nice=19','--property=CPUWeight=1','--property=MemoryMax=256M','--property=RuntimeMaxSec=62h','--property=TimeoutStopSec=90','--property=ExecStopPost='+py+' '+script+' --restore'),py,script)
 for _ in range(30):
  time.sleep(1)
  if (R/'extended-status.json').exists():
   x=json.loads((R/'extended-status.json').read_text())
   if x['state']=='stock_test_running' and x.get('adopted_samples',0)>0:break
 else:raise RuntimeError('Extended monitor not ready')
 for name in ['adsb-fr24-stock-deadline-20261030.timer','adsb-fr24-stock-safety-20261030.timer']:run('systemctl','stop',name)
 old['save'](D/'schedule.json',{**json.loads((B/'schedule.json').read_text()),'planned_restore_unix':plan['new_restore_unix'],'extension':plan},0o600)
 receipt=dict(success=True,before=before,after=old['snapshot'](),plan=plan,extended_unit=run('systemctl','show','adsb-fr24-stock-extended-20261030','-p','ActiveState','-p','MainPID'),old_monitor_closed_for_user_extension=True)
 assert receipt['before']['pids']==receipt['after']['pids'] and receipt['before']['fr24_pid']==receipt['after']['fr24_pid']
except BaseException:
 old['save'](D/'state.json',state,0o600);old['restore']('extension_failed_restore_original_routing');raise
old['save'](D/'extension-receipt.json',receipt,0o600);print(json.dumps(dict(success=True,new_restore_unix=plan['new_restore_unix'],fr24_pid_unchanged=True,protected_pids_unchanged=True)))
