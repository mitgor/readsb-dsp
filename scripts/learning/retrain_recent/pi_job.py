"""Protect live receiver while running only the owned, bounded offline replay."""
import json,os,runpy,signal,subprocess,time
from pathlib import Path
mode=runpy.run_path('/usr/local/sbin/adsb-coherent-rust-mode');before=mode['snapshot']();mode['healthy'](before,before);samples=[];bad=0
process=subprocess.Popen(['/home/pi/adsb-neural-rescue/.venv/bin/python','scripts/learning/retrain_recent/benchmark.py','--output','results/retrain-companion-20261029/pi-rf.json'],env={**os.environ,'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','STREAM1090_BINARY':'/home/pi/stream1090-shadow/build/stream1090'},start_new_session=True)
try:
 while process.poll() is None:
  time.sleep(3)
  try:
   current=mode['snapshot']();assert current['shadow_pid']==before['shadow_pid'],'External shadow restart';mode['healthy'](before,current);samples.append({k:current[k] for k in ['unix','pids','shadow_pid','samples','pending','mean_latency_s','temperature_c']});bad=0
  except Exception:
   bad+=1
   if bad>=2:raise
 assert process.wait()==0,'Offline replay failed'
 after=mode['snapshot']();mode['healthy'](before,after);assert after['shadow_pid']==before['shadow_pid']
 Path('results/retrain-companion-20261029/pi-health.json').write_text(json.dumps(dict(before=before,after=after,samples=samples,live_unchanged=True),indent=2)+'\n')
except BaseException as error:
 if process.poll() is None:os.killpg(process.pid,signal.SIGTERM)
 Path('results/retrain-companion-20261029/pi-interrupted.json').write_text(json.dumps(dict(error=repr(error),before=before,samples=samples,our_service_changes=False),indent=2)+'\n');raise
