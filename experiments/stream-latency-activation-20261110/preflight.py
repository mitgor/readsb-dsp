"""Run the actual candidate hooks on saved RF without any live input/relay."""
import hashlib,json,os,signal,subprocess,time
from pathlib import Path
ROOT=Path(os.environ['PHASE_BENCH_ROOT']);OUT=ROOT/'results';OUT.mkdir(exist_ok=True)
exec((ROOT/'protected-prefix.py').read_text(),globals());base=snap();healthy(base,base);child=None
try:
 for n,h in json.loads((ROOT/'manifest.json').read_text()).items():assert hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h,n
 with (OUT/'replay.stdout').open('w') as f:
  child=subprocess.Popen(['/home/pi/adsb-neural-rescue/.venv/bin/python',str(ROOT/'replay.py'),'--capture',str(ROOT/'capture'),'--libraries',str(ROOT/'bin'),'--legacy',str(ROOT/'legacy'),'--output',str(OUT/'integration.json')],stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
  while child.poll() is None:time.sleep(2);healthy(base,snap())
  assert child.returncode==0,'Integration replay failed'
 after=snap();healthy(base,after);(OUT/'protected.private.json').write_text(json.dumps(dict(before=base,after=after,production_actions=[]),indent=2)+'\n')
except BaseException:
 if child is not None and child.poll() is None:os.killpg(child.pid,signal.SIGTERM)
 raise
