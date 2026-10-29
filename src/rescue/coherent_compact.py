"""Optional compact decisions; collection/research retain the frozen full API."""
import ctypes as C
from pathlib import Path
import numpy as np
_LIB=None

def library():
 global _LIB
 if _LIB is None:
  lib=C.CDLL(str(Path(__file__).with_name('_coherent_compact.so')));arr=lambda t:np.ctypeslib.ndpointer(t,flags='C_CONTIGUOUS')
  lib.rescue_coherent_compact.argtypes=[arr(np.float32),C.c_int64,arr(np.int64),C.c_int64,arr(np.uint8),arr(np.int8),arr(np.uint8)];lib.rescue_coherent_compact.restype=C.c_int
  if lib.rescue_coherent_init():raise RuntimeError('Invalid coherent CRC tables')
  _LIB=lib
 return _LIB

def compact_windows(iq,starts):
 iq=np.ascontiguousarray(iq,np.complex64);starts=np.ascontiguousarray(starts,np.int64)
 if iq.ndim!=1 or starts.ndim!=1 or len(starts)>4096 or np.any(starts<0) or np.any(starts>len(iq)-480):raise ValueError('Invalid compact coherent bounds')
 n=len(starts);rows=np.empty((n,14),np.uint8);flips=np.empty((n,2),np.int8);valid=np.empty(n,np.uint8)
 if library().rescue_coherent_compact(iq.view(np.float32),len(iq),starts,n,rows,flips,valid):raise ValueError('Compact coherent bounds failed')
 return rows,flips,valid.astype(bool)
