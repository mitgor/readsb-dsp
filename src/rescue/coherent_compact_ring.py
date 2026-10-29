"""Isolated compact coherent candidate on the deployed cached-FIR transport."""
import concurrent.futures as futures
import multiprocessing as mp
import json
from pathlib import Path
import numpy as np
from . import ring_transport as rt,workers
from .coherent_compact_candidate import CompactSequenceDecoder

def initialize_compact(*args):
 rt.initialize_ring(*args)
 model,methods,runtime,assignments,companion,role,tuning,ring=args
 if role=='coherent':
  h=json.loads(Path(tuning['sequence_model']).read_text());b=workers._DECODER._ring_backend
  d=CompactSequenceDecoder(np.array(h['h_real'])+1j*np.array(h['h_imag']),b,tuning['threshold'],tuning['budget']);d.sequence_enabled=tuning.get('sequence_enabled',True);workers._DECODER.decoder=d

class CompactRingPool(rt.RingStreamingPool):
 def __init__(self,model,methods,runtime,selection,companion=None,**kwargs):
  super().__init__(model,methods,runtime,selection,companion,**kwargs)
  self.coherent_executor.shutdown();ctx=mp.get_context('spawn');cfg=selection['config'];dm={**methods,'coherent':False}
  tuning=dict(threshold=cfg.get('coherent_threshold',.35),budget=cfg.get('coherent_budget',48),optimized_dsp=True,optimized_v3=True,share_frontend=True,sequence_model=str(Path(model).parent/'pulse-sequence.json'),sequence_enabled=cfg.get('sequence_enabled',True),cached_fir=True)
  self.coherent_executor=futures.ProcessPoolExecutor(max_workers=len(selection['coherent_cpus']),mp_context=ctx,initializer=initialize_compact,initargs=(str(model),dm,str(runtime),self.coherent_assignments,None,'coherent',tuning,self.ring))
