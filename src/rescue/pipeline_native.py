"""Opt-in native DSP backend and bounded tmpfs frontend sharing; no SDR I/O."""
import ctypes as C
import struct,time,os
from pathlib import Path
import numpy as np
from scipy.signal import find_peaks
from . import native
from .dsp import FIR,SAMPLES,PREAMBLE
from .classical import SHIFTS
from .research_sequence import SharedRescue
_LIB=None

def fast_library():
 global _LIB
 if _LIB is None:
  lib=C.CDLL(str(Path(__file__).with_name('_pipeline_native.so')));arr=lambda t:np.ctypeslib.ndpointer(dtype=t,flags='C_CONTIGUOUS')
  lib.rescue_fast_peaks.argtypes=[arr(np.float64),C.c_int64,C.c_double,arr(np.int64)];lib.rescue_fast_peaks.restype=C.c_int64
  lib.rescue_fast_convert.argtypes=[arr(np.uint8),*([C.c_int64]*3),arr(np.float32)];lib.rescue_fast_convert.restype=C.c_int
  lib.rescue_fast_soft.argtypes=[arr(np.float32),arr(np.float32),C.c_int64,C.c_float,C.c_int,C.c_int,arr(np.int64),arr(np.uint8),arr(np.int8),C.POINTER(C.c_int64)];lib.rescue_fast_soft.restype=C.c_int64
  lib.rescue_extended_scores.argtypes=[arr(np.float32),C.c_int64,*([C.c_double]*3),arr(np.float64)];lib.rescue_extended_scores.restype=C.c_int
  if lib.rescue_coherent_init():raise RuntimeError('Invalid CRC table')
  _LIB=lib
 return _LIB

class FastBackend:
 library=staticmethod(native.library);header_ids=staticmethod(native.header_ids);energy_candidates=staticmethod(native.energy_candidates)
 def __init__(self,cache_role=None):
  if cache_role not in (None,'producer','consumer'):raise ValueError('Invalid cache role')
  self.cache_role=cache_role;self.cached_iq=None;self.cached_power=None;self.cached_score=None
  self.lib=fast_library();self.integers=np.floor(SHIFTS).astype(np.int64);taps=np.arange(-3,5);weights=[]
  for shift,integer in zip(SHIFTS,self.integers):
   w=np.sinc(taps-(shift-integer))*np.kaiser(8,5);weights.append((w/w.sum()).astype(np.float32))
  self.weights=np.stack(weights)
  known=np.r_[PREAMBLE,np.repeat([1,0,0,1,0,1,0,1,1,0],2)].astype(np.float32);template=known-known.mean()
  self.on=float(template[0]);self.off=float(template[2]);self.norm=float(np.dot(template,template))
  self.seq=self.lib;self.tie_fallbacks=0
 def peaks(self,score,threshold):
  score=np.ascontiguousarray(score,np.float64)
  if score.ndim!=1 or not np.isfinite(score).all():raise ValueError('Expected finite 1-D scores')
  if len(score)<3:return np.empty(0,np.int64),{}
  out=np.empty(len(score),np.int64);n=self.lib.rescue_fast_peaks(score,len(score),threshold,out)
  if n==-2:self.tie_fallbacks+=1;return find_peaks(score,height=threshold,distance=3)
  if n<0:raise ValueError('Invalid peak bounds')
  return out[:n],{}
 def extended(self,power,core,budget=16):
  # Power is supplied by the frozen C scorer, already finite from UC8 FIR.
  sc=np.empty(len(power)-51,np.float64)
  if self.seq.rescue_extended_scores(power,len(power),self.on,self.off,self.norm,sc):raise ValueError('Invalid acquisition bounds')
  ids,_=self.peaks(sc,.30);ids=ids[(ids>=8)&(ids<core)&(ids+488<len(power))]
  if len(ids):ids=ids[np.argsort(-sc[ids],kind='stable')[:budget]]
  return ids,sc[ids]
 def dsp_candidates(self,iq,starts,timing=True,matched=True):
  starts=np.ascontiguousarray(starts,np.int64);capacity=len(starts)*7
  ids=np.empty(capacity,np.int64);methods=np.empty(capacity,np.int64);rows=np.empty((capacity,14),np.uint8)
  # Initialize ctypes signature through the frozen adapter once, without work.
  lib=native.library()
  if not getattr(lib.rescue_dsp,'argtypes',None):native.dsp_candidates(iq,np.empty(0,np.int64),False,False)
  self.last_native_dsp_cpu=None
  if hasattr(lib,'rescue_dsp_profiled'):
   f=lib.rescue_dsp_profiled;f.argtypes=[*lib.rescue_dsp.argtypes,np.ctypeslib.ndpointer(dtype=np.float64,flags='C_CONTIGUOUS')];f.restype=C.c_int64;cpu=np.zeros(2,np.float64)
   n=f(iq.view(np.float32),len(iq),starts,len(starts),self.integers,self.weights,int(timing),int(matched),ids,methods,rows,cpu)
   self.last_native_dsp_cpu=dict(timing=float(cpu[0]),matched=float(cpu[1]))
  else:n=lib.rescue_dsp(iq.view(np.float32),len(iq),starts,len(starts),self.integers,self.weights,int(timing),int(matched),ids,methods,rows)
  if n<0:raise ValueError('Invalid DSP bounds')
  return ids[:n],methods[:n],rows[:n]
 def soft_decode(self,logits,confidence,limit=.35,k=6,allow_header=False):
  l=np.ascontiguousarray(logits,np.float32);c=np.ascontiguousarray(confidence,np.float32)
  if l.ndim!=2 or l.shape[1]!=112 or c.shape!=l.shape or not np.isfinite(l).all() or not np.isfinite(c).all():raise ValueError('Invalid logits/confidence')
  n=len(l);ids=np.empty(n,np.int64);rows=np.empty((n,14),np.uint8);flips=np.empty((n,2),np.int8);hyp=C.c_int64()
  count=self.lib.rescue_fast_soft(l,c,n,limit,k,int(allow_header),ids,rows,flips,C.byref(hyp))
  if count<0:raise ValueError('Invalid soft bounds')
  return [(int(ids[j]),rows[j],tuple(int(b) for b in flips[j] if b>=0)) for j in range(count)],{'hypotheses':hyp.value}
 def prepare(self,iq):
  if iq is not self.cached_iq:
   power=np.empty(len(iq),np.float32);score=np.empty(len(iq)-31,np.float64)
   native.library().rescue_scores(iq.view(np.float32),len(iq),power,score)
   self.cached_iq=iq;self.cached_power=power;self.cached_score=score
  return self.cached_power,self.cached_score
 def candidate_scores(self,iq,core,threshold,with_power=False):
  power,score=self.prepare(iq);peaks,_=self.peaks(score,threshold);peaks=peaks[(peaks<core)&(peaks+SAMPLES<=len(iq))]
  return (peaks,score[peaks],power) if with_power else (peaks,score[peaks])
 def coherent_scores(self,iq,core,threshold):
  from .coherent_fast import library
  _,score=self.prepare(iq);out=np.empty(len(score),np.int64)
  n=library().rescue_coherent_peaks(score,len(score),core,len(iq),threshold,out)
  if n<0:raise ValueError('Invalid coherent selection')
  return out[:n],score[out[:n]]
 def iq_blocks(self,path,block_seconds=.05,block_range=None,source_first=0,total_samples=None):
  path=Path(path)
  if path.stat().st_size%2:raise ValueError('Truncated UC8 pair')
  raw=np.memmap(path,dtype=np.uint8,mode='r').reshape(-1,2);total=len(raw) if total_samples is None else total_samples
  if source_first and block_range is None:raise ValueError('Partial source needs explicit block range')
  hop=round(block_seconds*2400000/3)*3
  if hop<600:raise ValueError('Block too small')
  # Reuse conversion scratch; outputs are owned until the next iterator step.
  scratch=np.empty((hop+1200)*2,np.float32)
  for index,start in enumerate(range(0,total,hop)):
   if block_range is not None and not block_range[0]<=index<block_range[1]:continue
   end=min(start+hop,total);offset=start*5//3;core=end*5//3-offset;available=max(0,min(core,total*5//3-offset-SAMPLES+1));lo=max(0,start-600);hi=min(total,end+600);left=max(0,600-start);right=max(0,end+600-total);n=hi-lo
   if lo<source_first or hi>source_first+len(raw):raise ValueError('Missing FIR context')
   cache=Path(str(path)+f'.fast-{index}')
   if self.cache_role=='consumer':
    deadline=time.monotonic()+5
    while not cache.exists():
     if time.monotonic()>deadline:raise TimeoutError('Shared frontend producer did not finish')
     time.sleep(.001)
    view=np.memmap(cache,dtype=np.uint8,mode='r');off,span,length=struct.unpack('<qqq',view[:24]);expected=24+(core+SAMPLES)*12+(core+SAMPLES-31)*8
    if (off,span,length)!=(offset,available,core+SAMPLES) or len(view)!=expected:raise ValueError('Invalid shared frontend block')
    iq=view[24:24+length*8].view(np.complex64);power=view[24+length*8:24+length*12].view(np.float32);score=view[24+length*12:].view(np.float64)
    self.cached_iq=iq;self.cached_power=power;self.cached_score=score
    yield offset,available,iq
    continue
   if self.lib.rescue_fast_convert(raw[lo-source_first:hi-source_first].reshape(-1),n,left,right,scratch):raise ValueError('Conversion bounds')
   out=np.empty((core+SAMPLES)*2,np.float32);native.library().rescue_resample_float(scratch,n+left+right,1000,core+SAMPLES,FIR,out)
   iq=out.view(np.complex64)
   if self.cache_role=='producer':
    power,score=self.prepare(iq);tmp=Path(str(cache)+'.tmp')
    with tmp.open('wb') as f:
     f.write(struct.pack('<qqq',offset,available,len(iq)));f.write(memoryview(iq));f.write(memoryview(power));f.write(memoryview(score))
    os.replace(tmp,cache)
   yield offset,available,iq

class FastSharedRescue(SharedRescue):
 def __init__(self,h,current_only=False):
  backend=FastBackend();super().__init__(h,backend=backend,current_only=current_only)
  self.legacy.dsp_candidates=backend.dsp_candidates;self.legacy.soft_decode=backend.soft_decode


def enable_decoder(decoder,cache_role=None):
 """Attach the tested native policies without changing methods or admission."""
 backend=FastBackend(cache_role);decoder.blocks=backend.iq_blocks;decoder.scores=backend.candidate_scores
 decoder.dsp_candidates=backend.dsp_candidates;decoder.soft_decode=backend.soft_decode
 decoder.optimized_backend=backend
 if getattr(decoder,'coherent',None):decoder.coherent.score_function=backend.coherent_scores
 return decoder
