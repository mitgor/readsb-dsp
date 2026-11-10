"""Freeze current non-Stream methods on the same recent RF, for swap attribution."""
from pathlib import Path
import json,sys,hashlib
R=Path('/Users/mit/Documents/!project/adsb-neural-rescue');O=R/'results/stream-phase-pi-20261110';W=R/'data/transfer/stream-phase-pi-20261110';P=W/'prepared';runtime=R/'data/transfer/retrain-20261110/benchmark-runtime';sys.path.insert(0,str(runtime/'src'))
from rescue.runtime import RescueDecoder
from rescue.pipeline_v3 import enable_v3
from rescue.fir_cached import FirBackend
from rescue.coherent_extended_opt import ExtendedNeonBackend
from rescue.model_cascade import cascade_decoder,production_paths
from rescue.workers import CoherentWorker
s=json.loads((O/'receiver-before.private.json').read_text());prior=json.loads((R/'results/retrain-20261110/receiver-before.private.json').read_text());assert s['methods']==prior['methods'] and s['workers']==prior['workers'] and s['model_sha256']==prior['model_sha256'];assert not any(s['methods'][k] for k in ['pulse','sequence','acquisition','header','sic']);cfg=s['workers'];d=cascade_decoder(production_paths(R),frontend='native',broad_crc=s['methods']['crc'],neural=True,methods=('timing','soft','matched'));enable_v3(d);b=FirBackend();d.blocks=b.iq_blocks;d.scores=b.candidate_scores;d.dsp_candidates=b.dsp_candidates;d.soft_decode=b.soft_decode;d.optimized_backend=b
coh=CoherentWorker(cfg['coherent_threshold'],cfg['coherent_budget'],True,False,str(R/'models/pulse-sequence.json'),True,True,True)
class Extended(FirBackend,ExtendedNeonBackend):pass
b=Extended();coh.backend=b;coh.decoder.backend=b;coh.decoder.score_function=b.coherent_scores;coh.decoder.coherent_enabled=True;coh.decoder.sequence_enabled=False;coh.decoder.acquisition_enabled=False
cases=[c for c in json.loads((P/'cases.json').read_text()) if c['family']=='recent'];original=R/'data/transfer/retrain-20261110/prepared';out={}
for c in cases:
 path=original/c['original_case'];assert hashlib.sha256(path.read_bytes()).hexdigest()==c['sha256'];rr=[]
 for decoder in [d,coh]:
  events,stats=decoder.decode(path,raw_events=True)
  for e in events:
   if e['source']=='broad_crc':continue
   tick=c['first_sample']*5+round(e['sample_4msps']*3)
   if c['core_start']*5<=tick<c['core_end']*5:rr.append({'ticks':tick+2398,'message_hex':e['message_hex'],'source':e['source']})
 out.setdefault(c['refgroup'],[]).extend(rr)
(P/'other-dsp.json').write_text(json.dumps(out,separators=(',',':')));(O/'other-dsp-audit.json').write_text(json.dumps({'methods':s['methods'],'workers':cfg,'rows':{k:len(v) for k,v in out.items()},'policy':'Frozen current non-Stream replay. Same math/libraries already Mac/Pi parity-validated during retraining; stock/full executable/current actual output are independent masks.'},indent=2));print(sum(map(len,out.values())))
