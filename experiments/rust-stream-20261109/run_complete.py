"""Supervise only owned finite benchmark; terminate it on protected health change."""
from pathlib import Path
import subprocess,time,json,os,signal,sys
from protected_health import snapshot
D=Path(sys.argv[1]);before=snapshot();checks=[];error=None;p=None
try:
 with (D/'job-complete.log').open('w') as f:
  p=subprocess.Popen(['bash',str(D/'code-complete/pi_complete.sh')],cwd=D,env={**os.environ,'PYTHONPATH':str(D/'src'),'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1'},stdout=f,stderr=f,start_new_session=True);end=time.monotonic()+1600
  while p.poll() is None:
   time.sleep(3);assert snapshot()==before,'Protected state changed';s=json.loads(Path('/run/adsb-rescue/status.json').read_text());processing=(s.get('max_recent_processing_s') or 0)+(s.get('stream1090',{}).get('last_wall_s') or 0);assert processing<2.3,'Processing margin crossed'
   rows=[list(map(int,x.split())) for x in subprocess.check_output(['ps','-e','-o','pid=,ppid=,rss='],text=True).splitlines()];owned={p.pid};last=set()
   while last!=owned:last=set(owned);owned.update(pid for pid,parent,rss in rows if parent in owned)
   rss=sum(rss for pid,parent,rss in rows if pid in owned);assert rss<1024*1024,'Conservative summed RSS >1GiB';assert time.monotonic()<end,'Finite timeout';checks.append(dict(unix=time.time(),processing_s=processing,rss_kib=rss))
  assert p.returncode==0,('job exit',p.returncode)
except BaseException as e:error=repr(e);raise
finally:
 if p and p.poll() is None:os.killpg(p.pid,signal.SIGTERM);p.wait(timeout=20)
 (D/'protected-complete.private.json').write_text(json.dumps(dict(before=before,after=snapshot(),checks=checks,error=error),indent=2)+'\n')
