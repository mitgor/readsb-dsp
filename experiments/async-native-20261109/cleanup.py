#!/usr/bin/env python3
"""Durable, checksum-verified backup before deleting only exact closed experiment roots."""
import json,subprocess,tarfile,io,hashlib,os
from pathlib import Path
D=Path('/Users/mit/Documents/!project/adsb-neural-rescue/results/async-native-20261109/closure');D.mkdir(parents=True,exist_ok=True)
roots=['/dev/shm/adsb-async-native-20261109','/run/adsb-async-native-20261109','/run/adsb-async-native-20261109-v2','/run/adsb-async-native-20261109-v3','/run/adsb-async-native-20261109-v4']
code='ROOTS='+repr(roots)+r'''
import pathlib,subprocess,json,hashlib,tarfile,io,sys
for u in ['adsb-async-native-20261109','adsb-async-native-20261109-v2','adsb-async-native-20261109-v3','adsb-async-native-20261109-v4']:
 assert subprocess.run(['systemctl','is-active','--quiet',u]).returncode!=0
m={};existing=[];b=io.BytesIO()
with tarfile.open(fileobj=b,mode='w') as t:
 for name in ROOTS:
  root=pathlib.Path(name)
  if not root.exists():continue
  assert root.is_dir() and not root.is_symlink();existing.append(dict(path=name,inode=root.stat().st_ino))
  for p in sorted(root.rglob('*')):
   st=p.lstat();row=dict(inode=st.st_ino,mtime_ns=st.st_mtime_ns,bytes=st.st_size)
   if p.is_symlink():row['link']=str(p.readlink())
   elif p.is_file():row['sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
   elif p.is_dir():continue
   else:raise RuntimeError('Unexpected active socket/file: '+str(p))
   m[str(p)]=row;t.add(p,arcname=str(p).lstrip('/'),recursive=False)
 raw=json.dumps(dict(roots=existing,files=m),indent=2).encode();i=tarfile.TarInfo('closure-manifest.json');i.size=len(raw);t.addfile(i,io.BytesIO(raw))
sys.stdout.buffer.write(b.getvalue())
'''
b=subprocess.check_output(['ssh','adsb-rpi','sudo','python3','-'],input=code.encode(),timeout=120);dest=D/'evidence.tar';assert not dest.exists();dest.write_bytes(b);dest.chmod(0o600)
with dest.open('rb') as f:os.fsync(f.fileno())
with tarfile.open(fileobj=io.BytesIO(b)) as t:
 manifest=json.load(t.extractfile('closure-manifest.json'))
 for n,row in manifest['files'].items():
  member=t.getmember(n.lstrip('/'))
  if 'link' in row:assert member.issym() and member.linkname==row['link']
  else:
   raw=t.extractfile(member).read();assert len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256']
(D/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');receipt=dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest(),verified_members=len(manifest['files']),durable=True);(D/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
for p in [D/'manifest.json',D/'receipt.json']:
 with p.open('rb') as f:os.fsync(f.fileno())
fd=os.open(D,os.O_RDONLY);os.fsync(fd);os.close(fd)
# Recheck the exact same tree/file identity and hashes after durable Mac verification.
remove='M='+repr(manifest)+r'''
import pathlib,hashlib,shutil,json,subprocess
for root in M['roots']:
 p=pathlib.Path(root['path']);assert p.is_dir() and not p.is_symlink() and p.stat().st_ino==root['inode']
 actual={str(q) for q in p.rglob('*') if not q.is_dir() or q.is_symlink()};expected={n for n in M['files'] if n.startswith(root['path']+'/')};assert actual==expected
 for n in expected:
  q=pathlib.Path(n);r=M['files'][n];st=q.lstat();assert st.st_ino==r['inode'] and st.st_mtime_ns==r['mtime_ns'] and st.st_size==r['bytes']
  if 'link' in r:assert q.is_symlink() and str(q.readlink())==r['link']
  else:assert q.is_file() and not q.is_symlink() and hashlib.sha256(q.read_bytes()).hexdigest()==r['sha256']
for root in M['roots']:shutil.rmtree(root['path'])
print(json.dumps(dict(owned_tmpfs_roots_removed=len(M['roots']),production_files_deleted=False,persistent_archives_deleted=False)))
'''
result=json.loads(subprocess.check_output(['ssh','adsb-rpi','sudo','python3','-'],input=remove,text=True,timeout=60));(D/'cleanup.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({**receipt,**result}))
