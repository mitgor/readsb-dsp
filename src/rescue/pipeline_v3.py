"""Optional exact-output candidate; does not change live worker configuration."""
import ctypes as C
from pathlib import Path
import numpy as np
from .pipeline_native import FastBackend,fast_library
from .sequence_live import SequenceAcquisitionDecoder
from .classical import window
from .dsp import SAMPLES
_LIB=None

def library():
 global _LIB
 if _LIB is None:
  old=fast_library();lib=C.CDLL(str(Path(__file__).with_name('_pipeline_v3.so')))
  for name in ('rescue_fast_peaks','rescue_fast_convert','rescue_fast_soft','rescue_extended_scores'):
   f=getattr(lib,name);f.argtypes=getattr(old,name).argtypes;f.restype=getattr(old,name).restype
  from .research_sequence import library as sequence_library
  seq=sequence_library()
  for name in ('rescue_sequence_batch','rescue_sequence_prepare'):
   f=getattr(lib,name);f.argtypes=getattr(seq,name).argtypes;f.restype=getattr(seq,name).restype
  if lib.rescue_coherent_init():raise RuntimeError('Invalid CRC tables')
  _LIB=lib
 return _LIB

def integer_window(iq,starts,shift=0.,margin=0):
 integer=int(np.floor(shift))
 if shift-integer:return window(iq,starts,shift,margin)
 starts=np.asarray(starts,dtype=np.int64)
 positions=starts[:,None]+np.arange(-margin,SAMPLES+margin)[None,:]+integer
 return iq[positions]

class BackendV3(FastBackend):
 def __init__(self,cache_role=None):
  super().__init__(cache_role);self.lib=library();self.seq=self.lib

class SequenceV3(SequenceAcquisitionDecoder):
 def __init__(self,h,backend,threshold=.35,budget=48):
  super().__init__(h,backend,threshold,budget);self.sequence.native_library=library()

def enable_v3(decoder,cache_role=None):
 backend=BackendV3(cache_role);decoder.blocks=backend.iq_blocks;decoder.scores=backend.candidate_scores;decoder.dsp_candidates=backend.dsp_candidates;decoder.soft_decode=backend.soft_decode;decoder.optimized_backend=backend
 if decoder.classical:decoder.classical.window=integer_window
 return decoder

class SharedV3:
 """Construct the same serial complete bundle with isolated optimized helpers."""
 @staticmethod
 def create(h):
  from .pipeline_native import FastSharedRescue
  d=FastSharedRescue(h);b=BackendV3();d.backend=b;d.legacy.dsp_candidates=b.dsp_candidates;d.legacy.soft_decode=b.soft_decode;d.legacy.classical.window=integer_window;d.sequence.native_library=library();return d
