"""Read-only bounded HTTP downloads through existing CRC archive export."""
from pathlib import Path
import subprocess,json,hashlib,os,urllib.request,concurrent.futures
R=Path('/Users/mit/Documents/!project/adsb-neural-rescue');O=R/'results/daily-20261110';D=R/'data/raw/prefetch-20261110';D.mkdir(exist_ok=True)
code="""from pathlib import Path;import json,hashlib\na=[]\nfor p in Path('/var/lib/adsb-rescue/crc-verification').glob('batch-[0-9]*.jsonl.gz'):\n if not p.is_symlink() and p.is_file():a.append({'path':str(p),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})\nprint(json.dumps(a))"""
rows=json.loads(subprocess.check_output(['ssh','-o','ConnectTimeout=8','adsb-rpi','sudo -n nice -n 19 taskset -c 3 python3 -'],input=code,text=True))
def get(r):
 name=Path(r['path']).name;dest=D/name;part=D/(name+'.part');assert not dest.exists() and not part.exists();h=hashlib.sha256();n=0
 with urllib.request.urlopen('http://192.168.2.195/neural-rescue/archives/crc-verification/'+name,timeout=60) as source,part.open('wb') as f:
  while b:=source.read(65536):f.write(b);h.update(b);n+=len(b)
  f.flush();os.fsync(f.fileno())
 assert n==r['bytes'] and h.hexdigest()==r['sha256'];part.rename(dest);fd=os.open(D,os.O_RDONLY);os.fsync(fd);os.close(fd);print(name,n,flush=True);return dict(r,local=str(dest),verified=True,source_deleted=False)
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:receipt=list(pool.map(get,rows))
with (O/'prefetch-crc-receipt.json').open('w') as f:json.dump(receipt,f,indent=2);f.flush();os.fsync(f.fileno())
