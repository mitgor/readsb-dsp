#!/usr/bin/env python3
import pathlib,json,subprocess,tarfile,io,base64
R=pathlib.Path(__file__).resolve().parents[2];P=pathlib.Path('/Users/mit/Documents/!project/adsb-neural-rescue');raw=P/'data/raw/async-producers-20261109/files';bundle=io.BytesIO()
with tarfile.open(fileobj=bundle,mode='w') as t:
 for p in raw.rglob('*'):
  if p.is_file():
   rel=p.relative_to(raw)
   if rel.parts[0]=='runtime':name=str(rel.relative_to('runtime'))
   elif rel.parts[0]=='capture-v3':name='capture/'+str(rel.relative_to('capture-v3'))
   else:continue
   t.add(p,arcname=name)
 for folder in ['async-native-20261109','async-relay-20261030','latency-publication-20261030','completion-bridge-20261030']:
  for p in (R/'experiments'/folder).glob('*.py'):t.add(p,arcname='experiments/'+folder+'/'+p.name)
 timing=P/'results/async-producers-20261109/mac-runtime/timing.json';t.add(timing,arcname='timing.json')
# Upload as a stream into an owned root executable-tmpfs tree. No permission/network policy changes.
code=r'''
import pathlib,sys,tarfile,os
stage=pathlib.Path('/dev/shm/adsb-async-native-20261109');assert not stage.exists();stage.mkdir()
with tarfile.open(fileobj=sys.stdin.buffer,mode='r|') as t:
 for m in t:
  assert m.isfile() and not m.name.startswith('/') and '..' not in pathlib.Path(m.name).parts
  p=stage/m.name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(t.extractfile(m).read());p.chmod(0o755 if p.name=='stream1090' else 0o644)
print(stage)
'''
# Separate interpreter argument and tar stdin, avoiding code/data mixing.
import shlex
cmd='sudo python3 -c '+shlex.quote(code)
print(subprocess.check_output(['ssh','adsb-rpi',cmd],input=bundle.getvalue(),timeout=120).decode())
