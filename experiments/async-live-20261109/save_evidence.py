"""Checksum-verified durable private activation backup; no receiver deletions."""
from pathlib import Path
import subprocess,json,hashlib,tarfile,io,os,argparse
P=Path('/Users/mit/Documents/!project/adsb-neural-rescue');parser=argparse.ArgumentParser();parser.add_argument('--dest',type=Path,default=P/'results/async-live-20261109');args=parser.parse_args();D=args.dest;D.mkdir(parents=True,exist_ok=False)
code=r'''
import pathlib,tarfile,io,hashlib,json,subprocess,time,urllib.request
P=pathlib.Path;paths=list(P('/var/lib/adsb-async-live-20261109').glob('*'))+list(P('/home/pi/adsb-neural-rescue/src/rescue').glob('async_live_*.py'))+list(P('/run/adsb-async-live-preflight-20261109').glob('*.py'))+[P('/run/adsb-async-live-preflight-20261109/observation.private.json'),P('/etc/default/adsb-rescue.json'),P('/etc/default/adsb-rescue-workers.json'),P('/etc/systemd/system/adsb-rescue-feed.service.d/99-asynchronous.conf'),P('/etc/systemd/system/adsb-rescue-shadow.service.d/99-asynchronous.conf'),P('/etc/systemd/system/adsb-async-live-20261109.service'),P('/etc/systemd/system/adsb-async-live-20261109.timer')]
b=io.BytesIO();manifest={}
with tarfile.open(fileobj=b,mode='w:gz') as t:
 def add(n,raw):
  member=tarfile.TarInfo(n);member.size=len(raw);t.addfile(member,io.BytesIO(raw));manifest[n]=dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
 for p in paths:
  assert p.is_file() and not p.is_symlink();add(str(p).lstrip('/'),p.read_bytes())
 for name,path in [('final-worker.private.json','/run/adsb-rescue/status.json'),('final-feed.json','/run/adsb-rescue/feed-status.json'),('final-collector.private.json','/run/adsb-far-capture/status.json'),('final-guard.json','/run/adsb-async-live-20261109/status.json')]:add(name,P(path).read_bytes())
 services=['readsb','fr24feed','adsb-far-capture','adsb-rescue-feed','adsb-rescue-shadow','adsbexchange-feed'];pids={u:subprocess.check_output(['systemctl','show',u,'-p','MainPID','--value'],text=True).strip() for u in services};m=json.load(urllib.request.urlopen('http://127.0.0.1:8754/monitor.json',timeout=3));add('final-health.json',json.dumps(dict(unix=time.time(),pids=pids,fr24_feed=m.get('feed_status'),fr24_receiver=m.get('rx_connected'),rollback_active=subprocess.run(['systemctl','is-active','--quiet','adsb-async-live-20261109.timer']).returncode==0,rollback_occurred=P('/var/lib/adsb-async-live-20261109/outcome.json').exists())).encode())
 raw=json.dumps(manifest,indent=2).encode();i=tarfile.TarInfo('manifest.json');i.size=len(raw);t.addfile(i,io.BytesIO(raw))
import sys;sys.stdout.buffer.write(b.getvalue())
'''
raw=subprocess.check_output(['ssh','adsb-rpi','sudo','python3','-'],input=code.encode(),timeout=30);f=D/'evidence.tar.gz';f.write_bytes(raw);f.chmod(0o600)
with f.open('rb') as h:os.fsync(h.fileno())
with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as t:
 manifest=json.load(t.extractfile('manifest.json'))
 for n,row in manifest.items():
  data=t.extractfile(n).read();assert len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256']
  if n in ['final-feed.json','final-guard.json','final-health.json','run/adsb-async-live-preflight-20261109/observation.private.json']:
   out=D/Path(n).name;out.write_bytes(data);out.chmod(0o600)
receipt=dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),verified_members=len(manifest),durable=True);r=D/'receipt.json';r.write_text(json.dumps(receipt,indent=2)+'\n')
for p in D.iterdir():
 with p.open('rb') as h:os.fsync(h.fileno())
fd=os.open(D,os.O_RDONLY);os.fsync(fd);os.close(fd);print(json.dumps(receipt))
