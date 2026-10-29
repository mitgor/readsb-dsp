"""Copy immutable saved ADS-B datasets, verify Mac hashes, then delete exact Pi copies.
No recorder flush, service change, archive policy, or access-permission change.
"""
import hashlib,json,os,re,shlex,subprocess,time
from pathlib import Path
ROOT=Path(os.environ.get('ADSB_NEURAL_DATA_ROOT',str(Path(__file__).resolve().parents[2]))).resolve();DEST=ROOT/'data/raw/pi-offload-20261029';OUT=ROOT/'results/far-training-collection-20261029';DEST.mkdir(parents=True,exist_ok=True);OUT.mkdir(parents=True,exist_ok=True)
remote=r'''
import hashlib,json,re
from pathlib import Path
roots=[Path('/var/lib/adsb-far-capture'),Path('/var/lib/adsb-rescue'),Path('/var/lib/adsb-rescue/crc-verification'),Path('/var/lib/adsb-range-log'),Path('/var/lib/adsb-neural-rescue')];out=[]
for root in roots:
 for p in root.glob('*'):
  if not p.is_file() or p.is_symlink():continue
  if not re.fullmatch(r'(?:capture-[0-9]+\.tar|batch-[0-9]+\.jsonl\.gz)',p.name):continue
  s=p.stat();out.append(dict(path=str(p),bytes=s.st_size,mtime_ns=s.st_mtime_ns,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
print(json.dumps(out))
'''
rows=json.loads(subprocess.check_output(['ssh','adsb-rpi','sudo -n nice -n 19 taskset -c 3 python3 -'],input=remote,text=True));run=str(time.time_ns());manifest={'run':run,'files':[],'policy':'Only immutable named capture tar / batch jsonl.gz; live RAM, configurations, graphs and active buffers excluded.'}
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while b:=f.read(1024**2):h.update(b)
 return h.hexdigest()
for r in rows:
 relative=Path(r['path']).relative_to('/');target=DEST/relative;target.parent.mkdir(parents=True,exist_ok=True)
 if not target.exists():
  # Reuse immutable, checksum-matched earlier Mac copies without downloading duplicates.
  candidates=list((ROOT/'data/raw').rglob(Path(r['path']).name));source=next((p for p in candidates if p.is_file() and p.stat().st_size==r['bytes'] and sha(p)==r['sha256']),None)
  if source:os.link(source,target)
  else:subprocess.run(['rsync','-a','adsb-rpi:'+r['path'],str(target)],check=True)
 assert target.is_file() and target.stat().st_size==r['bytes'] and sha(target)==r['sha256'],r['path']
 manifest['files'].append(dict(r,local=str(target),mac_verified=True))
manifest['verified_bytes']=sum(r['bytes'] for r in rows);p=OUT/('offload-'+run+'.json');p.write_text(json.dumps(manifest,indent=2)+'\n')
# All Mac data is verified and durable before any source deletion.
for r in manifest['files']:
 with open(r['local'],'rb') as f:os.fsync(f.fileno())
for directory in {str(Path(r['local']).parent) for r in manifest['files']}:
 fd=os.open(directory,os.O_RDONLY)
 try:os.fsync(fd)
 finally:os.close(fd)
code='expected='+repr(rows)+'\n'+r'''
import hashlib,json,os,re
from pathlib import Path
allowed={Path('/var/lib/adsb-far-capture'),Path('/var/lib/adsb-rescue'),Path('/var/lib/adsb-rescue/crc-verification'),Path('/var/lib/adsb-range-log'),Path('/var/lib/adsb-neural-rescue')};out=[]
for r in expected:
 p=Path(r['path']);assert re.fullmatch(r'(?:capture-[0-9]+\.tar|batch-[0-9]+\.jsonl\.gz)',p.name);assert p.parent in allowed and p.resolve()==p and not p.is_symlink();s=p.stat();assert s.st_size==r['bytes'] and s.st_mtime_ns==r['mtime_ns'];assert hashlib.sha256(p.read_bytes()).hexdigest()==r['sha256'];p.unlink();out.append(str(p))
for d in {str(Path(p).parent) for p in out}:
 fd=os.open(d,os.O_RDONLY)
 try:os.fsync(fd)
 finally:os.close(fd)
print(json.dumps({'deleted':out}))
'''
result=json.loads(subprocess.check_output(['ssh','adsb-rpi','sudo -n nice -n 19 taskset -c 3 python3 -'],input=code,text=True));manifest.update(result,deleted_bytes=manifest['verified_bytes']);p.write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps({'manifest':str(p),'files':len(rows),'verified_and_deleted_bytes':manifest['verified_bytes']}))
