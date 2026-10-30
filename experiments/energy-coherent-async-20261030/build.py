import argparse,json,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--rustc',default='rustc');p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True);source=Path(__file__).with_name('dedup.rs')
flags=['--edition=2021','-C','opt-level=3']
subprocess.run([a.rustc,*flags,'--crate-type=cdylib',str(source),'-o',str(a.output/'dedup.so')],check=True)
subprocess.run([a.rustc,*flags,'--test',str(source),'-o',str(a.output/'dedup-tests')],check=True)
r=subprocess.run([str(a.output/'dedup-tests')],capture_output=True,text=True,check=True);print(r.stdout)
(a.output/'build.json').write_text(json.dumps(dict(rustc=subprocess.check_output([a.rustc,'--version','--verbose'],text=True),flags=flags,tests=r.stdout),indent=2))
