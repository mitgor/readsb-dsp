"""Chronological historical candidates with full sequence halos; never live RF."""
from pathlib import Path
import sys,json,hashlib,argparse
import numpy as np
H=Path(__file__).resolve().parent;C=H.parents[1];sys.path.insert(0,str(C/'src'))
from rescue.pipeline_v3 import BackendV3,SequenceV3
p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
R=Path('/Users/mit/Documents/!project/adsb-neural-rescue');W=R/'data/transfer/stream-windows-20261109';dataset=json.loads((W/'dataset.private.json').read_text());model=json.loads((C/'models/pulse-sequence.json').read_text());h=np.array(model['h_real'])+1j*np.array(model['h_imag']);backend=BackendV3();engine=SequenceV3(h,backend,.35,48);engine.coherent_enabled=True;engine.sequence_enabled=True;engine.acquisition_enabled=True;engine.pair_retry=True
windows=[];seeds=[];provenance=[];case_seen={};original=engine.sequence.decode;context={}
def capture(iq,starts,frequency):
 for at,f in zip(starts,frequency):
  if case_seen.get(context['file'],0)>=160:continue
  case_seen[context['file']]=case_seen.get(context['file'],0)+1
  windows.append(iq[at-8:at+488].copy());seeds.append(f);provenance.append(dict(file=context['file'],sample_4msps=int(context['offset']+at)))
 return original(iq,starts,frequency)
engine.sequence.decode=capture
for case in dataset['rows']:
 path=W/'rf'/case['file'];assert hashlib.sha256(path.read_bytes()).hexdigest()==case['sha256'];context['file']=case['file']
 for offset,core,iq in backend.iq_blocks(path):
  context['offset']=offset;engine.decode(path,blocks=iter([(offset,core,iq)]),raw_events=True)
 print(case['file'],len(windows),flush=True)
 # Broad chronological coverage without selecting based on decoding success.
 # Continue through every frozen RF second for chronological diversity.
x=np.stack(windows[:4096]).astype(np.complex64);s=np.array(seeds[:4096],np.float64);np.savez(a.out/'windows.npz',iq=x,seeds=s,h=h)
(a.out/'manifest.private.json').write_text(json.dumps(dict(windows=len(x),seed_nan=int(np.isnan(s).sum()),fixture_sha256=hashlib.sha256((a.out/'windows.npz').read_bytes()).hexdigest(),model=model,provenance=provenance[:len(x)],scope='Historical previously consumed evaluation windows; chronological selected production-like sequence candidate calls. No training labels.'),indent=2)+'\n')
