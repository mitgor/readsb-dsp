"""Frozen EM inputs from previously consumed shared-feedback development RF."""
import argparse,hashlib,json,struct,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'))
from rescue.pipeline_v3 import BackendV3
from rescue.native import header_ids,energy_candidates
from rescue.coherent_fast import native_windows
p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();b=BackendV3();windows=[];files=[]
for path in sorted(a.input.glob('rf-*.uc8'))[:42]:
 used=[]
 for offset,core,iq in b.iq_blocks(path):
  starts,_=b.coherent_scores(iq,core,.35);starts=starts[(starts>=8)&(starts+488<len(iq))];starts=starts[header_ids(iq,starts)];_,valid=energy_candidates(iq,starts);starts=starts[~valid]
  for at in starts[:8-len(used)]:windows.append(iq[at-8:at+488].copy());used.append(int(offset+at))
  if len(used)==8:break
 files.append({'name':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'starts_4msps':used})
rng=np.random.default_rng(20261029)
for i in range(32):windows.append((rng.normal(0,.01,496)+1j*rng.normal(0,.01,496)).astype(np.complex64))
x=np.stack(windows).astype('<c8');starts=np.arange(len(x),dtype=np.int64)*496+8;l,c,tracked,f,*_=native_windows(x.reshape(-1),starts);f=np.asarray(f,dtype='<f8');f[::4]=np.nan
arrays=[x,f,l.astype('<f8'),c.astype('<f8')];a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(struct.pack('<Q',len(x))+b''.join(x.tobytes() for x in arrays));manifest={'windows':len(x),'files':files,'rf_files':len(files),'noise_controls':32,'finite_seeds':int(np.isfinite(f).sum()),'fixture_sha256':hashlib.sha256(a.output.read_bytes()).hexdigest(),'scope':'Already consumed RF; first 8 hard-header, failed-energy windows per file, shared frozen initial logits/confidence/carrier seeds, no training labels.'};a.output.with_suffix('.json').write_text(json.dumps(manifest,indent=2)+'\n');print({k:v for k,v in manifest.items() if k!='files'})
