"""Offline-only shared-ring candidate with worker-local cached FIR plans."""
import concurrent.futures as futures
import multiprocessing as mp
import numpy as np
from pathlib import Path
from . import ring_transport as rt
from .fir_cached import FirPlan
from .dsp import SAMPLES
from . import workers
from .streaming import TOTAL,HOP

class FirRingBackend(rt.RingBackend):
 def __init__(self,ring,role):super().__init__(ring,role);self.fir=FirPlan() if role=='producer' else None
 def iq_blocks(self,path,block_seconds=.05,block_range=None,source_first=0,total_samples=None):
  if block_seconds!=.05 or self.job is None:raise ValueError('Ring needs explicit 50 ms job')
  slot,gen=self.job;raw=self.ring.raw(slot,gen);total=total_samples or len(raw);hop=HOP
  scratch=np.empty((hop+1200)*2,np.float32) if self.role=='producer' else None
  for index,start in enumerate(range(0,total,hop)):
   if block_range is not None and not block_range[0]<=index<block_range[1]:continue
   end=min(start+hop,total);offset=start*5//3;core=end*5//3-offset;available=max(0,min(core,total*5//3-offset-SAMPLES+1));lo=max(0,start-600);hi=min(total,end+600);left=max(0,600-start);right=max(0,end+600-total);n=hi-lo
   if lo<source_first or hi>source_first+len(raw):raise ValueError('Missing FIR context')
   if self.role=='consumer':
    iq,power,score=self.ring.consume(slot,gen,index,offset,available,core+SAMPLES);self.cached_iq=iq;self.cached_power=power;self.cached_score=score
   else:
    if self.lib.rescue_fast_convert(raw[lo-source_first:hi-source_first].reshape(-1),n,left,right,scratch):raise ValueError('Conversion bounds')
    out=np.empty((core+SAMPLES)*2,np.float32);self.fir.resample_out(scratch,int(n+left+right),1000,out);iq=out.view(np.complex64);power,score=self.prepare(iq);self.ring.publish(slot,gen,index,offset,available,iq,power,score)
   yield offset,available,iq

def initialize_fir_ring(*args):
 # Isolated spawned test workers only. The parent and production modules stay frozen.
 rt.RingBackend=FirRingBackend
 rt.initialize_ring(*args)

class FirRingStreamingPool(rt.RingStreamingPool):
 def __init__(self,model,methods,runtime,selection,companion=None,**kwargs):
  super().__init__(model,methods,runtime,selection,companion,**kwargs)
  self.executor.shutdown();self.coherent_executor.shutdown();ctx=mp.get_context('spawn');cfg=selection.get('config',{})
  tuning=dict(threshold=cfg.get('coherent_threshold',.35),budget=cfg.get('coherent_budget',48),optimized_dsp=True,optimized_v3=True,share_frontend=True,sequence_model=str(Path(model).parent/'pulse-sequence.json'),sequence_enabled=cfg.get('sequence_enabled',True))
  dm=dict(methods);dm['coherent']=False
  self.executor=futures.ProcessPoolExecutor(max_workers=selection['workers'],mp_context=ctx,initializer=initialize_fir_ring,initargs=(str(model),dm,str(runtime),self.cpu_assignments,companion,'dsp',tuning,self.ring))
  self.coherent_executor=futures.ProcessPoolExecutor(max_workers=len(selection['coherent_cpus']),mp_context=ctx,initializer=initialize_fir_ring,initargs=(str(model),dm,str(runtime),self.coherent_assignments,None,'coherent',tuning,self.ring))
