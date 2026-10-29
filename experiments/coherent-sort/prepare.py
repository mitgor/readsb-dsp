"""Chronological development windows spread across previously consumed RF files."""
import argparse,hashlib,json,struct,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'))
from rescue.pipeline_v3 import BackendV3
from rescue.native import header_ids
p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
b=BackendV3();windows=[];files=[]
for path in sorted(a.input.glob('rf-*.uc8'))[:42]:
 used=[]
 for offset,core,iq in b.iq_blocks(path):
  starts,_=b.coherent_scores(iq,core,.35);starts=starts[(starts>=8)&(starts+488<len(iq))];starts=starts[header_ids(iq,starts)]
  for at in starts[:96-len(used)]:windows.append(iq[at:at+480].copy());used.append(int(offset+at))
  if len(used)==96:break
 files.append({'name':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'starts_4msps':used})
rng=np.random.default_rng(20261029)
for _ in range(32):windows.append((rng.normal(0,.01,480)+1j*rng.normal(0,.01,480)).astype(np.complex64))
x=np.stack(windows).astype('<c8');a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(struct.pack('<Q',len(x))+x.tobytes())
m={'windows':len(x),'rf_files':len(files),'noise_controls':32,'fixture_sha256':hashlib.sha256(a.output.read_bytes()).hexdigest(),'files':files,'scope':'Development regression only; existing consumed RF, first 96 eligible candidates per file, not unique transmissions.'}
a.output.with_suffix('.json').write_text(json.dumps(m,indent=2)+'\n');print({k:v for k,v in m.items() if k!='files'})
