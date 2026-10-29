"""Frozen power blocks from already consumed development RF; no live input."""
import argparse,hashlib,json,struct,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'))
from rescue.pipeline_v3 import BackendV3
from rescue.dsp import PREAMBLE
p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();files=sorted(a.input.glob('rf-*.uc8'));chosen=[files[i] for i in np.linspace(0,len(files)-1,min(24,len(files)),dtype=int)];b=BackendV3();records=[];meta=[]
known=np.r_[PREAMBLE,np.repeat([1,0,0,1,0,1,0,1,1,0],2)].astype(np.float32);template=known-known.mean();weights=[float(template[0]),float(template[2]),float(np.dot(template,template))]
for path in chosen:
 offset,core,iq=next(b.iq_blocks(path));power=(iq.real*iq.real+iq.imag*iq.imag).astype('<f4');records.append(struct.pack('<qq',len(power),core)+power.tobytes());meta.append({'file':path.name,'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'offset_4msps':int(offset),'core':int(core),'samples':len(power)})
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(struct.pack('<Qddd',len(records),*weights)+b''.join(records));d={'blocks':len(records),'power_samples':sum(x['samples'] for x in meta),'nominal_rf_seconds':sum(x['core'] for x in meta)/4e6,'weights':weights,'files':meta,'fixture_sha256':hashlib.sha256(a.output.read_bytes()).hexdigest(),'scope':'First 50ms blocks from 24 time-spread already-consumed RF captures; no new labels or reserved RF.'};a.output.with_suffix('.json').write_text(json.dumps(d,indent=2)+'\n');print({k:v for k,v in d.items() if k!='files'})
