"""Native-speed tests only, generous bounded CPU; abort owned process on health changes."""
import json,time,subprocess,sys,os,signal,argparse
from pathlib import Path
from health import snapshot
parser=argparse.ArgumentParser();parser.add_argument('stage',type=Path);parser.add_argument('output',type=Path);parser.add_argument('--modes',nargs='+',choices=['sync_sic','sync_no_sic','async_no_sic'],default=['sync_sic','async_no_sic','sync_no_sic','sync_no_sic','async_no_sic','sync_sic']);args=parser.parse_args();stage=args.stage;out=args.output;out.mkdir(exist_ok=True);before=snapshot();samples=[];error=None;completed=[]
order=args.modes
try:
 for i,mode in enumerate(order):
  name=f'{i:02d}-{mode}';args=[sys.executable,str(stage/'experiments/async-native-20261109/benchmark.py'),'--stage',str(stage),'--output',str(out/(name+'.json')),'--mode',mode,'--label',name,'--timeout','90']
  proc=subprocess.Popen(args,start_new_session=True);last_hash=0
  try:
   while proc.poll() is None:
    time.sleep(.5)
    live=json.loads(Path('/run/adsb-rescue/status.json').read_text())
    if live.get('max_recent_processing_s',0)>2.3:raise RuntimeError('Protected live DSP approached rollback margin')
    if time.time()-live['updated_unix']>15:raise RuntimeError('Protected live DSP status stale')
    if time.monotonic()-last_hash>5:
     h=snapshot();assert h==before,'Protected receiver changed';samples.append(dict(unix=time.time(),mode=mode,unchanged=True,production_max_processing_s=live.get('max_recent_processing_s')));last_hash=time.monotonic()
   assert proc.returncode==0,'Owned benchmark failed: '+name
   after=snapshot();assert after==before;completed.append(name)
  except BaseException:
   if proc.poll() is None:os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=20)
   raise
except BaseException as e:error=repr(e);raise
finally:
 try:after=snapshot()
 except BaseException as e:after={'snapshot_error':repr(e)}
 (out/'protected.private.json').write_text(json.dumps(dict(before=before,after=after,samples=samples,error=error,completed=completed),indent=2)+'\n')
