"""Stream closed isolated target evidence to durable checksum-verified Mac tar."""
from pathlib import Path
import subprocess,tarfile,hashlib,json,os
D=Path('/Users/mit/Documents/!project/adsb-neural-rescue/results/rust-stream-20261109');dest=D/'target-evidence.private.tar';assert not dest.exists()
code=r'''
from pathlib import Path
import subprocess,sys,tarfile,io,json,hashlib
for u in ['adsb-rust-stream-20261109','adsb-rust-stream-v2-20261109','adsb-rust-stream-final-20261109','adsb-rust-stream-timing-20261109','adsb-rust-stream-complete-20261109']:assert subprocess.run(['systemctl','is-active','--quiet',u]).returncode!=0
D=Path('/dev/shm/adsb-rust-stream-20261109');m={}
h=json.loads((D/'protected-complete.private.json').read_text());assert h['error'] is None and h['before']==h['after']
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|') as t:
 for p in sorted(D.rglob('*')):
  if p.is_symlink():
   # Temporary toolchain contains compiler-managed symlinks; preserve, never follow.
   n=str(p.relative_to(D));link=p.readlink().as_posix();st=p.lstat();i=tarfile.TarInfo(n);i.type=tarfile.SYMTYPE;i.linkname=link;t.addfile(i);m[n]=dict(symlink=link,inode=st.st_ino,mtime_ns=st.st_mtime_ns);continue
  if not p.is_file():continue
  n=str(p.relative_to(D));st=p.stat();raw=p.read_bytes();i=tarfile.TarInfo(n);i.size=len(raw);t.addfile(i,io.BytesIO(raw));m[n]=dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),inode=st.st_ino,mtime_ns=st.st_mtime_ns)
 raw=json.dumps(m).encode();i=tarfile.TarInfo('transfer-manifest.json');i.size=len(raw);t.addfile(i,io.BytesIO(raw))
'''
with dest.open('wb') as f:
 subprocess.run(['ssh','adsb-rpi','sudo','nice','-n','19','taskset','-c','3','python3','-'],input=code.encode(),stdout=f,check=True,timeout=240);f.flush();os.fsync(f.fileno())
dest.chmod(0o600)
with tarfile.open(dest) as t:
 m=json.load(t.extractfile('transfer-manifest.json'))
 for n,v in m.items():
  member=t.getmember(n)
  if 'symlink' in v:assert member.issym() and member.linkname==v['symlink'];continue
  f=t.extractfile(n);h=hashlib.sha256();size=0
  while b:=f.read(1024*1024):h.update(b);size+=len(b)
  assert size==v['bytes'] and h.hexdigest()==v['sha256'],n
 for n in ['pi-final.json','protected-final.private.json','job-final.log','protected-complete.private.json','job-complete.log','pi-production-timing.json','gprof.txt']:(D/n).write_bytes(t.extractfile(n).read())
h=hashlib.sha256()
with dest.open('rb') as f:
 while b:=f.read(1024*1024):h.update(b)
receipt=dict(bytes=dest.stat().st_size,sha256=h.hexdigest(),members=len(m),verified=True,durable=True)
(D/'target-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');(D/'target-files.private.json').write_text(json.dumps(m)+'\n')
for p in D.iterdir():
 if p.is_file():
  with p.open('rb') as f:os.fsync(f.fileno())
fd=os.open(D,os.O_RDONLY);os.fsync(fd);os.close(fd)
print(json.dumps(receipt))
