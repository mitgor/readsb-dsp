"""Verify closed target result/source bundle on Mac; preserve failed launch logs."""
from pathlib import Path
import subprocess,tarfile,io,json,hashlib,os
R=Path('/Users/mit/Documents/!project/adsb-neural-rescue');D=R/'results/stream-windows-20261109/followup-unique';D.mkdir(exist_ok=False);dest=D/'target-evidence.tar';assert not dest.exists()
code=r'''
from pathlib import Path
import subprocess,json,tarfile,io,hashlib,sys
for u in ['adsb-stream-windows-20261109','adsb-stream-windows-20261109-v2','adsb-stream-windows-20261109-v3']:assert subprocess.run(['systemctl','is-active','--quiet',u]).returncode!=0
D=Path('/dev/shm/adsb-stream-windows-20261109');assert json.loads((D/'protected.private.json').read_text())['error'] is None
b=io.BytesIO();manifest={}
with tarfile.open(fileobj=b,mode='w') as t:
 for p in sorted(D.rglob('*')):
  if not p.is_file():continue
  assert not p.is_symlink();raw=p.read_bytes();name=str(p.relative_to(D));i=tarfile.TarInfo(name);i.size=len(raw);t.addfile(i,io.BytesIO(raw));manifest[name]=dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),inode=p.stat().st_ino,mtime_ns=p.stat().st_mtime_ns)
 raw=json.dumps(manifest).encode();i=tarfile.TarInfo('transfer-manifest.json');i.size=len(raw);t.addfile(i,io.BytesIO(raw))
sys.stdout.buffer.write(b.getvalue())
'''
raw=subprocess.check_output(['ssh','adsb-rpi','sudo','python3','-'],input=code.encode(),timeout=120);dest.write_bytes(raw);dest.chmod(0o600)
with dest.open('rb') as f:os.fsync(f.fileno())
with tarfile.open(fileobj=io.BytesIO(raw)) as t:
 manifest=json.load(t.extractfile('transfer-manifest.json'))
 for n,m in manifest.items():
  data=t.extractfile(n).read();assert len(data)==m['bytes'] and hashlib.sha256(data).hexdigest()==m['sha256']
  if n.endswith('.json') and '/' not in n:(D/n).write_bytes(data)
  if n.endswith('.log') and '/' not in n:(D/n).write_bytes(data)
receipt=dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),members=len(manifest),durable=True);(D/'target-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');(D/'target-files.json').write_text(json.dumps(manifest)+'\n')
for p in D.iterdir():
 if p.is_file():
  with p.open('rb') as f:os.fsync(f.fileno())
fd=os.open(D,os.O_RDONLY);os.fsync(fd);os.close(fd)
print(json.dumps(receipt))
