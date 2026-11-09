"""Stage known released Rust ELFs and current C in owned executable tmpfs."""
from pathlib import Path
import io,tarfile,subprocess,shlex,hashlib,json
C=Path(__file__).resolve().parents[2];R=Path('/Users/mit/Documents/!project/adsb-neural-rescue');O=R/'results/rust-revalidate-20261109';O.mkdir(exist_ok=False);b=io.BytesIO()
files={
 'candidate/_coherent.so':C/'experiments/rust-live/.work/pi-release/_coherent.so',
 'candidate/_coherent_pair.so':C/'experiments/rust-live/.work/pi-release/_coherent_pair.so',
 'candidate/build.json':C/'experiments/rust-live/.work/pi-release/build.json',
 'candidate/_acquisition_rust.so':C/'experiments/rust-methods-live/.work/pi-candidate/_acquisition_rust.so',
 'acquisition-build.json':C/'experiments/rust-methods-live/.work/pi-candidate/build.json',
 'experiments/rust-live/.work/windows.bin':C/'experiments/rust-live/.work/windows.bin',
 'parity/blocks.bin':C/'experiments/rust-acquisition/.work/blocks.bin',
 'parity/iq-blocks.bin':C/'experiments/rust-acquisition/.work/iq-blocks.bin',
 'src/rescue/coherent_extended_opt.py':C/'src/rescue/coherent_extended_opt.py',
 'src/rescue/coherent_rust.rs':C/'src/rescue/coherent_rust.rs',
 'src/rescue/acquisition_rust.rs':C/'src/rescue/acquisition_rust.rs',
 'src/rescue/coherent_peaks.c':C/'src/rescue/coherent_peaks.c'}
for folder in ['rust-live','rust-acquisition','goose-coherent','rust-revalidate-20261109']:
 for p in (C/'experiments'/folder).iterdir():
  if p.is_file() and p.suffix in ['.py','.c']:files['experiments/'+folder+'/'+p.name]=p
manifest={n:hashlib.sha256(p.read_bytes()).hexdigest() for n,p in files.items()}
expected={'candidate/_coherent.so':'4b0ace9ff94b985742ee97b15c7d9472a65ceb3c6603f0d2b82acfc1e4c17cc3','candidate/_coherent_pair.so':'54ae8162e10e029ddf5303762ba5fd3d6e842dcd9c21b17f26430a0ec9055f8d','candidate/_acquisition_rust.so':'323c0f4c7723d9bfb6f37996620d04585aa9eb3daba9d2935c89f306e6686497'};assert all(manifest[k]==v for k,v in expected.items());(O/'release-inputs.json').write_text(json.dumps(manifest,indent=2)+'\n')
with tarfile.open(fileobj=b,mode='w') as t:
 for n,p in files.items():t.add(p,arcname=n)
 W=R/'data/transfer/stream-windows-20261109'
 for p in W.rglob('*'):
  if p.is_file():t.add(p,arcname='input/'+str(p.relative_to(W)))
code=r'''
from pathlib import Path
import sys,tarfile,shutil,hashlib,json
D=Path('/dev/shm/adsb-rust-revalidate-20261109');assert not D.exists();D.mkdir(mode=0o700)
# Capture current production sources/libraries/models before overlaying experimental files.
root=Path('/home/pi/adsb-neural-rescue');shutil.copytree(root/'src',D/'src');shutil.copytree(root/'models',D/'models');shutil.copytree(root/'src',D/'reference/src')
with tarfile.open(fileobj=sys.stdin.buffer,mode='r|') as t:
 for m in t:
  assert m.isfile() and not m.name.startswith('/') and '..' not in Path(m.name).parts
  p=D/m.name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(t.extractfile(m).read());p.chmod(m.mode)
for n in ['_coherent.so','_coherent_pair.so']:shutil.copy2(D/'candidate'/n,D/'src/rescue'/n)
shutil.copy2(D/'candidate/_acquisition_rust.so',D/'src/rescue/_acquisition_rust.so');shutil.copy2(root/'src/rescue/_pipeline_extended_neon.so',D/'parity/c.so');shutil.copy2(D/'candidate/_acquisition_rust.so',D/'parity/rust.so')
for n,src in [('methods.json','/etc/default/adsb-rescue.json'),('workers.json','/etc/default/adsb-rescue-workers.json')]:shutil.copy2(src,D/n)
(D/'parity/build.json').write_text(json.dumps(dict(candidate='Exact preserved rustc1.99.1 release ELF, revalidated against actual current C; no compilation or live deployment in this stage.')))
print('Staged exact known Rust release plus current copied C reference.')
'''
print(subprocess.check_output(['ssh','adsb-rpi','sudo python3 -c '+shlex.quote(code)],input=b.getvalue(),timeout=120).decode())
