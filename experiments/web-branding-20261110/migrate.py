#!/usr/bin/env python3
"""Owned receiver web-only migration. Keeps decoding, logs and service paths intact."""
import hashlib,json,subprocess,time
from pathlib import Path
BACKUP=Path('/var/backups/readsb-dsp-web-20261110')
CONF=Path('/etc/lighttpd/conf-available/99-neural-rescue.conf')
WEB=Path('/usr/share/adsb-rescue')
CONTROL=Path('/home/pi/adsb-neural-rescue/src/rescue/web_control.py')
SERVICES=('readsb','fr24feed','adsb-rescue-feed','adsb-rescue-shadow','adsb-far-capture','adsbexchange-feed')
def pids():
 return {n:subprocess.check_output(['systemctl','show',n,'--property=MainPID','--value'],text=True).strip() for n in SERVICES}
def main():
 if BACKUP.exists():raise RuntimeError('Migration backup already exists; inspect instead of overwriting')
 oldconf=CONF.read_text()
 if '/readsb-dsp/' in oldconf:raise RuntimeError('Canonical mapping already exists')
 oldcontrol=CONTROL.read_text()
 marker="self.path!='/neural-rescue/api/settings'"
 if oldcontrol.count(marker)!=2:raise RuntimeError('Control source changed; inspect before migration')
 newcontrol=oldcontrol.replace(marker,"self.path not in ('/readsb-dsp/api/settings','/neural-rescue/api/settings')")
 # Keep original aliases, then add the same mappings under the canonical prefix.
 newconf=oldconf+'\n# Canonical readsb-dsp URLs; compatibility mappings above remain valid.\n'+oldconf.replace('/neural-rescue/','/readsb-dsp/').replace('/usr/share/adsb-rescue/','/usr/share/readsb-dsp/')
 changed={CONF:newconf.encode(),CONTROL:newcontrol.encode()}
 for path in WEB.rglob('*.html'):
  if path.is_symlink():continue
  text=path.read_bytes();new=text.replace(b'/neural-rescue/',b'/readsb-dsp/')
  if path==WEB/'index.html':new=new.replace(b'ADS-B rescue statistics',b'readsb-dsp statistics').replace(b'<h1>ADS-B rescue</h1>',b'<h1>readsb-dsp</h1>')
  if new!=text:changed[path]=new
 canonical=Path('/usr/share/readsb-dsp')
 if canonical.exists() or canonical.is_symlink():raise RuntimeError('Canonical web directory already exists')
 before=pids();BACKUP.mkdir(mode=0o700)
 originals={p:p.read_bytes() for p in changed}
 manifest=[]
 for i,(path,data) in enumerate(originals.items()):
  backup=BACKUP/str(i);backup.write_bytes(data)
  manifest.append(dict(path=str(path),backup=str(backup),sha256=hashlib.sha256(data).hexdigest(),new_sha256=hashlib.sha256(changed[path]).hexdigest()))
 (BACKUP/'manifest.json').write_text(json.dumps(manifest,indent=2))
 try:
  canonical.symlink_to(WEB,target_is_directory=True)
  for path,data in changed.items():path.write_bytes(data)
  subprocess.run(['lighttpd','-tt','-f','/etc/lighttpd/lighttpd.conf'],check=True)
  subprocess.run(['systemctl','restart','adsb-rescue-web'],check=True)
  subprocess.run(['systemctl','reload','lighttpd'],check=True)
  import urllib.request
  for endpoint in ('readsb-dsp/','readsb-dsp/status.json','readsb-dsp/api/settings','neural-rescue/api/settings','readsb-dsp/feed-status.json','readsb-dsp/capture-status.json','readsb-dsp/range-map/'):
   with urllib.request.urlopen('http://127.0.0.1/'+endpoint,timeout=10) as r:
    data=r.read()
    if r.status!=200:raise RuntimeError(endpoint)
    if endpoint.endswith('.json') or 'api/settings' in endpoint:json.loads(data)
  after=pids()
  if before!=after:raise RuntimeError('Protected process changed during web migration')
  (BACKUP/'result.json').write_text(json.dumps(dict(before=before,after=after,changed_files=len(changed),canonical_url='/readsb-dsp/',verified_unix=time.time()),indent=2))
 except Exception:
  for path,data in originals.items():path.write_bytes(data)
  canonical.unlink(missing_ok=True)
  subprocess.run(['systemctl','restart','adsb-rescue-web'])
  subprocess.run(['systemctl','reload','lighttpd'])
  raise
 print((BACKUP/'result.json').read_text())
if __name__=='__main__':main()
