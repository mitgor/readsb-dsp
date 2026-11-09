#!/usr/bin/env python3
"""Read-only closure evidence acquisition. Private destination, no receiver mutations."""
import subprocess,json,hashlib,os,tarfile,io,datetime
from pathlib import Path
DEST=Path('/Users/mit/Documents/!project/adsb-neural-rescue/incidents/fr24-drop-20261027/native-fr24-20261107/review-20261109');DEST.mkdir(parents=True,exist_ok=True)
remote=r'''
import pathlib,json,subprocess,urllib.request,tarfile,io,hashlib,time,base64
D=pathlib.Path('/var/lib/adsb-fr24-native-20261107-v4');s=json.loads((D/'state.json').read_text());assert s.get('closed'), 'Still active; refuse closure copy'
paths=[D,pathlib.Path('/run/adsb-fr24-native-20261107-v4')]
files={}
for root in paths:
 for p in root.rglob('*'):
  if p.is_file() and not p.is_symlink():files[str(p)]=p.read_bytes()
start=int(s['measurement_start_unix']);end=int(s['closed_unix'])
for unit in ['fr24feed','readsb','adsb-rescue-feed','adsb-fr24-native-health-20261107-v4','adsb-rescue-shadow','adsb-far-capture']:
 files['journals/'+unit+'.jsonl']=subprocess.check_output(['journalctl','-u',unit,'--since','@'+str(start-600),'--until','@'+str(end+600),'-o','json','--no-pager'])
units=['readsb','fr24feed','adsb-rescue-shadow','adsb-rescue-feed','adsb-far-capture','adsbexchange-feed','adsb-rescue-feed-guard.timer','adsb-unified-graphs.timer']
live=dict(unix=time.time(),services={u:subprocess.getoutput('systemctl show '+u+' -p ActiveState -p MainPID -p FreezerState') for u in units})
try:
 m=json.load(urllib.request.urlopen('http://127.0.0.1:8754/monitor.json',timeout=5));live['fr24']={k:m.get(k) for k in ['num_messages','feed_status','rx_connected','feed_num_ac_tracked','timing_is_valid','feed_current_mode']}
except Exception as e:live['fr24_error']=str(e)
for name,p in [('capture','/run/adsb-far-capture/status.json'),('shadow','/run/adsb-rescue-shadow/status.json')]:
 try:live[name]=json.loads(pathlib.Path(p).read_text())
 except Exception as e:live[name+'_error']=str(e)
live['config_restoration']=[{'path':r['path'],'originally_exists':r['exists'],'matches':(pathlib.Path(r['path']).exists() and hashlib.sha256(pathlib.Path(r['path']).read_bytes()).hexdigest()==r['sha256']) if r['exists'] else not pathlib.Path(r['path']).exists()} for r in s['files']]
live['native_timers']=subprocess.getoutput("systemctl list-timers --all --no-legend 'adsb-fr24-native*'")
live['readsb_options']=pathlib.Path('/etc/default/readsb').read_text()
live['fr24_config']=pathlib.Path('/etc/fr24feed.ini').read_text()
files['live.private.json']=json.dumps(live,indent=2).encode()
manifest={k:dict(bytes=len(v),sha256=hashlib.sha256(v).hexdigest()) for k,v in files.items()}
files['remote-manifest.json']=json.dumps(manifest,indent=2).encode()
b=io.BytesIO()
with tarfile.open(fileobj=b,mode='w:gz') as t:
 for n,v in files.items():
  i=tarfile.TarInfo(n.lstrip('/'));i.size=len(v);i.mode=0o600;t.addfile(i,io.BytesIO(v))
import sys
sys.stdout.buffer.write(b.getvalue())
'''
b=subprocess.check_output(['ssh','-o','ConnectTimeout=15','adsb-rpi','sudo','python3','-'],input=remote.encode(),timeout=120)
p=DEST/'closure-evidence.private.tar.gz'
assert not p.exists(),'Do not overwrite closure evidence'
p.write_bytes(b);p.chmod(0o600)
with p.open('rb') as f:os.fsync(f.fileno())
with tarfile.open(p) as t:
 m=json.load(t.extractfile('remote-manifest.json'))
 for n,r in m.items():
  v=t.extractfile(n.lstrip('/')).read();assert len(v)==r['bytes'] and hashlib.sha256(v).hexdigest()==r['sha256']
 # Extract only after member identity verified; every destination stays below private directory.
 for member in t.getmembers():
  assert member.isfile() and not member.name.startswith('/') and '..' not in Path(member.name).parts
  out=DEST/'files'/member.name;out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(t.extractfile(member).read());out.chmod(0o600)
  with out.open('rb') as f:os.fsync(f.fileno())
for d in [DEST,DEST/'files',*[p for p in (DEST/'files').rglob('*') if p.is_dir()]]:
 fd=os.open(d,os.O_RDONLY);os.fsync(fd);os.close(fd)
r=dict(collected_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),bytes=len(b),sha256=hashlib.sha256(b).hexdigest(),members_verified=len(m),remote_mutations=False,forced_flush=False,manifest=m)
(DEST/'transfer-receipt.private.json').write_text(json.dumps(r,indent=2)+'\n')
with (DEST/'transfer-receipt.private.json').open('rb') as f:os.fsync(f.fileno())
fd=os.open(DEST,os.O_RDONLY);os.fsync(fd);os.close(fd)
print(json.dumps({k:v for k,v in r.items() if k!='manifest'}))
