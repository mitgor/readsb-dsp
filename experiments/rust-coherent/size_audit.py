"""Debug-stripped COPY sizes; does not modify timed benchmark executables."""
import argparse,hashlib,json,platform,shutil,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--work',type=Path,default=Path(__file__).resolve().parent/'.work');p.add_argument('--output',type=Path,required=True);a=p.parse_args();w=a.work.resolve();out={'platform':platform.platform(),'policy':'strip -S on copies only; raw binaries used for CPU/RSS are unchanged. Rust prebuilt standard-library debug sections can survive staticlib compilation. Debug-only file size is not resident RAM.','variants':{}}
for name in ['c-old','c-current','goose','rust','rust-libc','rust-matched']:
 original=w/(name+'-bench');copy=w/(name+'-debug-stripped');shutil.copy2(original,copy);subprocess.run(['strip','-S',str(copy)],check=True)
 out['variants'][name]={'raw_bytes':original.stat().st_size,'debug_stripped_bytes':copy.stat().st_size,'raw_sha256':hashlib.sha256(original.read_bytes()).hexdigest(),'stripped_sha256':hashlib.sha256(copy.read_bytes()).hexdigest()}
a.output.write_text(json.dumps(out,indent=2)+'\n')
