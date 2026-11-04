"""Daily immutable offload with durable backup/manifest before exact source unlink.
Derived from scripts/collection/offload_20261029.py; no flush or service change.
"""
import os,re,json,time,hashlib,subprocess,shlex,uuid
from pathlib import Path
ROOT=Path(os.environ.get('ADSB_NEURAL_DATA_ROOT','/Users/mit/Documents/!project/adsb-neural-rescue'));O=ROOT/'results/daily-20261104';DEST=ROOT/'data/raw/pi-offload-20261104';DEST.mkdir(parents=True,exist_ok=True);RUN=str(time.time_ns());M=O/('offload-'+RUN+'.json')
COMMON=r'''
import os,re,json,hashlib,time
from pathlib import Path
ALLOWED={Path('/var/lib/adsb-far-capture'),Path('/var/lib/adsb-rescue'),Path('/var/lib/adsb-rescue/crc-verification'),Path('/var/lib/adsb-range-log'),Path('/var/lib/adsb-neural-rescue')}
PAT=re.compile(r'(?:capture-[0-9]+\.tar|batch-[0-9]+\.jsonl\.gz)')
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while b:=f.read(1024**2):h.update(b)
 return h.hexdigest()
def identity(s):return {'device':s.st_dev,'inode':s.st_ino,'bytes':s.st_size,'mtime_ns':s.st_mtime_ns}
def writers(paths):
 found=set()
 for d in Path('/proc').glob('[0-9]*'):
  try:fds=list((d/'fd').iterdir())
  except OSError:continue
  for fd in fds:
   try:
    target=os.readlink(fd)
    if target in paths:
     flags=next(l.split()[1] for l in (d/'fdinfo'/fd.name).read_text().splitlines() if l.startswith('flags:'))
     if int(flags,8)&3:found.add(target)
   except (OSError,StopIteration):continue
 return found
'''
code=COMMON+r'''
rows=[];skipped=[];candidates=[]
for root in ALLOWED:
 for p in root.glob('*'):
  if p.is_symlink() or not p.is_file() or not PAT.fullmatch(p.name):continue
  if time.time()-p.stat().st_mtime<60:skipped.append({'path':str(p),'reason':'too_recent'});continue
  candidates.append(p)
open_writers=writers({str(p) for p in candidates})
for p in candidates:
 if str(p) in open_writers:skipped.append({'path':str(p),'reason':'write_descriptor_open'});continue
 a=identity(p.stat());digest=sha(p);b=identity(p.stat())
 if a!=b:skipped.append({'path':str(p),'reason':'changed_during_hash'});continue
 rows.append({'path':str(p),'sha256':digest,**a})
print(json.dumps({'files':rows,'skipped':skipped}))
'''
def remote(code):return subprocess.check_output(['ssh','-o','ConnectTimeout=10','adsb-rpi','sudo -n nice -n 19 taskset -c 3 python3 -'],input=code,text=True)
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while b:=f.read(1024**2):h.update(b)
 return h.hexdigest()
def sync_dir(p):
 fd=os.open(p,os.O_RDONLY)
 try:os.fsync(fd)
 finally:os.close(fd)
def save(d):
 tmp=M.with_suffix('.tmp')
 with tmp.open('w') as f:json.dump(d,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
 tmp.replace(M);sync_dir(O)
inv=json.loads(remote(code));manifest={'run':RUN,'started_unix':time.time(),'policy':'Final named immutable files only, no open writers; durable byte/SHA verified Mac backup and manifest before identity/hash recheck and exact deletion. No capture flush or live change.','skipped':inv['skipped'],'files':[]};save(manifest)
for r in inv['files']:
 target=DEST/Path(r['path']).relative_to('/');target.parent.mkdir(parents=True,exist_ok=True);reused=False
 if not target.exists():
  source=None
  for f in (ROOT/'data/raw').rglob(Path(r['path']).name):
   if f.is_file() and not f.is_symlink() and f.stat().st_size==r['bytes'] and sha(f)==r['sha256']:source=f;break
  if source:os.link(source,target);reused=True
  else:
   part=target.with_name('.'+target.name+'.'+uuid.uuid4().hex+'.part');subprocess.run(['rsync','-a','--','adsb-rpi:'+r['path'],str(part)],check=True);assert part.stat().st_size==r['bytes'] and sha(part)==r['sha256'];part.replace(target)
 assert target.is_file() and not target.is_symlink() and target.stat().st_size==r['bytes'] and sha(target)==r['sha256']
 with target.open('rb') as f:os.fsync(f.fileno())
 parent=target.parent
 while True:
  sync_dir(parent)
  if parent==ROOT:break
  parent=parent.parent
 entry={**r,'local':str(target),'reused_existing_mac':reused,'mac_verified_durable':True,'remote_deleted':False};manifest['files'].append(entry);save(manifest)
 # Recheck file identity, active writer status and content immediately before unlink.
 delete=COMMON+'\nr='+repr(r)+'\n'+r'''
p=Path(r['path']);assert p.parent in ALLOWED and PAT.fullmatch(p.name) and not p.is_symlink() and p.resolve()==p
assert identity(p.stat())=={k:r[k] for k in ['device','inode','bytes','mtime_ns']}
assert not writers({str(p)})
assert sha(p)==r['sha256']
assert identity(p.stat())=={k:r[k] for k in ['device','inode','bytes','mtime_ns']}
p.unlink();fd=os.open(p.parent,os.O_RDONLY)
try:os.fsync(fd)
finally:os.close(fd)
print(json.dumps({'deleted':str(p),'sha256':r['sha256'],'identity_verified':True}))
'''
 try:entry['deletion_receipt']=json.loads(remote(delete));entry['remote_deleted']=True;entry['deleted_unix']=time.time();save(manifest)
 except Exception as e:entry['deletion_error']=repr(e);save(manifest);raise
manifest.update(completed_unix=time.time(),verified_bytes=sum(r['bytes'] for r in manifest['files']),deleted_bytes=sum(r['bytes'] for r in manifest['files'] if r['remote_deleted']));save(manifest);print(json.dumps({'manifest':str(M),'files':len(manifest['files']),'verified_deleted_bytes':manifest['deleted_bytes'],'skipped':manifest['skipped']}))
