#!/usr/bin/env python3
import pathlib,subprocess,tarfile,io,json,hashlib,os
D=pathlib.Path('/Users/mit/Documents/!project/adsb-neural-rescue/results/async-native-20261109');D.mkdir(parents=True,exist_ok=True)
code=r'''
import pathlib,tarfile,io,json,hashlib,subprocess,sys
for u in ['adsb-async-native-20261109','adsb-async-native-20261109-v2','adsb-async-native-20261109-v3','adsb-async-native-20261109-v4']:assert subprocess.run(['systemctl','is-active','--quiet',u]).returncode!=0
roots=[pathlib.Path('/run/adsb-async-native-20261109'+s) for s in ['', '-v2','-v3','-v4']];stage=pathlib.Path('/dev/shm/adsb-async-native-20261109');files={}
for root in roots:
 for p in root.glob('*.json'):files[root.name+'/'+p.name]=p.read_bytes()
for p in (stage/'experiments/async-native-20261109').iterdir():
 if p.is_file():files['sources/'+p.name]=p.read_bytes()
for u in ['adsb-async-native-20261109','adsb-async-native-20261109-v2','adsb-async-native-20261109-v3','adsb-async-native-20261109-v4']:
 files['journals/'+u+'.jsonl']=subprocess.check_output(['journalctl','-u',u,'--no-pager','-o','json'])
# Numeric feeder events only: preserve the interruption without sharing credentials/server identity.
rows=[]
for line in subprocess.check_output(['journalctl','-u','fr24feed','--since','2026-11-09 18:10:00 UTC','--no-pager','-o','json'],text=True).splitlines():
 r=json.loads(line);m=r.get('MESSAGE','');kind=None
 if 'syncing stream: timeout' in m:kind='stream_timeout'
 elif '[feed][n]disconnected' in m:kind='feed_disconnected'
 elif 'connected via' in m:kind='feed_connected'
 if kind:rows.append(dict(unix=int(r['__REALTIME_TIMESTAMP'])/1000000,kind=kind))
files['feeder-events.redacted.json']=json.dumps(rows,indent=2).encode();manifest={n:dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest()) for n,b in files.items()};files['manifest.json']=json.dumps(manifest,indent=2).encode();buf=io.BytesIO()
with tarfile.open(fileobj=buf,mode='w:gz') as t:
 for n,b in files.items():i=tarfile.TarInfo(n);i.size=len(b);i.mode=0o600;t.addfile(i,io.BytesIO(b))
sys.stdout.buffer.write(buf.getvalue())
'''
b=subprocess.check_output(['ssh','adsb-rpi','sudo','python3','-'],input=code.encode());p=D/'evidence.tar.gz';assert not p.exists();p.write_bytes(b);p.chmod(0o600)
with p.open('rb') as f:os.fsync(f.fileno())
with tarfile.open(fileobj=io.BytesIO(b)) as t:
 m=json.load(t.extractfile('manifest.json'))
 for n,r in m.items():
  raw=t.extractfile(n).read();assert len(raw)==r['bytes'] and hashlib.sha256(raw).hexdigest()==r['sha256'];assert not n.startswith('/') and '..' not in pathlib.Path(n).parts
  p=D/'files'/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
  with p.open('rb') as f:os.fsync(f.fileno())
receipt=dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest(),members_verified=len(m));(D/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
for d in [D,*[p for p in D.rglob('*') if p.is_dir()]]:
 fd=os.open(d,os.O_RDONLY);os.fsync(fd);os.close(fd)
print(json.dumps(receipt))
