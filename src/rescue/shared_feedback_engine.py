"""Isolated serial replay of frozen live methods plus opt-in five-step proposals.

No sockets, hardware, feeder, service/configuration or persistent RF writes.
Cross-worker catalog transport is not deployed by this replay prototype.
"""
import collections,time
from pathlib import Path
from unittest.mock import patch
import numpy as np
import onnxruntime as ort
from . import native,sequence_live
from .runtime import RescueDecoder
from .pipeline_v3 import enable_v3
from .sequence_live import SequenceAcquisitionDecoder
from .model_cascade import CascadeSession
from .dsp import features,baseline,payloads,crc_batch,PREAMBLE,FS
from .candidate_context import CandidateContext
from .feedback_experiment import soft_feedback,guarded_cancel
from .coherent_fast import native_windows

class DeferredSession:
 def __init__(self,session,context,starts,rank,budget):self.real=session;self.context=context;self.starts=starts;self.rank=rank;self.budget=budget;self.waiting=[]
 def run(self,names,inputs):
  ids=self.context.header_ids(self.context.iq,self.starts);pos=self.starts[ids]
  x=features(self.context.iq[pos[:,None]+np.arange(480)]);rows=payloads(baseline(x));valid=(crc_batch(rows)==0)&(rows[:,0]>>3==17)
  pending=[(int(ids[j]),float(self.rank[ids[j]]),j) for j in np.flatnonzero(~valid)]
  chosen=sorted(sorted(pending,key=lambda r:(-r[1],r[0]))[:self.budget]);positions=self.starts[[r[0] for r in chosen]]
  assert np.array_equal(x[[r[2] for r in chosen]],inputs['iq_features']),'Neural candidate mapping changed'
  self.waiting.append((positions,inputs['iq_features'].copy()))
  return [np.full((len(positions),112),-1,np.float32)]

def valid_rows(logits):
 rows=payloads(logits);return rows,(crc_batch(rows)==0)&(rows[:,0]>>3==17)
def event(sample,row,source):return dict(sample_4msps=float(sample),seconds=float(sample)/FS,message_hex=row.tobytes().hex(),source=source,training_eligible=False)
def same_window(sample,events):return any(abs(sample-r['sample_4msps'])<=1 for r in events if r['source']!='broad_crc')

class ExperimentEngine:
 def __init__(self,root,stage):
  if stage not in range(6):raise ValueError('Invalid experiment stage')
  self.stage=stage;root=Path(root);self.decoder=d=RescueDecoder(root/'models/tiny-fp32.onnx',frontend='native',neural=True,broad_crc=True,methods=('timing','soft','matched'));enable_v3(d);self.backend=d.optimized_backend
  from .candidate_native import CandidateWorkspace
  self.workspace=CandidateWorkspace()
  opt=ort.SessionOptions();opt.intra_op_num_threads=1;opt.inter_op_num_threads=1
  paths=['models/tiny-fp32.onnx','models/candidates/dsp-20261025/tiny-rf-v1.onnx','models/candidates/improvement-raw-20261027/tiny-rf-v1.onnx'];self.session=CascadeSession([ort.InferenceSession(str(root/p),opt,providers=['CPUExecutionProvider']) for p in paths]);d.session=self.session
  # Sequence/acquisition remain off, matching the captured live config. Their
  # disabled selector is not a source of claimed CPU savings.
  import json
  h=json.loads((root/'models/pulse-sequence.json').read_text());coherent=SequenceAcquisitionDecoder(np.array(h['h_real'])+1j*np.array(h['h_imag']),self.backend,.35,48);coherent.sequence_enabled=False;coherent.acquisition_enabled=False;coherent.pair_retry=True;d.coherent=coherent
 def block(self,offset,core,iq,references):
  d=self.decoder;b=self.backend;stage=self.stage;cost=collections.Counter();work=collections.Counter();begin=time.process_time()
  ctx=CandidateContext(iq,offset,native_fused=stage>=2);d.blocks=lambda *a,**kw:iter([(offset,core,iq)])
  if stage>=2:ctx.workspace=self.workspace
  d.header_ids=ctx.header_ids if stage else native.header_ids;d.session=self.session
  if stage==3:
   starts,rank=b.candidate_scores(iq,core,.4);proxy=DeferredSession(self.session,ctx,starts,rank,d.budget);d.session=proxy
  if stage:
   with patch.object(sequence_live,'header_ids',ctx.header_ids),patch.object(sequence_live,'energy_candidates',ctx.energy_candidates):rows,detail=d.decode(None,raw_events=True)
  else:rows,detail=d.decode(None,raw_events=True)
  if stage==3:
   mark=time.process_time()
   for positions,x in proxy.waiting:
    keep=np.array([not same_window(offset+int(s),rows) for s in positions],bool);work['neural_requested']+=len(x);work['neural_skipped']+=int((~keep).sum());logits=self.session.run(None,{'iq_features':x[keep]})[0] if keep.any() else np.empty((0,112),np.float32);pred,valid=valid_rows(logits)
    for j in np.flatnonzero(valid):rows.append(event(offset+positions[keep][j],pred[j],'neural'))
   cost['deferred_inference_s']+=time.process_time()-mark
  cost['frozen_and_cache_s']+=time.process_time()-begin;work.update(ctx.count)
  # Stage 4/5 append to the fixed Stage 2 baseline, not to the potentially lossy
  # inference scheduler. Original detections always remain present.
  if stage==4:
   mark=time.process_time();normal,_=b.coherent_scores(iq,core,.35);normal=normal[(normal>=8)&(normal+488<len(iq))];normal=normal[ctx.header_ids(iq,normal)];_,valid=ctx.energy_candidates(iq,normal);pending=normal[~valid]
   if len(pending):
    p=abs(iq[pending[:,None]+np.arange(32)])**2;rank=p[:,PREAMBLE.astype(bool)].mean(1)/(p[:,~PREAMBLE.astype(bool)].mean(1)+1e-8);pending=pending[np.argsort(-rank,kind='stable')];pending=np.array([s for s in pending if not same_window(offset+int(s),rows)],np.int64)[:8]
   logits,confidence,freq=soft_feedback(iq,pending);fixed,_=b.soft_decode(logits,confidence)
   pred=payloads(logits)
   for j,p,flips in fixed:pred[j]=p
   valid=(crc_batch(pred)==0)&(pred[:,0]>>3==17)
   for j in np.flatnonzero(valid):rows.append(dict(event(offset+pending[j],pred[j],'coherent'),experiment='soft_feedback',iterations=2))
   work['feedback_windows']+=len(pending);cost['feedback_s']+=time.process_time()-mark
  if stage==5:
   mark=time.process_time();refs=[]
   for r in references:
    s=round(r['sample_4msps']-offset)
    if 480<=s<core-960 and len(r['message_hex'])==28 and int(r['message_hex'][:2],16)>>3==17:
     refs.append((float(np.mean(abs(iq[s:s+480])**2)),s,r['message_hex']))
   for power,s,payload in sorted(refs,reverse=True)[:2]:
    work['sic_attempts']+=1;lo=s-480;hi=s+960;original=iq[lo:hi].copy();residual,fit=guarded_cancel(original,480,payload);work['sic_'+fit['reason']]+=1
    if residual is None:continue
    before=self.residual(original);after=self.residual(residual);work['sic_raw_outputs']+=len(after)
    for pos,p in after:
     if p.tobytes().hex()==payload or any(p.tobytes()==q.tobytes() and abs(pos-t)<=480 for t,q in before):continue
     rows.append(dict(event(offset+lo+pos,p,'sic'),experiment='heldout_reference_sic',fit=fit))
   cost['sic_s']+=time.process_time()-mark
  return rows,dict(cpu_s=time.process_time()-begin,cost=dict(cost),work=dict(work))
 def residual(self,iq):
  # Identical decode work on original and residual prevents attributing extra
  # computation itself to cancellation. Never changes the baseline RF block.
  b=self.backend;starts,score=b.candidate_scores(iq,len(iq)-480,.4);starts=starts[(starts>=8)&(starts+488<len(iq))];starts=starts[native.header_ids(iq,starts)]
  rows,valid=native.energy_candidates(iq,starts);out=[(int(starts[j]),rows[j]) for j in np.flatnonzero(valid)];pending=starts[~valid][:8]
  if len(pending):
   r=native_windows(iq,pending)
   out.extend((int(pending[j]),r[5][j]) for j in np.flatnonzero(r[-1]))
  return out
