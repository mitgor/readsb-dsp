"""Finite isolated Pi revalidation, only owned child aborts on health change."""
from pathlib import Path
import subprocess,time,json,os,signal,sys,hashlib
from protected_health import snapshot
D=Path(sys.argv[1]);before=snapshot();env={**os.environ,'PYTHONPATH':str(D/'src'),'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','TMPDIR':str(D/'tmp')};(D/'tmp').mkdir(exist_ok=True);checks=[];error=None
commands=[('coherent', [str(D/'experiments/rust-live/validate.py'),'--work',str(D/'experiments/rust-live/.work'),'--reference-root',str(D/'reference'),'--candidate',str(D/'candidate'),'--output',str(D/'coherent.json')],False),('acq-controls',[str(D/'experiments/rust-acquisition/controls.py'),'--work',str(D/'parity'),'--decoder-root',str(D),'--output',str(D/'acquisition-controls.json')],False),('acq-packets',[str(D/'experiments/rust-acquisition/packet_replay.py'),'--work',str(D/'parity'),'--decoder-root',str(D),'--output',str(D/'acquisition-packets.json')],False),('acq-cpu',[str(D/'experiments/rust-acquisition/benchmark.py'),'--work',str(D/'parity'),'--output',str(D/'acquisition-cpu.json')],False),('full-c',[str(D/'experiments/rust-revalidate-20261109/full_replay.py'),'--stage',str(D),'--output',str(D/'full-c.private.json')],True),('full-rust',[str(D/'experiments/rust-revalidate-20261109/full_replay.py'),'--stage',str(D),'--output',str(D/'full-rust.private.json'),'--cycles','6'],False)]
try:
 for label,argv,is_c in commands:
  use={**env,'PYTHONPATH':str(D/'reference/src') if is_c else str(D/'src')}
  with (D/(label+'.log')).open('w') as log:
   process=subprocess.Popen(['/home/pi/adsb-neural-rescue/.venv/bin/python',*argv],cwd=D,env=use,stdout=log,stderr=log,start_new_session=True);deadline=time.monotonic()+1200
   try:
    while process.poll() is None:
     time.sleep(3);now=snapshot();assert now==before,'Production identity/health changed';s=json.loads(Path('/run/adsb-rescue/status.json').read_text());lat=(s.get('max_recent_processing_s') or 0)+(s.get('stream1090',{}).get('last_wall_s') or 0);assert lat<2.3,'Production margin crossed'
     data=[list(map(int,l.split())) for l in subprocess.check_output(['ps','-e','-o','pid=,ppid=,rss='],text=True).splitlines()];owned={process.pid};last=set()
     while last!=owned:last=set(owned);owned.update(p for p,parent,rss in data if parent in owned)
     rss=sum(rss for p,parent,rss in data if p in owned);assert rss<1024*1024,'Owned test RSS exceeds 1 GiB';checks.append(dict(unix=time.time(),phase=label,processing_s=lat,rss_kib=rss));assert time.monotonic()<deadline,'Bounded runtime exceeded'
    assert process.returncode==0,(label,process.returncode)
   finally:
    if process.poll() is None:os.killpg(process.pid,signal.SIGTERM);process.wait(timeout=20)
except BaseException as e:error=repr(e);raise
finally:(D/'protected.private.json').write_text(json.dumps(dict(before=before,after=snapshot(),checks=checks,error=error),indent=2)+'\n')
