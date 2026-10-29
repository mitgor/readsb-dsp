"""Isolated reusable per-worker workspace; no production switch or live changes."""
import ctypes as C
from pathlib import Path
import numpy as np
from scipy.signal import find_peaks
from .pipeline_v3 import BackendV3
from . import native
_LIB=None

def library():
 global _LIB
 if _LIB is None:
  lib=C.CDLL(str(Path(__file__).with_name('_pipeline_buffers.so')))
  lib.rescue_peak_workspace_bytes.argtypes=[C.c_int64];lib.rescue_peak_workspace_bytes.restype=C.c_size_t
  lib.rescue_buffered_peaks.argtypes=[np.ctypeslib.ndpointer(np.float64,flags='C_CONTIGUOUS'),C.c_int64,C.c_double,np.ctypeslib.ndpointer(np.int64,flags='C_CONTIGUOUS'),C.c_void_p,np.ctypeslib.ndpointer(np.uint8,flags='C_CONTIGUOUS')];lib.rescue_buffered_peaks.restype=C.c_int64
  _LIB=lib
 return _LIB

class BufferedBackend(BackendV3):
 def __init__(self,cache_role=None):
  super().__init__(cache_role);self.workspace_lib=library();self.buffers={};self.allocations=0
 def scratch(self,key,n,dtype):
  dtype=np.dtype(dtype);old=self.buffers.get(key)
  if old is None or old.dtype!=dtype or len(old)<n:
   old=np.empty(n,dtype);self.buffers[key]=old;self.allocations+=1
  return old[:n]
 def peaks(self,score,threshold):
  score=np.ascontiguousarray(score,np.float64)
  if score.ndim!=1 or not np.isfinite(score).all():raise ValueError('Expected finite 1-D scores')
  n=len(score)
  if n<3:return np.empty(0,np.int64),{}
  size=self.workspace_lib.rescue_peak_workspace_bytes(n)
  if not size:raise ValueError('Invalid peak bounds')
  # uint64 backing supplies native alignment for Peak (double + int64).
  space=self.scratch('peak_workspace',(size+7)//8,np.uint64)
  mask=self.scratch('peak_mask',n,np.uint8);out=self.scratch('peak_output',n,np.int64)
  count=self.workspace_lib.rescue_buffered_peaks(score,n,threshold,out,space.ctypes.data,mask)
  if count==-2:self.tie_fallbacks+=1;return find_peaks(score,height=threshold,distance=3)
  if count<0:raise ValueError('Invalid peak bounds')
  # Starts survive further peak calls in acquisition; never expose scratch.
  return out[:count].copy(),{}
 def prepare(self,iq):
  if iq is not self.cached_iq:
   power=self.scratch('power',len(iq),np.float32);score=self.scratch('score',len(iq)-31,np.float64)
   native.library().rescue_scores(iq.view(np.float32),len(iq),power,score)
   self.cached_iq=iq;self.cached_power=power;self.cached_score=score
  return self.cached_power,self.cached_score
 def extended(self,power,core,budget=16):
  sc=self.scratch('extended_score',len(power)-51,np.float64)
  if self.seq.rescue_extended_scores(power,len(power),self.on,self.off,self.norm,sc):raise ValueError('Invalid acquisition bounds')
  ids,_=self.peaks(sc,.30);ids=ids[(ids>=8)&(ids<core)&(ids+488<len(power))]
  if len(ids):ids=ids[np.argsort(-sc[ids],kind='stable')[:budget]]
  return ids,sc[ids]
