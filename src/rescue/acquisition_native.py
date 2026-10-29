"""Isolated exact-policy acquisition orchestration; no live configuration hook."""
import ctypes as C
from pathlib import Path
import numpy as np
from .dsp import PREAMBLE
from .pipeline_v3 import BackendV3
_LIB=None

def library():
 global _LIB
 if _LIB is None:
  lib=C.CDLL(str(Path(__file__).with_name('_acquisition_native.so')))
  arr=lambda t:np.ctypeslib.ndpointer(dtype=t,flags='C_CONTIGUOUS')
  ip=arr(np.int64);fp=arr(np.float32);dp=arr(np.float64)
  lib.rescue_acq_screen.argtypes=[fp,C.c_int64,ip,C.c_int64,ip,C.POINTER(C.c_int64)]
  lib.rescue_acq_top.argtypes=[ip,dp,C.c_int64,C.c_int64,ip]
  lib.rescue_acq_union.argtypes=[ip,C.c_int64,ip,C.c_int64,ip,ip,ip]
  for n in ('screen','top','union'):getattr(lib,'rescue_acq_'+n).restype=C.c_int64
  _LIB=lib
 return _LIB

def top(starts,rank,budget):
 starts=np.ascontiguousarray(starts,np.int64);rank=np.ascontiguousarray(rank,np.float64)
 if starts.ndim!=1 or rank.shape!=starts.shape or type(budget) is not int:raise ValueError('Invalid ranking')
 out=np.empty(min(len(starts),max(budget,0)),np.int64)
 n=library().rescue_acq_top(starts,rank,len(starts),budget,out)
 if n<0:raise ValueError('Invalid ranking bounds/values')
 return out[:n]

def screen(iq,normal,budget):
 iq=np.ascontiguousarray(iq,np.complex64);normal=np.ascontiguousarray(normal,np.int64)
 if iq.ndim!=1 or normal.ndim!=1:raise ValueError('Invalid screen shape')
 out=np.empty(len(normal),np.int64);ordinary=C.c_int64()
 n=library().rescue_acq_screen(iq.view(np.float32),len(iq),normal,len(normal),out,C.byref(ordinary))
 if n<0:raise ValueError('Invalid screening bounds')
 pending=out[:n]
 if n:
  # Preserve NumPy's exact platform-specific complex magnitude and pairwise sums.
  p=np.abs(iq[pending[:,None]+np.arange(32)])**2
  rank=p[:,PREAMBLE.astype(bool)].mean(1)/(p[:,~PREAMBLE.astype(bool)].mean(1)+1e-8)
  pending=top(pending,rank,budget)
 return pending,ordinary.value

def union(pending,acquire):
 pending=np.ascontiguousarray(pending,np.int64);acquire=np.ascontiguousarray(acquire,np.int64)
 if pending.ndim!=1 or acquire.ndim!=1:raise ValueError('Invalid union shape')
 out=np.empty(len(pending)+len(acquire),np.int64);pi=np.empty(len(pending),np.int64);ai=np.empty(len(acquire),np.int64)
 n=library().rescue_acq_union(pending,len(pending),acquire,len(acquire),out,pi,ai)
 if n<0:raise ValueError('Invalid union bounds')
 return out[:n],pi,ai

class AcquisitionBackend(BackendV3):
 def extended(self,power,core,budget=16):
  sc=np.empty(len(power)-51,np.float64)
  if self.seq.rescue_extended_scores(power,len(power),self.on,self.off,self.norm,sc):raise ValueError('Invalid acquisition bounds')
  ids,_=self.peaks(sc,.30);ids=ids[(ids>=8)&(ids<core)&(ids+488<len(power))]
  ids=top(ids,sc[ids],budget)
  return ids,sc[ids]
