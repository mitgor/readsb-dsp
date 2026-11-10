"""Read-only compressed transfer through established SSH; exact original TAR bytes.
Safe offloader separately rechecks identity/checksum before any source deletion.
"""
import subprocess,pathlib,hashlib,json,os,gzip,time
R=pathlib.Path('/Users/mit/Documents/!project/adsb-neural-rescue');O=R/'results/daily-20261110';D=R/'data/raw/prefetch-20261110';D.mkdir(exist_ok=True)
code="""import json,hashlib\nfrom pathlib import Path\na=[]\nfor p in Path('/var/lib/adsb-far-capture').glob('capture-[0-9]*.tar'):\n if not p.is_symlink() and p.is_file():a.append({'path':str(p),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})\nprint(json.dumps(a))"""
rows=json.loads(subprocess.check_output(['ssh','-o','ConnectTimeout=8','adsb-rpi','sudo -n nice -n 19 taskset -c 3 python3 -'],input=code,text=True));receipt=[]
for r in rows:
 target=D/pathlib.Path(r['path']).name;part=target.with_suffix('.tar.part');assert not part.exists() and not target.exists()
 proc=subprocess.Popen(['ssh','-o','ConnectTimeout=8','adsb-rpi','sudo','-n','nice','-n','19','taskset','-c','3','gzip','-1','-c','--',r['path']],stdout=subprocess.PIPE)
 h=hashlib.sha256();n=0
 with gzip.GzipFile(fileobj=proc.stdout) as source,part.open('wb') as f:
  while b:=source.read(1024**2):f.write(b);h.update(b);n+=len(b)
  f.flush();os.fsync(f.fileno())
 assert proc.wait()==0 and n==r['bytes'] and h.hexdigest()==r['sha256'];part.replace(target);fd=os.open(D,os.O_RDONLY);os.fsync(fd);os.close(fd);receipt.append(dict(r,local=str(target),verified=True,source_deleted=False));print(target.name,n,flush=True)
with (O/'prefetch-receipt.json').open('w') as f:json.dump(receipt,f,indent=2);f.flush();os.fsync(f.fileno())
