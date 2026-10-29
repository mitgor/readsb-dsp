"""Opt-in offline CRC-gated neural cascade. Existing valid packets always win.

Companions only run on windows unresolved by every earlier model. Caller retains
stock/address/conflict guards; CRC validity alone does not authorize forwarding.
"""
import collections,hashlib,time
from pathlib import Path
import numpy as np
from .dsp import payloads,crc_batch

# The optional production cascade is selected only when neural=true. A model
# mismatch fails worker initialization instead of silently changing decoding.
PRODUCTION_COMPANIONS=(Path('candidates/dsp-20261025/tiny-rf-v1.onnx'),Path('candidates/improvement-raw-20261027/tiny-rf-v1.onnx'))
PRODUCTION_SHA256=('2422633f33e600eaa295dbd3cc48639573b2741adf641d6ad834b01f0be445d9','fe10fdc4ff4f71da03aae5b5a76106a42ce9cbbda5f27a917c8f7fd9e07429aa','18285149351966395b859a150e8bdc494576ecdc7ca17c7d3043226e899c0eb9')

def production_paths(root):
 paths=[Path(root)/'models/tiny-fp32.onnx',*(Path(root)/'models'/p for p in PRODUCTION_COMPANIONS)]
 if any(hashlib.sha256(p.read_bytes()).hexdigest()!=h for p,h in zip(paths,PRODUCTION_SHA256)):
  raise ValueError('Production neural model set failed integrity check')
 return paths

def valid_logits(logits):
 rows=payloads(logits);return (crc_batch(rows)==0)&(rows[:,0]>>3==17)

class CascadeSession:
 def __init__(self,sessions):
  if not sessions:raise ValueError('At least one model required')
  self.sessions=tuple(sessions);self.counts=collections.Counter()
 def run(self,output_names,inputs):
  x=inputs['iq_features']
  if x.ndim!=3 or x.shape[1:]!=(2,480):raise ValueError('Expected N x 2 x 480 production features')
  result=self.sessions[0].run(output_names,inputs)[0]
  if result.shape!=(len(x),112):raise ValueError('Invalid model output shape')
  self.last_model_origin=np.zeros(len(x),np.int16);good=valid_logits(result);self.counts['windows']+=len(x)
  for index,session in enumerate(self.sessions[1:],1):
   ids=np.flatnonzero(~good)
   if not len(ids):break
   started=time.process_time();candidate=session.run(output_names,{'iq_features':np.ascontiguousarray(x[ids])})[0]
   if candidate.shape!=(len(ids),112):raise ValueError('Invalid companion output shape')
   use=valid_logits(candidate);chosen=ids[use];result[chosen]=candidate[use];good[chosen]=True;self.last_model_origin[chosen]=index
   self.counts[f'model_{index}_windows']+=len(ids);self.counts[f'model_{index}_rescued']+=len(chosen);self.counts[f'model_{index}_cpu_s']+=time.process_time()-started
  self.last_candidate_mask=self.last_model_origin>0
  return [result]

def cascade_decoder(paths,**kwargs):
 import onnxruntime as ort
 from .runtime import RescueDecoder
 if kwargs.get('neural',True) is False:raise ValueError('Neural cascade requires inference')
 d=RescueDecoder(paths[0],**kwargs);options=ort.SessionOptions();options.intra_op_num_threads=kwargs.get('threads',1);options.inter_op_num_threads=1
 d.session=CascadeSession([d.session]+[ort.InferenceSession(str(p),options,providers=['CPUExecutionProvider']) for p in paths[1:]])
 return d
