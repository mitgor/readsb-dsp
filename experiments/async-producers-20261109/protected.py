"""Guard only the owned replay; never repair/change protected services."""
import subprocess,time,sys,json,os
from pathlib import Path
from health import snapshot
stage=Path(sys.argv[1]);output=Path(sys.argv[2]) if len(sys.argv)>2 else stage;before=snapshot();samples=[];error=None
command=[sys.executable,str(stage/'experiments/async-producers-20261109/replay.py'),'--stage',str(stage),'--output',str(output/'pi-v4.json'),'--label','pi','--scale','12','--timeout','400','--job-runtime',str(output/'jobs-pi-v4')]
p=subprocess.Popen(command,start_new_session=True)
try:
 while p.poll() is None:
  time.sleep(5);after=snapshot();samples.append(dict(unix=time.time(),unchanged=after==before));assert after==before,'Protected receiver changed; stop only owned replay'
 assert p.returncode==0,'Replay failed'
 assert snapshot()==before
except BaseException as e:
 error=repr(e)
 if p.poll() is None:
  import signal
  os.killpg(p.pid,signal.SIGTERM);p.wait(timeout=20)
 raise
finally:(output/'protected-v4.private.json').write_text(json.dumps(dict(before=before,after=snapshot(),samples=samples,error=error),indent=2)+'\n')
