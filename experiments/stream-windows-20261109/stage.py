from pathlib import Path
import io,tarfile,subprocess,shlex
R=Path('/Users/mit/Documents/!project/adsb-neural-rescue');C=Path(__file__).resolve().parent;W=R/'data/transfer/stream-windows-20261109';b=io.BytesIO()
with tarfile.open(fileobj=b,mode='w') as t:
 for p in W.rglob('*'):
  if p.is_file():t.add(p,arcname='input/'+str(p.relative_to(W)))
 for p in C.glob('*.py'):t.add(p,arcname='code/'+p.name)
code=r'''
from pathlib import Path
import shutil,sys,tarfile,hashlib,json
D=Path('/dev/shm/adsb-stream-windows-20261109');assert not D.exists();D.mkdir(mode=0o700)
with tarfile.open(fileobj=sys.stdin.buffer,mode='r|') as t:
 for m in t:
  assert m.isfile() and not m.name.startswith('/') and '..' not in Path(m.name).parts
  p=D/m.name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(t.extractfile(m).read())
root=Path('/home/pi/adsb-neural-rescue');shutil.copytree(root/'src',D/'src');shutil.copytree(root/'models',D/'models');shutil.copy2('/home/pi/stream1090-shadow/build/stream1090',D/'stream1090')
for name,source in [('methods.json','/etc/default/adsb-rescue.json'),('workers.json','/etc/default/adsb-rescue-workers.json')]:shutil.copy2(source,D/name)
manifest={str(p.relative_to(D)):hashlib.sha256(p.read_bytes()).hexdigest() for folder in ['src','models'] for p in (D/folder).rglob('*') if p.is_file() and p.suffix in ['.py','.so','.onnx']};(D/'source-manifest.json').write_text(json.dumps(manifest,indent=2));print('Isolated source/model/library/RF copy staged.')
'''
print(subprocess.check_output(['ssh','adsb-rpi','sudo python3 -c '+shlex.quote(code)],input=b.getvalue(),timeout=120).decode())
