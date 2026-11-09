"""Upload isolated source/toolchain/RF; never replace receiver files."""
from pathlib import Path
import subprocess,tarfile,io,shlex,json,hashlib
H=Path(__file__).parent.resolve();C=H.parents[1];D=Path('/Users/mit/Documents/!project/adsb-neural-rescue/results/rust-stream-20261109');b=io.BytesIO();files={}
for p in H.glob('*'):
 if p.is_file():files['code/'+p.name]=p
for n in ['rustc.tar.xz','rust-std.tar.xz']:files[n]=C/'experiments/rust-coherent/.work'/n
for folder in ['source','input']:
 for p in (D/folder).rglob('*'):
  if p.is_file():files[str(p.relative_to(D))]=p
with tarfile.open(fileobj=b,mode='w') as t:
 for n,p in files.items():t.add(p,arcname=n)
(D/'upload-manifest.json').write_text(json.dumps({n:dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for n,p in files.items()},indent=2)+'\n')
code=r'''
from pathlib import Path
import tarfile,sys,shutil,hashlib,json
D=Path('/dev/shm/adsb-rust-stream-20261109');assert not D.exists();D.mkdir(mode=0o700)
with tarfile.open(fileobj=sys.stdin.buffer,mode='r|') as t:
 for m in t:
  assert m.isfile() and not m.name.startswith('/') and '..' not in Path(m.name).parts
  p=D/m.name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(t.extractfile(m).read());p.chmod(m.mode)
shutil.copy2('/home/pi/stream1090-shadow/build/stream1090',D/'stream-original');shutil.copytree('/home/pi/adsb-neural-rescue/src',D/'src')
print('Staged isolated source, exact current binary, RF and compiler archives.')
'''
print(subprocess.check_output(['ssh','adsb-rpi','sudo python3 -c '+shlex.quote(code)],input=b.getvalue(),timeout=120).decode())
