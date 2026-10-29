"""Offline learned eight-sample PPM energy discriminant; no address forcing.

Fits class means and shrinkage covariance on stock-confirmed training bits.
The waveform decision is linear, followed only by existing restricted CRC repair.
"""
import collections,json,time
import numpy as np
from .dsp import payloads,crc_batch,PREAMBLE
from .classical import soft_decode
OFFSETS=np.arange(-2,6)

def bit_features(chunks):
 power=(np.abs(np.asarray(chunks,np.complex64))**2).astype(np.float64);scale=np.maximum(power[:,8:40][:,PREAMBLE.astype(bool)].mean(1),1e-6)
 return power[:,8+32+4*np.arange(112)[:,None]+OFFSETS]/scale[:,None,None]

def fit(chunks,truth,distance,shrinkage=.5):
 x=bit_features(chunks);bits=np.unpackbits(truth,axis=1);weights=np.where(np.asarray(distance)>=180,3.,1.)
 means=[];cov=[]
 for label in (0,1):
  w=weights[:,None]*(bits==label);mass=w.sum();mean=np.einsum('nbi,nb->i',x,w)/mass
  centered=x-mean;matrix=np.einsum('nbi,nbj,nb->ij',centered,centered,w)/mass;means.append(mean);cov.append(matrix)
 pooled=(cov[0]+cov[1])/2;regular=(1-shrinkage)*pooled+shrinkage*np.diag(np.diag(pooled));regular+=np.eye(8)*max(1e-8,np.trace(pooled)*1e-5/8)
 w=np.linalg.solve(regular,means[1]-means[0]);w*=4/max(np.abs(w).sum(),1e-9);bias=-.5*np.dot(means[1]+means[0],w)
 return dict(schema='pulse-discriminant-v1',weights=w.tolist(),bias=float(bias),shrinkage=shrinkage,offsets=OFFSETS.tolist(),label_policy='stock-confirmed training split only; far windows weighted 3x',training_eligible_predictions=False)

def decisions(x,model):
 w=np.asarray(model['weights']);bias=model['bias'];logits=np.einsum('nbi,i->nb',x,w)+bias;conf=np.abs(logits)/(np.einsum('nbi,i->nb',x,np.abs(w))+abs(bias)+1e-9)
 return logits.astype(np.float32),np.clip(conf,0,1).astype(np.float32)

def packet_predictions(chunks,model):
 logits,conf=decisions(bit_features(chunks),model);rows=payloads(logits);fixed,_=soft_decode(logits,conf)
 # The native/legacy soft routine never changes ICAO or DF bits.
 for index,row,bits in fixed:rows[index]=row
 return rows

class PulseDiscriminantDecoder:
 def __init__(self,model,budget=64,native=False):
  from .pipeline_v3 import BackendV3
  self.model=model;self.budget=budget;self.native=native;self.backend=BackendV3()
 def decode(self,path):
  events=[];count=collections.Counter();begin=time.process_time()
  for offset,core,iq in self.backend.iq_blocks(path):
   starts,scores=self.backend.candidate_scores(iq,core,.4);safe=(starts>=10)&(starts+490<len(iq));starts=starts[safe];scores=scores[safe]
   if not len(starts):continue
   # Same preamble gate and bounded workload; no target-guided timing or header rewrite.
   ids=np.argsort(-scores,kind='stable')[:self.budget];positions=starts[ids]
   if self.native:
    from .pulse_native import scores as native_scores
    logits,conf=native_scores(self.backend.prepare(iq)[0],positions,self.model);pred=payloads(logits);fixed,_=self.backend.soft_decode(logits,conf)
    for index,row,bits in fixed:pred[index]=row
   else:
    windows=iq[positions[:,None]+np.arange(-8,488)];pred=packet_predictions(windows,self.model)
   valid=(crc_batch(pred)==0)&(pred[:,0]>>3==17);count['windows']+=len(pred)
   for j in np.flatnonzero(valid):events.append(dict(sample_4msps=float(offset+positions[j]),seconds=(offset+positions[j])/4e6,message_hex=pred[j].tobytes().hex(),source='matched',experiment_source='pulse_discriminant',training_eligible=False))
  return events,dict(cpu_s=time.process_time()-begin,**count)
