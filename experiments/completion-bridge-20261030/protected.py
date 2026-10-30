"""Only owned finite replay, with independent protected service monitoring."""
import hashlib,json,os,runpy,subprocess,sys,time
from pathlib import Path
stage=Path(sys.argv[1]);old=runpy.run_path('/var/lib/adsb-fr24-stock-trial-20261030/trial.py')
def snapshot():
 s=old['snapshot']();baseline=json.loads(Path('/run/adsb-fr24-stock-trial-20261030/extended-status.json').read_text())['baseline'];old['health'](baseline,s,True);return s
def hashes():
 root=Path('/home/pi/adsb-neural-rescue');return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for folder in ('src','models') for p in (root/folder).rglob('*') if p.is_file() and p.suffix in ('.py','.so','.onnx','.json')}
before=snapshot();initial=hashes()
for p,h in initial.items():assert hashlib.sha256((stage/p).read_bytes()).hexdigest()==h,'Staging source differs: '+p
proc=subprocess.Popen([sys.executable,str(stage/'experiment/benchmark.py'),str(stage),str(stage/'pi.json')]);error=None;samples=[]
try:
 while proc.poll() is None:
  time.sleep(5);s=snapshot();samples.append(dict(unix=s['unix'],pids=s['pids'],fr24_pid=s['fr24_pid'],stock=s['stock'],gain_db=s['gain_db']))
  assert s['pids']==before['pids'] and s['fr24_pid']==before['fr24_pid'] and s['configs']==before['configs']
 assert proc.returncode==0,'Replay failed; preserve partial evidence'
 after=snapshot();assert hashes()==initial,'Protected sources/models changed'
except BaseException as e:
 error=repr(e)
 if proc.poll() is None:proc.terminate();proc.wait(timeout=20)
 raise
finally:
 (stage/'protected.private.json').write_text(json.dumps(dict(before=before,after=snapshot(),samples=samples,error=error,source_hashes=initial),indent=2))
