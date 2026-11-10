import os,sys,json,subprocess,time,runpy,signal
from pathlib import Path
D=Path('/dev/shm/adsb-larger-companion-20261110');G=runpy.run_path('/usr/local/sbin/adsb-coherent-rust-mode');before=G['snapshot']();samples=[]
proc=subprocess.Popen(['/home/pi/adsb-neural-rescue/.venv/bin/python',str(D/'benchmark.py'),'--output',str(D/'results/larger-companion-20261110/pi-full-pipeline.json')],cwd=D,env={**os.environ,'ADSB_NEURAL_DATA_ROOT':str(D),'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1'},stdout=(D/'benchmark.log').open('w'),stderr=subprocess.STDOUT,start_new_session=True)
try:
 while proc.poll() is None:
  s=G['snapshot']();checked=s
  if int(s['fr24'].get('feed_num_ac_tracked') or 0)==0:checked={**s,'fr24':{**s['fr24'],'feed_last_ac_sent_time':int(time.time())}}
  G['healthy'](before,checked)
  rows=[list(map(int,line.split())) for line in subprocess.check_output(['ps','-eo','pid=,ppid=,rss='],text=True).splitlines()];ids={proc.pid}
  for _ in range(5):ids|={pid for pid,parent,rss in rows if parent in ids}
  rss=sum(rss for pid,parent,rss in rows if pid in ids);assert rss<1048576,'Owned benchmark RSS over 1 GiB'
  samples.append({'at':time.time(),'rss_kib':rss,'healthy':True});(D/'health.json').write_text(json.dumps(samples));time.sleep(5)
 assert proc.returncode==0,f'Benchmark failed {proc.returncode}'
 (D/'protected.json').write_text(json.dumps({'before':before,'after':G['snapshot'](),'checks':len(samples)}))
except BaseException:
 if proc.poll() is None:os.killpg(proc.pid,signal.SIGTERM)
 raise
