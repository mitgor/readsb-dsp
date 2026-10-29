"""Offline block-scoped candidate cache. Never changes live imports or switches.

Native and NumPy transforms remain distinct: their rounding/clipping differs.
Contexts own an immutable block and cannot survive a new sample-clock identity.
"""
from collections import Counter
import numpy as np
from . import native

class CandidateContext:
 def __init__(self,iq,identity,native_fused=False):
  self.iq=iq;self.identity=identity;self.fused=native_fused;self.headers={};self.energy={};self.count=Counter();self.workspace=None;self.catalog=None
 def header_ids(self,iq,starts):
  if iq is not self.iq:raise ValueError('Context/block mismatch')
  starts=np.asarray(starts,np.int64)
  if starts.ndim!=1 or np.any(starts<0) or np.any(starts+480>len(iq)):raise ValueError('Bad candidate bounds')
  if self.fused:
   ids,n=self.native_catalog().header(starts);self.count['header_requested']+=len(starts);self.count['header_computed']+=n
   return ids
  missing=np.array(sorted({int(v) for v in starts if int(v) not in self.headers}),np.int64)
  self.count['header_requested']+=len(starts);self.count['header_computed']+=len(missing)
  if len(missing):
   if self.fused:
    from .candidate_native import CandidateWorkspace
    if self.workspace is None:self.workspace=CandidateWorkspace()
    flags,rows,valid=self.workspace.prepare(iq,missing)
    for i,s in enumerate(missing):
     self.headers[int(s)]=bool(flags[i])
     if flags[i]:self.energy[int(s)]=(rows[i].copy(),bool(valid[i]))
   else:
    ids=set(map(int,native.header_ids(iq,missing)))
    self.headers.update((int(s),i in ids) for i,s in enumerate(missing))
  return np.array([i for i,s in enumerate(starts) if self.headers[int(s)]],np.int64)
 def energy_candidates(self,iq,starts):
  if iq is not self.iq:raise ValueError('Context/block mismatch')
  starts=np.asarray(starts,np.int64)
  if self.fused:
   rows,valid,n=self.native_catalog().energy(starts);self.count['energy_requested']+=len(starts);self.count['energy_computed']+=n
   return rows.copy(),valid
  missing=np.array(sorted({int(v) for v in starts if int(v) not in self.energy}),np.int64)
  self.count['energy_requested']+=len(starts);self.count['energy_computed']+=len(missing)
  if len(missing):
   rows,valid=native.energy_candidates(iq,missing)
   self.energy.update((int(s),(rows[i].copy(),bool(valid[i]))) for i,s in enumerate(missing))
  return np.array([self.energy[int(s)][0] for s in starts],np.uint8).reshape(-1,14),np.array([self.energy[int(s)][1] for s in starts],bool)

 def native_catalog(self):
  from .candidate_native import CandidateWorkspace,NativeCatalog
  if self.workspace is None:self.workspace=CandidateWorkspace()
  if self.catalog is None:self.catalog=NativeCatalog(self.iq,self.workspace)
  return self.catalog
