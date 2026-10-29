"""Isolated reusable candidate buffers. Not connected to production workers."""
import ctypes as C
from pathlib import Path
import numpy as np
_LIB=None
class CandidateWorkspace:
 def __init__(self):self.capacity=0
 def prepare(self,iq,starts):
  global _LIB
  iq=np.ascontiguousarray(iq,np.complex64);starts=np.ascontiguousarray(starts,np.int64);n=len(starts)
  if iq.ndim!=1 or starts.ndim!=1 or n>8192 or np.any(starts<0) or np.any(starts>len(iq)-480):raise ValueError('Bad candidate bounds')
  if _LIB is None:
   _LIB=C.CDLL(str(Path(__file__).with_name('_candidate_context.so')));arr=lambda t:np.ctypeslib.ndpointer(dtype=t,flags='C_CONTIGUOUS');f=_LIB.rescue_candidate_prepare;f.argtypes=[arr(np.float32),C.c_int64,arr(np.int64),C.c_int64,arr(np.uint8),arr(np.uint8),arr(np.uint8)];f.restype=C.c_int
  if n>self.capacity:self.capacity=max(128,n);self.headers=np.empty(self.capacity,np.uint8);self.rows=np.empty((self.capacity,14),np.uint8);self.valid=np.empty(self.capacity,np.uint8)
  if not n:return np.empty(0,bool),np.empty((0,14),np.uint8),np.empty(0,bool)
  if _LIB.rescue_candidate_prepare(iq.view(np.float32),len(iq),starts,n,self.headers,self.rows,self.valid):raise ValueError('Invalid native candidate values')
  return self.headers[:n].astype(bool),self.rows[:n],self.valid[:n].astype(bool)

class NativeCatalog:
 """One RF block, native memoization; no unused row copying for header queries."""
 def __init__(self,iq,workspace):
  self.iq=iq;self.w=workspace;length=len(iq);workspace.prepare(iq,np.empty(0,np.int64))
  arr=lambda t:np.ctypeslib.ndpointer(dtype=t,flags='C_CONTIGUOUS')
  if not getattr(_LIB,'catalog_bound',False):
   f=_LIB.rescue_cached_header;f.argtypes=[arr(np.float32),C.c_int64,arr(np.int64),C.c_int64,arr(np.uint8),arr(np.int64),C.POINTER(C.c_int64)];f.restype=C.c_int64
   f=_LIB.rescue_cached_energy;f.argtypes=[arr(np.float32),C.c_int64,arr(np.int64),C.c_int64,*([arr(np.uint8)]*5)];f.restype=C.c_int64;_LIB.catalog_bound=True
  if getattr(workspace,'catalog_capacity',0)<length:
   workspace.catalog_capacity=length;workspace.state=np.empty(length,np.uint8);workspace.catalog_rows=np.empty((length,14),np.uint8);workspace.catalog_valid=np.empty(length,np.uint8)
  workspace.state[:length]=0
 def query(self,starts):
  starts=np.ascontiguousarray(starts,np.int64)
  if starts.ndim!=1 or len(starts)>8192:raise ValueError('Invalid catalog dimensions')
  if len(starts)>getattr(self.w,'query_capacity',0):
   self.w.query_capacity=max(128,len(starts));self.w.query_ids=np.empty(self.w.query_capacity,np.int64);self.w.query_rows=np.empty((self.w.query_capacity,14),np.uint8);self.w.query_valid=np.empty(self.w.query_capacity,np.uint8)
  return starts
 def header(self,starts):
  starts=self.query(starts)
  if not len(starts):return np.empty(0,np.int64),0
  computed=C.c_int64();n=_LIB.rescue_cached_header(self.iq.view(np.float32),len(self.iq),starts,len(starts),self.w.state,self.w.query_ids,C.byref(computed))
  if n<0:raise ValueError('Invalid cached header')
  return self.w.query_ids[:n].copy(),computed.value
 def energy(self,starts):
  starts=self.query(starts);k=len(starts)
  if not k:return np.empty((0,14),np.uint8),np.empty(0,bool),0
  n=_LIB.rescue_cached_energy(self.iq.view(np.float32),len(self.iq),starts,k,self.w.state,self.w.catalog_rows,self.w.catalog_valid,self.w.query_rows,self.w.query_valid)
  if n<0:raise ValueError('Invalid cached energy')
  return self.w.query_rows[:k].copy(),self.w.query_valid[:k].astype(bool),n
