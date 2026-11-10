"""Checksum-backed private evidence copy; reuse identical already-durable Mac inputs."""
import argparse,subprocess,json,hashlib,tarfile,io,os,shutil
from pathlib import Path

def main():
 p=argparse.ArgumentParser();p.add_argument('--dest',type=Path,required=True);p.add_argument('--reuse',type=Path,required=True);a=p.parse_args();assert not a.dest.exists();a.dest.mkdir();E=a.dest/'files';E.mkdir()
 script="""import json,hashlib
from pathlib import Path
r=Path('/dev/shm/adsb-stream-latency-activation-20261110');out={}
for x in r.rglob('*'):
 if x.is_symlink():raise RuntimeError('Unexpected link')
 if x.is_file():out[str(x.relative_to(r))]={'bytes':x.stat().st_size,'sha256':hashlib.sha256(x.read_bytes()).hexdigest()}
print(json.dumps(out))"""
 manifest=json.loads(subprocess.check_output(['ssh','-o','BatchMode=yes','adsb-rpi','sudo -n python3 -'],input=script.encode()));(a.dest/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');missing=[]
 for name,m in manifest.items():
  assert not Path(name).is_absolute() and '..' not in Path(name).parts
  x=a.reuse/name
  if x.is_file() and not x.is_symlink() and x.stat().st_size==m['bytes'] and hashlib.sha256(x.read_bytes()).hexdigest()==m['sha256']:
   target=E/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(x,target)
  else:missing.append(name)
 raw=subprocess.check_output(['ssh','-o','BatchMode=yes','adsb-rpi','sudo -n tar -C /dev/shm/adsb-stream-latency-activation-20261110 -czf - --null -T -'],input=b''.join(x.encode()+b'\0' for x in missing));(a.dest/'delta.tar.gz').write_bytes(raw)
 with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as f:
  assert all(not m.issym() and not m.islnk() for m in f.getmembers());f.extractall(E,filter='data')
 for name,m in manifest.items():
  x=E/name;assert x.stat().st_size==m['bytes'] and hashlib.sha256(x.read_bytes()).hexdigest()==m['sha256'],name
  with x.open('rb') as f:os.fsync(f.fileno())
 archive=a.dest/'evidence.tar.gz'
 with tarfile.open(archive,'w:gz',compresslevel=1) as f:f.add(E,arcname='evidence')
 with archive.open('rb') as f:os.fsync(f.fileno())
 receipt=dict(files=len(manifest),downloaded_files=len(missing),all_hashes_verified=True,fsynced=True,archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),archive_bytes=archive.stat().st_size);(a.dest/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
 for x in [a.dest/'manifest.json',a.dest/'receipt.json']:
  with x.open('rb') as f:os.fsync(f.fileno())
 for x in [p for p in E.rglob('*') if p.is_dir()]+[E,a.dest,a.dest.parent]:
  fd=os.open(x,os.O_RDONLY);os.fsync(fd);os.close(fd)
 print(json.dumps(receipt),flush=True)
if __name__=='__main__':main()
