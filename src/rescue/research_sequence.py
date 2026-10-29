"""Offline shared-front-end sequence/acquisition decoder; no service or feed I/O."""
import ctypes as C,time
from pathlib import Path
from collections import Counter
import numpy as np
from scipy.signal import find_peaks
from .dsp import PREAMBLE
from . import native
from .coherent_fast import library as coherent_library,native_windows
from .runtime import RescueDecoder
from .workers import merge_events
_LIB=None

def library():
 global _LIB
 if _LIB is None:
  lib=C.CDLL(str(Path(__file__).with_name('_sequence.so')));arr=lambda t:np.ctypeslib.ndpointer(dtype=t,flags='C_CONTIGUOUS')
  lib.rescue_sequence_prepare.argtypes=[arr(np.float64)]*4;lib.rescue_sequence_prepare.restype=C.c_int
  lib.rescue_sequence_batch.argtypes=[arr(np.float32),C.c_int64,arr(np.int64),C.c_int64,*([arr(np.float64)]*5),arr(np.uint8),arr(np.int8),arr(np.uint8)];lib.rescue_sequence_batch.restype=C.c_int
  lib.rescue_extended_scores.argtypes=[arr(np.float32),C.c_int64,C.c_double,C.c_double,C.c_double,arr(np.float64)];lib.rescue_extended_scores.restype=C.c_int
  if lib.rescue_coherent_init():raise RuntimeError('CRC tables invalid')
  _LIB=lib
 return _LIB

class PulseSequence:
 def __init__(self,h):
  h=np.asarray(h,np.complex128)
  if h.shape!=(9,) or not np.isfinite(h).all() or not np.linalg.norm(h)>0:raise ValueError('Expected finite nonzero nine-tap response')
  self.templates=np.empty((114,4,2,4,2),np.float64);self.pre=np.empty((24,2),np.float64)
  if library().rescue_sequence_prepare(np.ascontiguousarray(h.real),np.ascontiguousarray(h.imag),self.templates,self.pre):raise ValueError('Invalid pulse model')
 def decode(self,iq,starts,frequency):
  iq=np.ascontiguousarray(iq,np.complex64);starts=np.ascontiguousarray(starts,np.int64);frequency=np.ascontiguousarray(frequency,np.float64)
  n=len(starts)
  if iq.ndim!=1 or starts.ndim!=1 or frequency.shape!=(n,) or n>4096 or np.any(starts<8) or np.any(starts+488>len(iq)) or not np.isfinite(iq).all() or np.isinf(frequency).any():raise ValueError('Invalid bounded sequence windows')
  l=np.empty((n,112),np.float64);c=np.empty_like(l);rows=np.empty((n,14),np.uint8);flips=np.empty((n,2),np.int8);valid=np.empty(n,np.uint8)
  lib=getattr(self,'native_library',None) or library()
  if n and lib.rescue_sequence_batch(iq.view(np.float32),len(iq),starts,n,frequency,self.templates,self.pre,l,c,rows,flips,valid):raise ValueError('Native sequence bounds failed')
  return rows,flips,valid.astype(bool),l,c

def extended_from_power(power,core,budget=16):
 power=np.ascontiguousarray(power,np.float32)
 if power.ndim!=1 or len(power)<52 or not np.isfinite(power).all() or np.any(power<0) or type(budget) is not int or not 1<=budget<=256 or type(core) is not int or not 0<=core<=len(power):raise ValueError('Invalid acquisition input')
 known=np.r_[PREAMBLE,np.repeat([1,0,0,1,0,1,0,1,1,0],2)].astype(np.float32);template=known-known.mean();sc=np.empty(len(power)-51,np.float64)
 if library().rescue_extended_scores(power,len(power),float(template[0]),float(template[2]),float(np.dot(template,template)),sc):raise ValueError('Invalid native acquisition')
 ids,_=find_peaks(sc,height=.30,distance=3);ids=ids[(ids>=8)&(ids<core)&(ids+488<len(power))]
 if len(ids):ids=ids[np.argsort(-sc[ids],kind='stable')[:budget]]
 return ids,sc[ids]

class SharedRescue:
 """Preserves frozen branch policies; shares FIR, power, score and carrier fits.
 Source attribution/admission stays offline. Existing decoder objects are local.
 """
 def __init__(self,h,backend=None,current_only=False):
  self.backend=backend or native;self.current_only=current_only
  self.sequence=PulseSequence(h);self.legacy=RescueDecoder('unused',frontend='native',neural=False,broad_crc=True,methods=('timing','soft','matched'))
 def decode(self,path):
  begin=time.process_time();wall=time.perf_counter();cpu=Counter();counts=Counter();groups={k:[] for k in ('current','sequence','acquisition')};block_cpu=[]
  backend=self.backend
  iterator=iter(backend.iq_blocks(path));last=time.process_time()
  while True:
   try:offset,core,iq=next(iterator)
   except StopIteration:break
   mark=time.process_time();cpu['frontend_s']+=mark-last;block_begin=last
   power=np.empty(len(iq),np.float32);score=np.empty(len(iq)-31,np.float64);backend.library().rescue_scores(iq.view(np.float32),len(iq),power,score)
   normal,_=backend.peaks(score,.4) if hasattr(backend,'peaks') else find_peaks(score,height=.4,distance=3);normal=normal[(normal<core)&(normal+480<=len(iq))]
   self.legacy.blocks=lambda *a,**kw:iter([(offset,core,iq)])
   self.legacy.scores=lambda *a,**kw:(normal,score[normal],power) if kw.get('with_power') else (normal,score[normal])
   current,_=self.legacy.decode(None,raw_events=True);groups['current'].extend(r for r in current if r['source']!='broad_crc');cpu['legacy_s']+=time.process_time()-mark;mark=time.process_time()
   positions=np.empty(len(score),np.int64);n=coherent_library().rescue_coherent_peaks(score,len(score),core,len(iq),.35,positions)
   if n<0:raise RuntimeError('Invalid coherent peaks')
   pending=positions[:n];pending=pending[(pending>=8)&(pending+488<len(iq))];pending=pending[backend.header_ids(iq,pending)];_,valid=backend.energy_candidates(iq,pending);pending=pending[~valid]
   if len(pending):
    p=np.abs(iq[pending[:,None]+np.arange(32)])**2;rank=p[:,PREAMBLE.astype(bool)].mean(1)/(p[:,~PREAMBLE.astype(bool)].mean(1)+1e-8);pending=pending[np.argsort(-rank,kind='stable')[:48]]
   acquire,_=(np.empty(0,np.int64),None) if self.current_only else (backend.extended(power,int(core)) if hasattr(backend,'extended') else extended_from_power(power,int(core)));all_starts=np.unique(np.r_[pending,acquire]);cpu['selection_s']+=time.process_time()-mark;mark=time.process_time()
   l,c,tracked,freq,inliers,rows,flips,valid=native_windows(iq,all_starts);cpu['carrier_s']+=time.process_time()-mark;mark=time.process_time()
   def emit(name,starts,values,repairs,accepted):
    for j in np.flatnonzero(accepted):
     sample=int(offset+starts[j]);groups[name].append(dict(sample_4msps=sample,seconds=sample/4e6,message_hex=values[j].tobytes().hex(),source='coherent',experiment_source=name,flipped_bits=[int(b) for b in repairs[j] if b>=0],research_only=True))
   pi=np.searchsorted(all_starts,pending);ai=np.searchsorted(all_starts,acquire)
   emit('current',pending,rows[pi],flips[pi],valid[pi]);emit('acquisition',acquire,rows[ai],flips[ai],valid[ai])
   if not self.current_only:
    sr,sf,sv,_,_=self.sequence.decode(iq,pending,freq[pi]);emit('sequence',pending,sr,sf,sv)
   cpu['sequence_s']+=time.process_time()-mark
   counts.update(blocks=1,coherent_windows=len(pending),extended_windows=len(acquire),unique_carrier_windows=len(all_starts),shared_carrier_windows=len(pending)+len(acquire)-len(all_starts));last=time.process_time();block_cpu.append(last-block_begin)
  current=merge_events([groups['current']]);combined=merge_events([current,groups['sequence'],groups['acquisition']])
  # Cached closures retain only the last 50ms block, never a capture-sized array.
  return dict(current=current,sequence=groups['sequence'],acquisition=groups['acquisition'],combined=combined),dict(cpu_s=time.process_time()-begin,wall_s=time.perf_counter()-wall,stage_cpu_s=dict(cpu),counts=dict(counts),p99_block_cpu_s=float(np.quantile(block_cpu,.99)) if block_cpu else 0)
