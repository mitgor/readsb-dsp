"""Opt-in research companion, loaded only by the separate paired experiment.

Used only by the explicitly enabled parallel neural experiment.
Shares the frozen decoder's acquired windows and feature tensors. A valid frozen
DF17 prediction always wins. Only failed predictions can be rescued by the RF
model. CRC acceptance and prior-stock guards still belong to the caller.
"""
import time
from collections import Counter
import numpy as np
from .dsp import payloads,crc_batch

def select_logits(original,candidate):
    if original.shape!=candidate.shape or original.ndim!=2 or original.shape[1]!=112:
        raise ValueError('Expected matching N x 112 logits')
    def valid(logits):
        rows=payloads(logits)
        return (crc_batch(rows)==0)&((rows[:,0]>>3)==17)
    use=~valid(original)&valid(candidate)
    result=original.copy();result[use]=candidate[use]
    return result,use

class PairSession:
    def __init__(self,original,candidate):
        self.original=original;self.candidate=candidate;self.counts=Counter()
    def run(self,output_names,inputs):
        original=self.original.run(output_names,inputs)[0]
        mark=time.perf_counter();candidate=self.candidate.run(output_names,inputs)[0]
        result,use=select_logits(original,candidate);self.last_candidate_mask=use
        self.counts['candidate_inference_and_selection_s']+=time.perf_counter()-mark
        self.counts['windows']+=len(original);self.counts['candidate_rescued_windows']+=int(use.sum())
        return [result]

def paired_decoder(original,candidate,**kwargs):
    import onnxruntime as ort
    from .runtime import RescueDecoder
    if kwargs.get('neural',True) is False:raise ValueError('Companion requires neural decoding')
    decoder=RescueDecoder(original,**kwargs)
    options=ort.SessionOptions();options.intra_op_num_threads=kwargs.get('threads',1);options.inter_op_num_threads=1
    options.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL
    session=ort.InferenceSession(str(candidate),options,providers=['CPUExecutionProvider'])
    decoder.session=PairSession(decoder.session,session)
    return decoder
