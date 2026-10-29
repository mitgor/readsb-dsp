"""Isolated worker-local tap/schedule cache. Production configuration unchanged."""
import ctypes as C
from pathlib import Path
import numpy as np
from .dsp import FIR
from .pipeline_v3 import BackendV3
_LIB=None

def library():
 global _LIB
 if _LIB is None:
  lib=C.CDLL(str(Path(__file__).with_name('_fir_cached.so')));fp=np.ctypeslib.ndpointer(np.float32,flags='C_CONTIGUOUS');ip=np.ctypeslib.ndpointer(np.int64,flags='C_CONTIGUOUS')
  lib.rescue_fir_prepare.argtypes=[fp,C.c_int64,fp,fp,ip,ip];lib.rescue_fir_prepare.restype=C.c_int
  lib.rescue_fir_cached.argtypes=[fp,C.c_int64,C.c_int64,fp,fp,ip,ip,fp];lib.rescue_fir_cached.restype=C.c_int
  _LIB=lib
 return _LIB

class FirPlan:
 def __init__(self,h=FIR,first=1000):
  h=np.ascontiguousarray(h,np.float32)
  if h.shape!=(102,) or type(first) is not int:raise ValueError('Expected 102 taps and integer origin')
  self.packed=np.empty((5,24),np.float32);self.reverse=np.empty_like(self.packed);self.phases=np.empty(5,np.int64);self.indices=np.empty(5,np.int64)
  self.lib=library()
  if self.lib.rescue_fir_prepare(h,first,self.packed,self.reverse,self.phases,self.indices):raise ValueError('Invalid FIR taps/origin')
  self.first=first
 def resample_out(self,src,n,first,out):
  # Scratch may be larger than n. Outputs never alias the cached taps or input.
  if first!=self.first or src.dtype!=np.float32 or out.dtype!=np.float32 or not src.flags.c_contiguous or not out.flags.c_contiguous or src.ndim!=1 or out.ndim!=1 or len(out)%2 or type(n) is not int or not 0<=n<=len(src)//2 or np.shares_memory(src,out):raise ValueError('Invalid FIR buffers/origin')
  if self.lib.rescue_fir_cached(src,n,len(out)//2,self.packed,self.reverse,self.phases,self.indices,out):raise ValueError('Invalid FIR bounds')

# Same block conversion, halos, ownership and cache policy as the frozen backend.
import os,struct,time
from . import native
from .dsp import SAMPLES
class FirBackend(BackendV3):
 def __init__(self,cache_role=None):
  super().__init__(cache_role);self.fir=FirPlan()
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
   out=np.empty((core+SAMPLES)*2,np.float32);self.fir.resample_out(scratch,int(n+left+right),1000,out)
   iq=out.view(np.complex64)
   if self.cache_role=='producer':
    power,score=self.prepare(iq);tmp=Path(str(cache)+'.tmp')
    with tmp.open('wb') as f:
     f.write(struct.pack('<qqq',offset,available,len(iq)));f.write(memoryview(iq));f.write(memoryview(power));f.write(memoryview(score))
    os.replace(tmp,cache)
   yield offset,available,iq
