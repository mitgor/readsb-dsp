import json,hashlib,subprocess,shutil,urllib.request,time
from pathlib import Path
before={'/usr/share/adsb-rescue/index.html': '66b781d98153c9a45cdd78cc1246dd1961e22be9ffad516e49aa98544b7fb6a4', '/home/pi/adsb-neural-rescue/src/rescue/web_control.py': '3ab734affba9ae7ae96f229dcdc4e5fed525f26373ebf023292500dae7008544'}
backup=Path('/var/backups/readsb-dsp-dashboard-loading-20261110-v2');backup.mkdir(mode=0o700)
services=('readsb','fr24feed','adsb-rescue-shadow','adsb-rescue-feed','adsb-far-capture','adsbexchange-feed')
def pids():return {s:subprocess.check_output(['systemctl','show',s,'--property=MainPID','--value'],text=True).strip() for s in services}
original=pids()
for path,sha in before.items():
 p=Path(path)
 assert hashlib.sha256(p.read_bytes()).hexdigest()==sha, 'Concurrent change: '+path
 shutil.copy2(p,backup/p.name)
module=Path('/home/pi/adsb-neural-rescue/src/rescue/dashboard_status.py')
assert not module.exists()
try:
 shutil.copyfile('/tmp/readsb-dsp-dashboard-status.py',module)
 shutil.copyfile('/tmp/readsb-dsp-web-control-fixed.py','/home/pi/adsb-neural-rescue/src/rescue/web_control.py')
 shutil.copyfile('/tmp/readsb-dsp-dashboard-fixed.html','/usr/share/adsb-rescue/index.html')
 subprocess.run(['systemctl','restart','adsb-rescue-web'],check=True)
 for attempt in range(40):
  try:
   with urllib.request.urlopen('http://127.0.0.1/readsb-dsp/api/dashboard-status',timeout=2) as r:json.load(r)
   break
  except OSError:
   if attempt==39:raise
   time.sleep(.25)
 for prefix in ('readsb-dsp','neural-rescue'):
  with urllib.request.urlopen('http://127.0.0.1/'+prefix+'/api/dashboard-status',timeout=5) as r:
   data=r.read();status=json.loads(data)
   assert 'distance' in status and 'crc_research_recent' not in status
  print(prefix,len(data))
 assert pids()==original,'Protected service changed'
 (backup/'result.json').write_text(json.dumps(dict(protected_pids=original,bytes=len(data),files=before),indent=2))
except Exception:
 for path in before:shutil.copyfile(backup/Path(path).name,path)
 module.unlink(missing_ok=True)
 subprocess.run(['systemctl','restart','adsb-rescue-web'])
 raise
