"""Finite supervisor: owns only copied-code children, never production controls."""
import json,os,subprocess,time,signal,hashlib,urllib.request
from pathlib import Path
ROOT=Path(os.environ['PHASE_BENCH_ROOT']);OUT=ROOT/'results';OUT.mkdir(exist_ok=True);UNITS=['readsb','fr24feed','adsb-rescue-shadow','adsb-rescue-feed','adsb-far-capture','adsbexchange-feed'];CONFIG=['/etc/default/readsb','/etc/default/adsb-rescue.json','/etc/default/adsb-rescue-workers.json','/etc/default/adsb-far-capture.json','/etc/fr24feed.ini']
def snap():
 s=json.loads(Path('/run/adsb-rescue/status.json').read_text());f=json.loads(Path('/run/adsb-rescue/feed-status.json').read_text());r=json.loads(Path('/run/readsb/stats.json').read_text());c=json.loads(Path('/run/adsb-far-capture/status.json').read_text());m=json.load(urllib.request.urlopen('http://127.0.0.1:8754/monitor.json',timeout=4))
 return {'unix':time.time(),'pids':{u:subprocess.check_output(['systemctl','show',u,'-p','MainPID','--value'],text=True).strip() for u in UNITS},'configs':{p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in CONFIG},'methods':s['method_switches'],'workers':s['workers']['config'],'samples':{k:r['total']['local'][k] for k in ['samples_lost','samples_dropped']},'gain_db':r['gain_db'],'updated':s['updated_unix'],'threads_alive':s['threads_alive'],'pending':s['workers']['pending_jobs'],'mean_latency_s':s['workers']['mean_batch_latency_s'],'feed_updated':f['updated_unix'],'stock_connected':f['stock_connected'],'capture_updated':c['updated_unix'],'capture_error':c['error'],'cap':c['config']['disk_limit_bytes'],'fr24':{k:m.get(k) for k in ['cfg_host','feed_status','rx_connected','timing_is_valid']},'temperature_c':int(Path('/sys/class/thermal/thermal_zone0/temp').read_text())/1000}
def healthy(base,s):
 for k in ['pids','configs','methods','workers','samples','gain_db','cap']:assert s[k]==base[k],k+' changed'
 assert s['fr24']==base['fr24'],'FR24 state changed';assert s['threads_alive'] and s['stock_connected'] and not s['capture_error'];assert time.time()-s['updated']<20 and time.time()-s['feed_updated']<10 and time.time()-s['capture_updated']<20,'Stale status';assert s['temperature_c']<75 and s['pending']<=max(4,base['pending']) and s['mean_latency_s']<max(.75,2*base['mean_latency_s']),'Protected load degraded';assert all(int(x)>0 for x in s['pids'].values())
base=snap();healthy(base,base);samples=[];child=None;PY='/home/pi/adsb-neural-rescue/.venv/bin/python';binary=ROOT/'bin/stream1090';native=ROOT/'source/libphase.so'
def run(cmd,log,cwd=None):
 global child
 with log.open('w') as f:
  child=subprocess.Popen([str(x) for x in cmd],cwd=cwd,stdout=f,stderr=subprocess.STDOUT,start_new_session=True);bad=0
  while child.poll() is None:
   time.sleep(3)
   try:s=snap();healthy(base,s);samples.append(s);bad=0
   except Exception:
    bad+=1
    if bad>=2:raise
  assert child.wait()==0,'Owned command failed: '+str(cmd)
 healthy(base,snap())
try:
 run(['c++','-O3','-std=c++20','-ffast-math','-mcpu=cortex-a76','-DSTATS_ENABLED=0','-DSTREAM1090_MIN_SNR=2.5','-DSTREAM1090_PREAMBLE_GATE=1','-DSTREAM1090_PREAMBLE_THRESHOLD=1.2','-fPIC','-I'+str(ROOT/'source'),'-c',ROOT/'source/native.cpp','-o',ROOT/'source/native.o'],OUT/'build.stdout')
 run(['c++','-O3','-std=c++20','-fPIC','-I'+str(ROOT/'source'),'-c',ROOT/'source/phase_wrap.cpp','-o',ROOT/'source/phase_wrap.o'],OUT/'wrapper-build.stdout')
 run(['c++','-shared',ROOT/'source/native.o',ROOT/'source/phase_wrap.o','-o',native],OUT/'link.stdout')
 run(['c++','-O2','-std=c++20',ROOT/'source/fenv_load.cpp','-ldl','-o',ROOT/'bin/fenv-load'],OUT/'fenv-build.stdout')
 run([ROOT/'bin/fenv-load',native],OUT/'fenv-load.stdout')
 run([PY,ROOT/'code-v3/controls.py','--root',ROOT,'--binary',binary,'--native',native,'--output',OUT/'controls.json'],OUT/'controls.stdout')
 run([PY,ROOT/'code-v3/repair_controls.py','--binary',binary,'--native',native,'--output',OUT/'repair-controls.json','--fixture-dir',ROOT/'fixtures'],OUT/'repair-controls.stdout')
 for i in range(1,2):
  dest=OUT/f'pi-{i}.json';assert not dest.exists();run([PY,ROOT/'code-v3/benchmark.py','--root',ROOT,'--binary',binary,'--native',native,'--repeat',i,'--output',dest],OUT/f'pi-{i}.stdout')
  d=json.loads(dest.read_text())
  assert all(d['digests'][k+'_native']==d['digests'][k+'_executable'] for k in ['raw','guarded','actual_extra']),'Exact executable packet/timestamp parity failed'
  run([PY,ROOT/'code-v3/attribution.py','--root',ROOT,'--result',dest,'--output',OUT/f'pi-{i}-attribution.json'],OUT/f'pi-{i}-attribution.stdout')
 result={'before':base,'after':snap(),'samples':samples,'repeats':1,'production_actions':[],'requested_limits':'nice19/core3/CPUQuota35%/MemoryMax1G/RuntimeMaxSec900; memory controller enforcement must be audited','hardware':Path('/proc/device-tree/model').read_bytes().rstrip(b'\0').decode()};(OUT/'health.private.json').write_text(json.dumps(result,indent=2))
except BaseException as e:
 if child is not None and child.poll() is None:os.killpg(child.pid,signal.SIGTERM)
 (OUT/'interrupted.private.json').write_text(json.dumps({'error':repr(e),'before':base,'samples':samples,'production_actions':[]},indent=2));raise
