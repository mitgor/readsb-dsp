"""Repair dashboard accounting/API; preserve receiver/feeder/collector and configs."""
import base64,json,subprocess,argparse
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--build',type=Path,required=True);p.add_argument('--web',type=Path,required=True);a=p.parse_args();names=['async_live_engine.py','async_live_shadow.py'];files={n:base64.b64encode((a.build/n).read_bytes()).decode() for n in names};files['web_control.py']=base64.b64encode(a.web.read_bytes()).decode();manifest=json.loads((a.build/'manifest.json').read_text())
code=r'''
from pathlib import Path
import os,json,base64,hashlib,time,subprocess,urllib.request
D=Path('/var/lib/adsb-async-dashboard-fix-20261109');assert not D.exists();ROOT=Path('/home/pi/adsb-neural-rescue/src/rescue');PROFILE=Path('/var/lib/adsb-async-live-20261109');state=json.loads((PROFILE/'activation.json').read_text());assert not (PROFILE/'outcome.json').exists()
def sha(raw):return hashlib.sha256(raw).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def call(*a):return subprocess.run(a,check=True,timeout=100,stdout=subprocess.DEVNULL)
def atomic(p,raw):
 st=p.stat();t=p.with_suffix('.fix-tmp');t.write_bytes(raw);t.chmod(st.st_mode&0o777);os.chown(t,st.st_uid,st.st_gid);os.replace(t,p)
s=read('/run/adsb-rescue/status.json');f=read('/run/adsb-rescue/feed-status.json');assert f['asynchronous'] and f['stock_connected'] and not s['method_switches']['sic']
for n,h in state['manifest']['files'].items():assert sha((ROOT/n).read_bytes())==h
assert b'current=self.read()\n   if m==' not in (ROOT/'web_control.py').read_bytes()
for sub,key in [('',s['archive']),('/crc-verification',s['crc_verification']['archive'])]:
 used=sum(p.stat().st_size for p in Path('/var/lib/adsb-rescue'+sub).glob('batch-*.jsonl.gz'));assert not key.get('error') and used+key['compressed_ram_bytes']+8*1048576<512*1048576
D.mkdir(mode=0o700);(D/'before-worker.private.json').write_text(json.dumps(s));(D/'before-feed.json').write_text(json.dumps(f));(D/'profile.before.json').write_bytes((PROFILE/'activation.json').read_bytes())
pids={u:subprocess.check_output(['systemctl','show',u,'-p','MainPID','--value'],text=True).strip() for u in ['readsb','fr24feed','adsb-rescue-feed','adsb-far-capture','adsbexchange-feed']};files={n:base64.b64decode(b) for n,b in FILES.items()}
for n,raw in files.items():(D/(n+'.before')).write_bytes((ROOT/n).read_bytes())
# Finite independent guard-resume timer survives interruption of this installer.
call('systemd-run','--unit=adsb-async-dashboard-resume-20261109','--on-active=90s','/usr/bin/systemctl','start','adsb-async-live-20261109.timer')
call('systemctl','stop','adsb-async-live-20261109.timer');call('systemctl','stop','adsb-async-live-20261109.service')
try:
 for n,raw in files.items():atomic(ROOT/n,raw)
 state['manifest']=MANIFEST;atomic(PROFILE/'activation.json',(json.dumps(state,indent=2)+'\n').encode())
 call('systemctl','restart','adsb-rescue-web')
 began=time.time();call('systemctl','restart','adsb-rescue-shadow')
 for _ in range(80):
  s=read('/run/adsb-rescue/status.json')
  if s['started_unix']>=began and s['method_metrics']['methods']['stream1090']['cpu_seconds']>0 and s['async_output']['stream_child_cpu_s']>0 and s['health'].get('gain_db')==state['gain']:break
  time.sleep(.5)
 else:raise RuntimeError('Stream1090 metrics did not become live')
 settings=json.load(urllib.request.urlopen('http://127.0.0.1:8911/neural-rescue/api/settings',timeout=3));assert settings['capture']['disk_limit_bytes']==5000000000 and settings['methods']['sic'] is False
 assert all(subprocess.check_output(['systemctl','show',u,'-p','MainPID','--value'],text=True).strip()==pid for u,pid in pids.items())
 (D/'outcome.json').write_text(json.dumps(dict(result='fixed',pids=pids,files={n:sha(raw) for n,raw in files.items()},unix=time.time()),indent=2)+'\n')
 print(json.dumps(dict(result='fixed',settings_HTTP=200,stream_cpu_seconds=s['method_metrics']['methods']['stream1090']['cpu_seconds'],protected_pids=pids)))
except BaseException:
 for n in files:atomic(ROOT/n,(D/(n+'.before')).read_bytes())
 atomic(PROFILE/'activation.json',(D/'profile.before.json').read_bytes());call('systemctl','restart','adsb-rescue-web');call('systemctl','restart','adsb-rescue-shadow');raise
finally:call('systemctl','start','adsb-async-live-20261109.timer')
'''
script='FILES='+repr(files)+'\nMANIFEST='+repr(manifest)+'\n'+code
print(subprocess.check_output(['ssh','adsb-rpi','sudo','python3','-'],input=script,text=True,timeout=200))
