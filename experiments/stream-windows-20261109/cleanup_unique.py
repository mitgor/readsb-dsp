"""Remove only closed owned tmpfs after durable complete Mac backup verification."""
from pathlib import Path
import json,subprocess,hashlib,os
D=Path('/Users/mit/Documents/!project/adsb-neural-rescue/results/stream-windows-20261109/followup-unique');receipt=json.loads((D/'target-receipt.json').read_text());archive=D/'target-evidence.tar';assert hashlib.sha256(archive.read_bytes()).hexdigest()==receipt['sha256'] and archive.stat().st_size==receipt['bytes']
manifest=json.loads((D/'target-files.json').read_text());code='MANIFEST='+repr(manifest)+r'''
from pathlib import Path
import subprocess,hashlib,shutil,json
root=Path('/dev/shm/adsb-stream-windows-20261109');assert root.is_dir() and not root.is_symlink()
for u in ['adsb-stream-windows-20261109','adsb-stream-windows-20261109-v2','adsb-stream-windows-20261109-v3']:assert subprocess.run(['systemctl','is-active','--quiet',u]).returncode!=0
actual={str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() or p.is_symlink()};assert actual==set(MANIFEST)
for name,m in MANIFEST.items():
 p=root/name;assert p.is_file() and not p.is_symlink();s=p.stat();assert s.st_ino==m['inode'] and s.st_mtime_ns==m['mtime_ns'] and s.st_size==m['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==m['sha256']
shutil.rmtree(root);print(json.dumps(dict(owned_tmpfs_removed=str(root),production_files_deleted=False,persistent_archives_deleted=False)))
'''
raw=subprocess.check_output(['ssh','adsb-rpi','sudo','nice','-n','19','taskset','-c','3','python3','-'],input=code,text=True,timeout=90);(D/'cleanup.json').write_text(raw)
with (D/'cleanup.json').open('rb') as f:os.fsync(f.fileno())
print(raw)
