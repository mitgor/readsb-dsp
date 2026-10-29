"""Extract already-consumed coherent windows; never reads the live receiver."""
import argparse,hashlib,json,struct,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'))
from rescue.pipeline_v3 import BackendV3
from rescue.native import header_ids,energy_candidates
p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--limit',type=int,default=1024);a=p.parse_args()
backend=BackendV3();windows=[];provenance=[];counts={'energy_valid_control':0,'failed_energy':0,'noise_control':0}
for path in sorted(a.input.glob('rf-*.uc8')):
 used=[]
 for offset,core,iq in backend.iq_blocks(path):
  starts,_=backend.coherent_scores(iq,core,.35);starts=starts[(starts>=8)&(starts+488<len(iq))];starts=starts[header_ids(iq,starts)]
  _,valid=energy_candidates(iq,starts)
  for i,s in enumerate(starts):
   if valid[i] and counts['energy_valid_control']>=a.limit//4:continue
   windows.append(iq[s:s+480].copy());counts['energy_valid_control' if valid[i] else 'failed_energy']+=1;used.append(int(offset+s))
   if len(windows)>=a.limit:break
  if len(windows)>=a.limit:break
 if used:provenance.append(dict(file=path.name,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),starts_4msps=used))
 if len(windows)>=a.limit:break
rng=np.random.default_rng(20261029)
for i in range(32):windows.append((rng.normal(0,.01,480)+1j*rng.normal(0,.01,480)).astype(np.complex64));counts['noise_control']+=1
x=np.stack(windows).astype('<c8');a.output.parent.mkdir(exist_ok=True,parents=True);a.output.write_bytes(struct.pack('<Q',len(x))+x.tobytes())
manifest=dict(windows=len(x),counts=counts,fixture_sha256=hashlib.sha256(a.output.read_bytes()).hexdigest(),scope='Already consumed shared-feedback RF; first chronological eligible windows, no language-performance-based selection. Plus 32 seeded noise controls. No training labels.',files=provenance)
a.output.with_suffix('.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps({k:v for k,v in manifest.items() if k!='files'},indent=2))
