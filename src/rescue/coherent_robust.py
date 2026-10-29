"""Offline-only inlier-consistent coherent retry; original valid results win."""
import ctypes as C
from pathlib import Path
import numpy as np
from .coherent_fast import library,native_windows,FastCoherentDecoder
_LIB=None
def robust_windows(iq,starts):
 global _LIB
 iq=np.ascontiguousarray(iq,np.complex64);starts=np.ascontiguousarray(starts,np.int64)
 if iq.ndim!=1 or starts.ndim!=1 or len(starts)>4096 or np.any(starts<0) or np.any(starts+480>len(iq)):raise ValueError('Invalid coherent window bounds')
 if _LIB is None:
  lib=C.CDLL(str(Path(__file__).with_name('_coherent_robust.so')));lib.rescue_coherent.argtypes=library().rescue_coherent.argtypes;lib.rescue_coherent.restype=C.c_int
  if lib.rescue_coherent_init():raise RuntimeError('Invalid CRC table')
  _LIB=lib
 n=len(starts);out=[np.zeros((n,112),np.float64),np.zeros((n,112),np.float64),np.zeros(n,np.uint8),np.full(n,np.nan),np.zeros(n,np.int32),np.zeros((n,14),np.uint8),np.full((n,2),-1,np.int8),np.zeros(n,np.uint8)]
 if _LIB.rescue_coherent(iq.view(np.float32),len(iq),starts,n,*out):raise ValueError('Invalid native bounds')
 out[-1]=out[-1].astype(bool);return tuple(out)
def rescue_windows(iq,starts):
 original=native_windows(iq,starts);failed=np.flatnonzero(~original[-1])
 if not len(failed):return original
 retry=robust_windows(iq,np.asarray(starts,dtype=np.int64)[failed]);accepted=np.flatnonzero(retry[-1])
 for dst,src in zip(original,retry):dst[failed[accepted]]=src[accepted]
 return original
class RobustCoherentDecoder(FastCoherentDecoder):
 def __init__(self):
  super().__init__(source='coherent',threshold=.35,budget=48);self.window_function=rescue_windows
