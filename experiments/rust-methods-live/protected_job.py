"""Abort only this owned test group if protected receiver health deteriorates."""
import json,os,runpy,signal,subprocess,time
from pathlib import Path
m=runpy.run_path('/usr/local/sbin/adsb-coherent-rust-mode');before=m['snapshot']();bad=0;samples=[]
process=subprocess.Popen(['/bin/bash','experiments/rust-methods-live/pi_job.sh'],start_new_session=True)
try:
 while process.poll() is None:
  time.sleep(3)
  try:
   s=m['snapshot']();assert s['shadow_pid']==before['shadow_pid'],'DSP restarted outside owned test';m['healthy'](before,s);samples.append({k:s[k] for k in ['unix','pids','shadow_pid','samples','pending','mean_latency_s','temperature_c']});bad=0
  except Exception:
   bad+=1
   if bad>=2:raise
 result=process.wait();assert result==0,f'Test process exited {result}'
 after=m['snapshot']();assert after['shadow_pid']==before['shadow_pid'];m['healthy'](before,after)
 Path('health.json').write_text(json.dumps({'before':before,'after':after,'samples':samples,'live_unchanged':True},indent=2)+'\n')
except BaseException as error:
 Path('health-interrupted.json').write_text(json.dumps({'before':before,'samples':samples,'error':repr(error),'live_unchanged':False,'our_service_mutations':False},indent=2)+'\n')
 if process.poll() is None:os.killpg(process.pid,signal.SIGTERM)
 raise
