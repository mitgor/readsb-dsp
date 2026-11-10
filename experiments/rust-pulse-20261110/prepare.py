"""Historical production-policy pulse windows, capped chronologically per RF case."""
from pathlib import Path
import sys,json,hashlib,argparse
import numpy as np
H=Path(__file__).resolve().parent;C=H.parents[1];sys.path.insert(0,str(C/'src'))
from rescue.pipeline_v3 import BackendV3
p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True);W=Path('/Users/mit/Documents/!project/adsb-neural-rescue/data/transfer/stream-windows-20261109');data=json.loads((W/'dataset.private.json').read_text());b=BackendV3();rows=[];provenance=[]
for case in data['rows']:
 raw=W/'rf'/case['file'];assert hashlib.sha256(raw.read_bytes()).hexdigest()==case['sha256'];seen=0
 for offset,core,iq in b.iq_blocks(raw):
  starts,scores=b.candidate_scores(iq,core,.4);safe=(starts>=10)&(starts+490<len(iq));starts=starts[safe];scores=scores[safe];positions=starts[np.argsort(-scores,kind='stable')[:64]];power=b.prepare(iq)[0]
  for at in positions:
   if seen>=160:break
   rows.append(power[at:at+482].copy());provenance.append(dict(file=case['file'],sample_4msps=int(offset+at)));seen+=1
 print(case['file'],seen,flush=True)
x=np.stack(rows).astype(np.float32);np.save(a.out/'power.npy',x);model=C/'models/pulse-discriminant.json';(a.out/'model.json').write_bytes(model.read_bytes());(a.out/'manifest.private.json').write_text(json.dumps(dict(windows=len(x),sha256=hashlib.sha256((a.out/'power.npy').read_bytes()).hexdigest(),model_sha256=hashlib.sha256(model.read_bytes()).hexdigest(),provenance=provenance,scope='24 consumed historical RF seconds, first160 pulse candidates per RF second under unchanged threshold/top64-per-block policy. No labels.'),indent=2)+'\n')
