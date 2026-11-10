"""Bounded range reads from existing LAN HTTP export, original bytes verified.
No source deletion; normal safe offloader separately rechecks and owns deletion.
"""
from pathlib import Path
import subprocess,json,hashlib,os,urllib.request,concurrent.futures,time
R=Path('/Users/mit/Documents/!project/adsb-neural-rescue');O=R/'results/daily-20261110';D=R/'data/raw/prefetch-20261110';name='capture-1794265240739666672.tar';remote='/var/lib/adsb-far-capture/'+name
code="from pathlib import Path;import json,hashlib;p=Path("+repr(remote)+");assert not p.is_symlink();print(json.dumps({'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}))"
r=json.loads(subprocess.check_output(['ssh','-o','ConnectTimeout=8','adsb-rpi','sudo -n nice -n 19 taskset -c 3 python3 -'],input=code,text=True));part=D/(name+'.part');assert part.exists();prefix=part.stat().st_size;assert prefix<=r['bytes'];fd=os.open(part,os.O_RDWR);os.ftruncate(fd,r['bytes']);url='http://192.168.2.195/neural-rescue/captures/'+name;chunk=1024**2
ranges=[(n,min(n+chunk,r['bytes'])-1) for n in range(prefix,r['bytes'],chunk)];started=time.monotonic()
def get(pair):
 lo,hi=pair
 for attempt in range(3):
  try:
   req=urllib.request.Request(url,headers={'Range':f'bytes={lo}-{hi}'})
   with urllib.request.urlopen(req,timeout=30) as response:
    assert response.status==206 and response.headers['Content-Range']==f'bytes {lo}-{hi}/{r["bytes"]}';b=response.read(hi-lo+2);assert len(b)==hi-lo+1
   at=0
   while at<len(b):at+=os.pwrite(fd,b[at:],lo+at)
   return len(b)
  except Exception:
   if attempt==2:raise
   time.sleep(1)
try:
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
  n=0
  for b in pool.map(get,ranges):
   n+=b
   if n%(8*chunk)<chunk:print('HTTP original bytes',prefix+n,'of',r['bytes'],flush=True)
 os.fsync(fd)
finally:os.close(fd)
assert hashlib.sha256(part.read_bytes()).hexdigest()==r['sha256'];dest=D/name;assert not dest.exists();part.rename(dest);fd=os.open(D,os.O_RDONLY);os.fsync(fd);os.close(fd)
receipt={**r,'local':str(dest),'original_prefix_bytes':prefix,'range_threads':4,'wall_seconds':time.monotonic()-started,'verified':True,'source_deleted':False}
with (O/'prefetch-receipt.json').open('w') as f:json.dump(receipt,f,indent=2);f.flush();os.fsync(f.fileno())
print(json.dumps(receipt))
