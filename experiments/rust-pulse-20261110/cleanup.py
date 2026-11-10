"""Delete only exact closed owned tmpfs after durable byte/checksum verification."""
from pathlib import Path
import json,hashlib,subprocess,os
D=Path('/Users/mit/Documents/!project/adsb-neural-rescue/results/rust-pulse-20261110');r=json.loads((D/'target-receipt.json').read_text());p=D/'target-evidence.private.tar';assert p.stat().st_size==r['bytes'];h=hashlib.sha256()
with p.open('rb') as f:
 while b:=f.read(1024*1024):h.update(b)
assert h.hexdigest()==r['sha256'] and r['verified'] and r['durable'];m=json.loads((D/'target-files.private.json').read_text())
code='M='+repr(m)+r'''
from pathlib import Path
import subprocess,hashlib,shutil,json
for u in ['adsb-rust-pulse-20261110']:assert subprocess.run(['systemctl','is-active','--quiet',u]).returncode!=0
D=Path('/dev/shm/adsb-rust-pulse-20261110');assert D.is_dir() and not D.is_symlink();assert {str(p.relative_to(D)) for p in D.rglob('*') if p.is_file() or p.is_symlink()}==set(M)
for n,v in M.items():
 p=D/n;st=p.lstat();assert st.st_ino==v['inode'] and st.st_mtime_ns==v['mtime_ns']
 if 'symlink' in v:assert p.is_symlink() and str(p.readlink())==v['symlink'];continue
 assert p.is_file() and not p.is_symlink() and st.st_size==v['bytes'];h=hashlib.sha256()
 with p.open('rb') as f:
  while b:=f.read(1024*1024):h.update(b)
 assert h.hexdigest()==v['sha256']
shutil.rmtree(D);print(json.dumps(dict(owned_tmpfs_removed=str(D),persistent_archives_deleted=False,production_changed=False)))
'''
raw=subprocess.check_output(['ssh','adsb-rpi','sudo','nice','-n','19','taskset','-c','3','python3','-'],input=code,text=True,timeout=120);(D/'cleanup.json').write_text(raw)
with (D/'cleanup.json').open('rb') as f:os.fsync(f.fileno())
print(raw)
