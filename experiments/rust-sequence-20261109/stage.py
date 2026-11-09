"""Stage frozen inputs and current production copies in an owned tmpfs root."""
from pathlib import Path
import io,tarfile,subprocess,shlex,json,hashlib
H=Path(__file__).resolve().parent;C=H.parents[1];R=Path('/Users/mit/Documents/!project/adsb-neural-rescue');O=R/'results/rust-sequence-20261109';files={}
for p in H.glob('*'):
 if p.is_file():files['experiments/rust-sequence-20261109/'+p.name]=p
for p in (C/'src/rescue').iterdir():
 if p.suffix in ['.c','.h','.rs']:files['src/rescue/'+p.name]=p
for n in ['rustc.tar.xz','rust-std.tar.xz']:files[n]=C/'experiments/rust-coherent/.work'/n
for p in (O/'input-spread').glob('*'):
 if p.is_file():files['input/'+p.name]=p
for p in (R/'data/transfer/stream-windows-20261109').rglob('*'):
 if p.is_file():files['rf-input/'+str(p.relative_to(R/'data/transfer/stream-windows-20261109'))]=p
files['experiments/rust-sequence-20261109/full_replay.py']=C/'experiments/rust-revalidate-20261109/full_replay.py'
b=io.BytesIO()
with tarfile.open(fileobj=b,mode='w') as t:
 for n,p in files.items():t.add(p,arcname=n)
(O/'upload-manifest.json').write_text(json.dumps({n:dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for n,p in files.items()},indent=2)+'\n')
code=r'''
from pathlib import Path
import sys,tarfile,shutil,json
D=Path('/dev/shm/adsb-rust-sequence-20261109');assert not D.exists();D.mkdir(mode=0o700)
root=Path('/home/pi/adsb-neural-rescue');shutil.copytree(root/'src',D/'reference/src');shutil.copytree(root/'models',D/'models');shutil.copytree(root/'src',D/'candidate/src')
with tarfile.open(fileobj=sys.stdin.buffer,mode='r|') as t:
 for m in t:
  assert m.isfile() and not m.name.startswith('/') and '..' not in Path(m.name).parts
  p=D/m.name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(t.extractfile(m).read());p.chmod(m.mode)
for n,p in [('methods.json','/etc/default/adsb-rescue.json'),('workers.json','/etc/default/adsb-rescue-workers.json')]:shutil.copy2(p,D/n)
print('Staged copies only; no live producer access or writes.')
'''
print(subprocess.check_output(['ssh','adsb-rpi','sudo python3 -c '+shlex.quote(code)],input=b.getvalue(),timeout=120).decode())
