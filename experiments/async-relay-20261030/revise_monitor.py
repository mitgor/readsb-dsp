"""Revise only owned monitor; preserve stock route throughout the handover."""
import runpy,json,time,shutil,subprocess
from pathlib import Path
D=Path('/var/lib/adsb-fr24-stock-trial-20261030');R=Path('/run/adsb-fr24-stock-trial-20261030');old=runpy.run_path(str(D/'trial.py'));state=json.loads((D/'state.json').read_text());report=json.loads((R/'extended-status.json').read_text());before=old['snapshot']();old['health'](report['baseline'],before,True)
assert report['state']=='stock_test_running';assert state['original_host']==old['ctl']['DSP']
backup=D/'monitor-v1';backup.mkdir(mode=0o700,exist_ok=False);shutil.copy2(D/'extended_trial.py',backup/'extended_trial.py');old['save'](backup/'status.json',report,0o600);old['save'](D/'extended-pre-resume.json',report,0o600)
try:
 old['save'](D/'state.json',dict(state,original_host=old['ctl']['STOCK'],guard_timer_active=False),0o600)
 subprocess.run(['systemctl','stop','adsb-fr24-stock-extended-20261030'],check=True)
 old['save'](D/'state.json',state,0o600);shutil.copyfile('/tmp/extended_trial.py',D/'extended_trial.py')
 after=old['snapshot']();assert before['pids']==after['pids'] and before['fr24_pid']==after['fr24_pid'];old['health'](report['baseline'],after,True)
 py='/home/pi/adsb-neural-rescue/.venv/bin/python';script=str(D/'extended_trial.py')
 subprocess.run(['systemd-run','--unit=adsb-fr24-stock-extended-v2-20261030','--collect','--property=Nice=19','--property=CPUWeight=1','--property=MemoryMax=256M','--property=RuntimeMaxSec=62h','--property=TimeoutStopSec=90','--property=ExecStopPost='+py+' '+script+' --restore',py,script],check=True)
 for _ in range(30):
  time.sleep(1);x=json.loads((R/'extended-status.json').read_text())
  if x.get('monitor_revision')==2 and x.get('adopted_samples',0)>0 and x['state']=='stock_test_running':break
 else:raise RuntimeError('v2 monitor not ready')
 receipt=dict(success=True,before=before,after=old['snapshot'](),planned_restore_unix=x['planned_restore_unix'],quiet_rf_policy='Require processed RF progress; no aircraft/alignment matches required during silence',unit='adsb-fr24-stock-extended-v2-20261030');old['save'](D/'monitor-v2-receipt.json',receipt,0o600);print(json.dumps(dict(success=True,fr24_pid_unchanged=receipt['before']['fr24_pid']==receipt['after']['fr24_pid'],protected_pids_unchanged=receipt['before']['pids']==receipt['after']['pids'],planned_restore_unix=x['planned_restore_unix'])))
except BaseException:
 old['save'](D/'state.json',state,0o600);old['restore']('monitor_revision_failed');raise
