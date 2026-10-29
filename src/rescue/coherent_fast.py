"""Bounded native coherent decoder, shared by live workers and saved-file validation."""
import ctypes as C,time
from pathlib import Path
from collections import Counter
import numpy as np
from .native import iq_blocks,library as frontend,header_ids,energy_candidates,candidate_scores
from .dsp import PREAMBLE
_LIB=None

def library():
    global _LIB
    if _LIB is None:
        lib=C.CDLL(str(Path(__file__).with_name('_coherent.so')))
        arr=lambda dtype:np.ctypeslib.ndpointer(dtype=dtype,flags='C_CONTIGUOUS')
        lib.rescue_coherent.argtypes=[arr(np.float32),C.c_int64,arr(np.int64),C.c_int64,
            arr(np.float64),arr(np.float64),arr(np.uint8),arr(np.float64),arr(np.int32),arr(np.uint8),arr(np.int8),arr(np.uint8)]
        lib.rescue_coherent.restype=C.c_int
        lib.rescue_coherent_peaks.argtypes=[arr(np.float64),C.c_int64,C.c_int64,C.c_int64,C.c_double,arr(np.int64)]
        lib.rescue_coherent_peaks.restype=C.c_int64
        if lib.rescue_coherent_init():raise RuntimeError('Ambiguous coherent CRC syndrome table')
        _LIB=lib
    return _LIB

def native_windows(iq,starts):
    iq=np.ascontiguousarray(iq,np.complex64);starts=np.ascontiguousarray(starts,np.int64)
    if iq.ndim!=1 or starts.ndim!=1 or len(starts)>4096 or np.any(starts<0) or np.any(starts+480>len(iq)):raise ValueError('Invalid coherent window bounds')
    n=len(starts);logits=np.empty((n,112),np.float64);confidence=np.empty_like(logits)
    tracked=np.empty(n,np.uint8);frequency=np.empty(n,np.float64);inliers=np.empty(n,np.int32)
    rows=np.empty((n,14),np.uint8);flips=np.empty((n,2),np.int8);valid=np.empty(n,np.uint8)
    if library().rescue_coherent(iq.view(np.float32),len(iq),starts,n,logits,confidence,tracked,frequency,inliers,rows,flips,valid):raise ValueError('Native coherent bounds check failed')
    return logits,confidence,tracked,frequency,inliers,rows,flips,valid.astype(bool)

def scores(iq,core,threshold=.3):
    iq=np.ascontiguousarray(iq,np.complex64)
    if len(iq)<34:raise ValueError('RF block too short')
    power=np.empty(len(iq),np.float32);score=np.empty(len(iq)-31,np.float64)
    frontend().rescue_scores(iq.view(np.float32),len(iq),power,score)
    positions=np.empty(len(score),np.int64)
    n=library().rescue_coherent_peaks(score,len(score),core,len(iq),threshold,positions)
    if n<0:raise ValueError('Native peak selection failed')
    return positions[:n],score[positions[:n]]

class FastCoherentDecoder:
    stages=('coherent',)
    def __init__(self,budget=24,fast_peaks=True,source="matched",threshold=.3):
        if type(budget) is not int or not 1<=budget<=256:raise ValueError('Invalid candidate budget')
        if isinstance(threshold,bool) or not isinstance(threshold,(int,float)) or not 0<threshold<=1:raise ValueError('Invalid acquisition threshold')
        self.threshold=threshold
        self.budget=budget;self.fast_peaks=fast_peaks;self.source=source;library()

    def decode(self,path,blocks=None,raw_events=False):
        wall=time.perf_counter();begin=time.process_time();cpu=Counter();counts=Counter();events=[];block_cpu=[];last_cpu=begin
        for offset,core,iq in (iq_blocks(path,.05) if blocks is None else blocks):
            mark=time.process_time();normal,sc=getattr(self,'score_function',scores if self.fast_peaks else candidate_scores)(iq,core,self.threshold)
            safe=(normal>=8)&(normal+488<len(iq));normal=normal[safe]
            if len(normal):normal=normal[header_ids(iq,normal)]
            _,valid=energy_candidates(iq,normal);pending=normal[~valid]
            if len(pending):
                p=np.abs(iq[pending[:,None]+np.arange(32)[None,:]])**2
                rank=p[:,PREAMBLE.astype(bool)].mean(1)/(p[:,~PREAMBLE.astype(bool)].mean(1)+1e-8)
                pending=pending[np.argsort(-rank,kind='stable')[:self.budget]]
            cpu['acquisition_screen_s']+=time.process_time()-mark
            counts['blocks']+=1;counts['ordinary_windows']+=len(normal);counts['coherent_windows']+=len(pending)
            if len(pending):
                mark=time.process_time();_,_,tracked,frequency,inliers,rows,flips,valid=getattr(self,'window_function',native_windows)(iq,pending)
                cpu['coherent_s']+=time.process_time()-mark;counts['coherent_tracked']+=int(tracked.sum())
                for j in np.flatnonzero(valid):
                    sample=float(offset+pending[j]);fit={'tracked':bool(tracked[j])}
                    if tracked[j]:fit.update(frequency_hz=float(frequency[j]),phase_inliers=int(inliers[j]))
                    event=dict(sample_4msps=sample,seconds=sample/4e6,message_hex=rows[j].tobytes().hex(),source=self.source,experiment_source='coherent',research_only=True,fit=fit)
                    bits=[int(b) for b in flips[j] if b>=0]
                    if bits:event['flipped_bits']=bits
                    events.append(event)
            now=time.process_time();block_cpu.append(now-last_cpu);last_cpu=now
        seen={};keep=[]
        for row in sorted(events,key=lambda r:r['seconds']):
            p=row['message_hex'];t=row['seconds']
            if not raw_events and t-seen.get(p,-1e9)<=120e-6:continue
            seen[p]=t;keep.append(row)
        return {'coherent':keep},dict(cpu_s=time.process_time()-begin,wall_s=time.perf_counter()-wall,
            branch_cpu_s=dict(cpu),counts=dict(counts),budget_per_50ms=self.budget,fast_peaks=self.fast_peaks,
            block_cpu_s=block_cpu,max_block_cpu_s=max(block_cpu,default=0),p99_block_cpu_s=float(np.quantile(block_cpu,.99)) if block_cpu else 0)
