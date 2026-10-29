"""Offline shared-frontend pulse bank and strictly bounded coherent retries."""
import time
from collections import Counter
import numpy as np
from .dsp import crc_batch,payloads
from .pulse_native import bank_scores
from .coherent_fast import native_windows
from .coherent_pair import pair_windows

class SharedPulseRetry:
 def __init__(self,models,budget=64,retry_budget=8):
  if not 1<=budget<=256 or not 0<=retry_budget<=16:raise ValueError('Invalid offline workload budget')
  self.models=models;self.budget=budget;self.retry_budget=retry_budget
 def block(self,iq,core,backend,offset=0):
  begin=time.process_time();starts,rank,power=backend.candidate_scores(iq,core,.4,with_power=True)
  mask=(starts>=10)&(starts+490<len(iq));starts=starts[mask];rank=rank[mask]
  selected=np.argsort(-rank,kind='stable')[:self.budget];starts=starts[selected];rank=rank[selected]
  groups={'frozen_pulse':[],'pulse_bank':[],'bounded_coherent_first_fit':[],'bounded_pair_retry':[]};cost=Counter(windows=len(starts))
  def emit(name,positions,rows,valid):
   for i in np.flatnonzero(valid):
    sample=int(offset+positions[i]);groups[name].append(dict(sample_4msps=sample,seconds=sample/4e6,message_hex=rows[i].tobytes().hex(),source='matched' if name=='pulse_bank' else 'coherent',experiment_source=name,training_eligible=False))
  if not len(starts):return groups,dict(cost,cpu_s=time.process_time()-begin)
  mark=time.process_time();l,c=bank_scores(power,starts,self.models);cost['pulse_bank_cpu_s']=time.process_time()-mark
  solved=np.zeros(len(starts),bool)
  for m in range(len(self.models)):
   rows=payloads(l[:,m]);fixed,_=backend.soft_decode(l[:,m],c[:,m])
   for i,p,bits in fixed:rows[i]=p
   valid=(crc_batch(rows)==0)&(rows[:,0]>>3==17)
   if m==0:emit('frozen_pulse',starts,rows,valid)
   emit('pulse_bank',starts,rows,valid&~solved);solved|=valid
  # A known failed waveform window is required; a coherent fit is first tried
  # only on the bounded optional subset, never across all RF or all candidates.
  pending=starts[~solved][:self.retry_budget]
  mark=time.process_time()
  if len(pending):
   original=native_windows(iq,pending);emit('bounded_coherent_first_fit',pending,original[5],original[-1]);failed=~original[-1];retry=pair_windows(iq,pending[failed]);emit('bounded_pair_retry',pending[failed],retry[5],retry[-1]);cost['pair_retry_windows']=int(failed.sum());cost['bounded_coherent_windows']=len(pending)
  cost['bounded_retry_cpu_s']=time.process_time()-mark
  return groups,dict(cost,cpu_s=time.process_time()-begin)
