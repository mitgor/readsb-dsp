"""Offline-only RF experiments. Frozen model/iteration bounds, no live I/O.
Not exact paper reproductions. No address, position or stock packet input.
"""
import ctypes as C
from pathlib import Path
import numpy as np
from .coherent_fast import native_windows
_LIB=None
_EM_LIB=None

def library():
 global _LIB
 if _LIB is None:
  _LIB=C.CDLL(str(Path(__file__).with_name('_science.so')))
  arr=lambda dtype:np.ctypeslib.ndpointer(dtype=dtype,flags='C_CONTIGUOUS')
  _LIB.rescue_science.argtypes=[arr(np.float32),C.c_int64,*([arr(np.float64)]*5),C.c_int,C.c_int,arr(np.float64),arr(np.float64),arr(np.uint8),arr(np.int8),arr(np.uint8),arr(np.float64)]
  _LIB.rescue_science.restype=C.c_int
  if _LIB.rescue_coherent_init():raise RuntimeError('CRC table invalid')
 return _LIB

def em_library():
 global _EM_LIB
 if _EM_LIB is None:
  path=Path(__file__).with_name('_science_em_rust.so')
  if not path.exists():return library()
  lib=C.CDLL(str(path));lib.rescue_science.argtypes=library().rescue_science.argtypes;lib.rescue_science.restype=C.c_int
  if lib.rescue_coherent_init():raise RuntimeError('Rust EM CRC table invalid')
  _EM_LIB=lib
 return _EM_LIB

def backend_status():
 return {'em':'rust' if Path(__file__).with_name('_science_em_rust.so').exists() else 'c','sequence':'c','em_sequence':'c'}

def decode(windows,h,method='em',iterations=4):
 z=np.ascontiguousarray(windows,np.complex64)
 if z.ndim!=2 or z.shape[1]!=496 or len(z)>4096 or not np.isfinite(z).all():raise ValueError('Expected finite [N,496] complex windows')
 if type(iterations) is not int or not 1<=iterations<=4:raise ValueError('Invalid iteration bound')
 if method not in ('em','sequence','em_sequence'):raise ValueError('Unknown method')
 h=np.asarray(h,np.complex128)
 if h.shape!=(9,) or not np.isfinite(h).all() or not np.linalg.norm(h)>0:raise ValueError('Expected finite nonzero nine-tap pulse response')
 n=len(z)
 if not n:return [],dict(logits=np.empty((0,112)),confidence=np.empty((0,112)),frequency=np.empty(0))
 l,c,t,f,_,_,_,_=native_windows(z.reshape(-1),np.arange(n,dtype=np.int64)*496+8)
 f=np.ascontiguousarray(f);l=np.ascontiguousarray(l);c=np.ascontiguousarray(c)
 ol=np.empty((n,112),np.float64);oc=np.empty_like(ol);r=np.empty((n,14),np.uint8);fl=np.empty((n,2),np.int8);v=np.empty(n,np.uint8);freq=np.empty(n,np.float64)
 assert (em_library() if method=='em' else library()).rescue_science(z.view(np.float32),n,f,l,c,np.ascontiguousarray(h.real),np.ascontiguousarray(h.imag),('em','sequence','em_sequence').index(method),iterations,ol,oc,r,fl,v,freq)==0
 rows=[dict(index=int(j),message_hex=r[j].tobytes().hex(),flipped_bits=[int(b) for b in fl[j] if b>=0]) for j in np.flatnonzero(v)]
 return rows,dict(logits=ol,confidence=oc,frequency=freq)

def extended_candidates(iq,core,budget=16):
 """Soft 13us preamble+DF evidence, bounded; never force the decoded header.
 No hard energy DF gate. Threshold empirical, not calibrated false-alarm rate.
 """
 from scipy.signal import find_peaks
 from .dsp import PREAMBLE
 p=np.abs(iq)**2
 # DF17 bits 10001 => chips 10 01 01 01 10, each chip two samples.
 known=np.r_[PREAMBLE,np.repeat([1,0,0,1,0,1,0,1,1,0],2)].astype(np.float32)
 template=known-known.mean();corr=np.correlate(p,template,'valid')
 cs=np.r_[0.,np.cumsum(p.astype(np.float64)**2)];norm=np.sqrt(np.maximum(cs[52:]-cs[:-52],1.e-12)*np.dot(template,template));score=corr/norm
 ids,_=find_peaks(score,height=.30,distance=3);ids=ids[(ids>=8)&(ids<core)&(ids+488<len(iq))]
 if len(ids):ids=ids[np.argsort(-score[ids],kind='stable')[:budget]]
 return ids,score[ids]
