"""Isolated bounded RF/frontend ring, with generation-checked job ownership.

No receiver, feeder, production configuration or archive I/O. Coordinator owns
leases until every task finishes; worker Event publication replaces file polling.
"""
import concurrent.futures as futures
import multiprocessing as mp
import os,struct,time
from pathlib import Path
import numpy as np
from .streaming import StreamingPool,TOTAL,HOP
from .pipeline_v3 import BackendV3
from .dsp import FIR,SAMPLES
from . import native,workers

MAX_IQ=200000+SAMPLES
BLOCK_BYTES=((64+MAX_IQ*12+(MAX_IQ-31)*8+63)//64)*64
RAW_BYTES=((2*(3*HOP+1200)+63)//64)*64

class FrontendRing:
 def __init__(self,slots=4,context=None):
  if not 1<=slots<=8:raise ValueError('Ring slots outside bounded range')
  ctx=context or mp.get_context('spawn');self.slots=slots;self.slot_bytes=RAW_BYTES+3*BLOCK_BYTES
  self.data=ctx.RawArray('B',slots*self.slot_bytes);self.meta=ctx.RawArray('q',slots*5)
  self.lock=ctx.Lock();self.ready=[ctx.Event() for _ in range(slots*3)]
 def acquire(self,raw,lo,hi):
  if len(raw)%2 or len(raw)>RAW_BYTES or not 0<=lo<hi<=21 or hi-lo>3:raise ValueError('Invalid ring batch')
  with self.lock:
   for slot in range(self.slots):
    k=slot*5
    if self.meta[k+1]:continue
    if self.meta[k]>=2**63-1:raise OverflowError('Generation exhausted')
    gen=self.meta[k]+1;self.meta[k]=gen;self.meta[k+1]=1;self.meta[k+2]=len(raw);self.meta[k+3]=lo;self.meta[k+4]=hi
    for i in range(3):self.ready[3*slot+i].clear()
    np.frombuffer(self.data,np.uint8,count=len(raw),offset=slot*self.slot_bytes)[:]=np.frombuffer(raw,np.uint8)
    return slot,gen
  raise RuntimeError('Bounded ring full')
 def verify(self,slot,gen,index=None):
  if not 0<=slot<self.slots:raise ValueError('Invalid slot')
  k=slot*5
  if self.meta[k]!=gen or not self.meta[k+1]:raise RuntimeError('Stale or released ring lease')
  if index is not None and not self.meta[k+3]<=index<self.meta[k+4]:raise ValueError('Block outside leased batch')
 def release(self,slot,gen):
  with self.lock:self.verify(slot,gen);self.meta[slot*5+1]=0
 def raw(self,slot,gen):
  with self.lock:self.verify(slot,gen);n=self.meta[slot*5+2]
  view=np.frombuffer(self.data,np.uint8,count=n,offset=slot*self.slot_bytes).reshape(-1,2);view.flags.writeable=False;return view
 def block_offset(self,slot,index):return slot*self.slot_bytes+RAW_BYTES+(index-self.meta[slot*5+3])*BLOCK_BYTES
 def publish(self,slot,gen,index,offset,core,iq,power,score):
  with self.lock:self.verify(slot,gen,index);pos=self.block_offset(slot,index);event=self.ready[3*slot+index-self.meta[slot*5+3]]
  n=len(iq)
  if n>MAX_IQ or len(power)!=n or len(score)!=n-31:raise ValueError('Frontend shape exceeds slot')
  np.frombuffer(self.data,np.uint8,count=24,offset=pos)[:]=np.frombuffer(struct.pack('<qqq',offset,core,n),np.uint8)
  for arr,dtype,count,at in ((iq,np.complex64,n,64),(power,np.float32,n,64+8*n),(score,np.float64,n-31,64+12*n)):
   np.frombuffer(self.data,dtype,count=count,offset=pos+at)[:]=arr
  event.set()
 def consume(self,slot,gen,index,offset,core,length,timeout=5):
  with self.lock:self.verify(slot,gen,index);event=self.ready[3*slot+index-self.meta[slot*5+3]]
  if not event.wait(timeout):raise TimeoutError('Shared frontend producer did not publish')
  with self.lock:self.verify(slot,gen,index);pos=self.block_offset(slot,index)
  header=bytes(np.frombuffer(self.data,np.uint8,count=24,offset=pos))
  if struct.unpack('<qqq',header)!=(offset,core,length):raise ValueError('Shared frontend metadata mismatch')
  arrays=[np.frombuffer(self.data,dtype,count=n,offset=pos+at) for dtype,n,at in ((np.complex64,length,64),(np.float32,length,64+8*length),(np.float64,length-31,64+12*length))]
  for a in arrays:a.flags.writeable=False
  return arrays
 def active(self):return sum(bool(self.meta[i*5+1]) for i in range(self.slots))

class RingBackend(BackendV3):
 def __init__(self,ring,role):super().__init__();self.ring=ring;self.role=role;self.job=None
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
    out=np.empty((core+SAMPLES)*2,np.float32);native.library().rescue_resample_float(scratch,n+left+right,1000,core+SAMPLES,FIR,out);iq=out.view(np.complex64);power,score=self.prepare(iq);self.ring.publish(slot,gen,index,offset,available,iq,power,score)
   yield offset,available,iq

def initialize_ring(model,methods,runtime,assignments,companion,role,tuning,ring):
 workers.initialize(model,methods,runtime,assignments,companion,role,tuning)
 decoder=workers._DECODER;backend=RingBackend
 if tuning.get('cached_fir',False):
  from .fir_ring import FirRingBackend
  backend=FirRingBackend
 if role=='coherent' and tuning.get('optimized_extended',False):
  from .coherent_extended_opt import ExtendedNeonBackend
  # Preserve the shared-ring IQ path (and optional cached FIR) while replacing
  # only extended candidate selection. The fallback stays the V3 selector.
  backend=type('RingExtendedBackend',(backend,ExtendedNeonBackend),{})
 b=backend(ring,'consumer' if role=='coherent' else 'producer')
 if role=='coherent':decoder.backend=b;decoder.decoder.backend=b;decoder.decoder.score_function=b.coherent_scores
 else:decoder.blocks=b.iq_blocks;decoder.scores=b.candidate_scores;decoder.dsp_candidates=b.dsp_candidates;decoder.soft_decode=b.soft_decode;decoder.optimized_backend=b
 decoder._ring_backend=b

def decode_ring(slot,gen,path,bounds,stock,source_first,total_samples,policy=None):
 workers._DECODER._ring_backend.job=(slot,gen)
 return workers.decode_job(path,bounds,stock,source_first,total_samples,policy)

class RingStreamingPool(StreamingPool):
 def __init__(self,model,methods,runtime,selection,companion=None,**kwargs):
  cfg=selection.get('config',{})
  if not(cfg.get('optimized_v3') and cfg.get('sequence_acquisition') and selection.get('coherent_cpus')):raise ValueError('Ring requires native v3 split acquisition bundle')
  # Base owns grouping/delivery behavior. Lazy original executors have no workers.
  super().__init__(model,{**methods,'coherent':True},runtime,selection,companion,**kwargs)
  self.executor.shutdown();self.coherent_executor.shutdown();ctx=mp.get_context('spawn');self.ring=FrontendRing(self.max_pending_jobs,ctx);self.leases={}
  tuning=dict(coherent_enabled=methods.get('coherent',False),threshold=cfg.get('coherent_threshold',.35),budget=cfg.get('coherent_budget',48),optimized_dsp=True,optimized_v3=True,share_frontend=True,sequence_model=str(Path(model).parent/'pulse-sequence.json'),sequence_enabled=cfg.get('sequence_enabled',True),acquisition_enabled=cfg.get('acquisition_enabled',True),cached_fir=cfg.get('cached_fir',False),optimized_extended=cfg.get('optimized_extended',False),coherent_pair_retry=cfg.get('coherent_pair_retry',False))
  dm={**methods,'coherent':False}
  self.executor=futures.ProcessPoolExecutor(max_workers=selection['workers'],mp_context=ctx,initializer=initialize_ring,initargs=(str(model),dm,str(runtime),self.cpu_assignments,companion,'dsp',tuning,self.ring))
  self.coherent_executor=futures.ProcessPoolExecutor(max_workers=len(selection['coherent_cpus']),mp_context=ctx,initializer=initialize_ring,initargs=(str(model),dm,str(runtime),self.coherent_assignments,None,'coherent',tuning,self.ring))
 def submit(self,batch,stock=()):
  if len(self.pending)>=self.max_pending_jobs:raise RuntimeError('Bounded streaming pool full')
  lo,hi=batch.bounds;count=min(self.selection['workers'],hi-lo);ranges=[(lo+i*(hi-lo)//count,lo+(i+1)*(hi-lo)//count) for i in range(count)]
  slot,gen=self.ring.acquire(batch.raw,lo,hi);path=self.runtime/f'ring-{slot}-{gen}';self.leases[path]=(slot,gen);submitted=time.monotonic();tasks=[]
  try:
   tasks=[self.executor.submit(decode_ring,slot,gen,str(path),r,stock,batch.raw_start,TOTAL,getattr(self,'job_policy',None)) for r in ranges]
   tasks += [self.coherent_executor.submit(decode_ring,slot,gen,str(path),r,(),batch.raw_start,TOTAL,getattr(self,'job_policy',None)) for r in ranges]
  except BaseException:
   # Never recycle a partially submitted lease while any worker can write it.
   self.close();raise
  self.pending.append((batch,tasks,submitted,path));self.jobs+=1
 def clean_job(self,path):
  lease=self.leases.pop(path,None)
  if lease is not None:self.ring.release(*lease)
 def report(self):return {**super().report(),'cached_fir':self.selection.get('config',{}).get('cached_fir',False),'transport':'bounded_shared_ring','ring_slots':self.ring.slots,'ring_bytes':len(self.ring.data),'ring_active':self.ring.active()}
 def close(self):
  try:super().close()
  finally:
   # Parent waits for both executors before releasing remaining leases.
   for path in list(getattr(self,'leases',{})):self.clean_job(path)
