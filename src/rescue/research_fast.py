"""Offline-only first/second experiments, with bounded native interpolation.
No production imports this module. Existing weights and frontend stay untouched.
"""
import ctypes as c,time
from collections import Counter
from pathlib import Path
import numpy as np
import onnxruntime as ort
from .runtime import RescueDecoder
from .native import energy_candidates
from .dsp import features,crc_batch,payloads
from .research_dsp import phase_features,variable_windows
_LIB=None

def interpolate(iq,starts,shifts,native=True):
    global _LIB
    if not native:return variable_windows(iq,starts,shifts)
    if _LIB is None:
        _LIB=c.CDLL(str(Path(__file__).with_name('_research_interp.so')))
        arr=lambda dtype:np.ctypeslib.ndpointer(dtype=dtype,flags='C_CONTIGUOUS')
        _LIB.rescue_variable_windows.argtypes=[arr(np.float32),c.c_int64,arr(np.int64),arr(np.int64),arr(np.float32),c.c_int64,arr(np.float32)]
        _LIB.rescue_variable_windows.restype=c.c_int
    starts=np.ascontiguousarray(starts,np.int64);shifts=np.asarray(shifts,np.float64)
    integer=np.ascontiguousarray(np.floor(shifts),np.int64);taps=np.arange(-3,5)
    weights=np.sinc(taps[None,:]-(shifts-integer)[:,None])*np.kaiser(8,5)
    weights=np.ascontiguousarray(weights/weights.sum(1,keepdims=True),np.float32)
    iq=np.ascontiguousarray(iq,np.complex64);out=np.empty((len(starts),480),np.complex64)
    if _LIB.rescue_variable_windows(iq.view(np.float32),len(iq),starts,integer,weights,len(starts),out.view(np.float32)):
        raise ValueError('Interpolation would exceed captured RF')
    return out

class FastResearchDecoder:
    stages=('real_mix','phase','learned_timing')
    def __init__(self,models,budget=64,native=True,timing_only=False,selector=None,timing_enabled=True):
        self.front=RescueDecoder('unused',frontend='native',neural=False);self.budget=budget;self.native=native;self.timing_only=timing_only;self.selector=selector;self.block_filter=None;self.timing_enabled=timing_enabled
        self.sessions={}
        for name in ('phase','timing') if timing_only else ('real_mix','phase','timing'):
            opt=ort.SessionOptions();opt.intra_op_num_threads=1;opt.inter_op_num_threads=1
            if name=='timing' and not timing_enabled:continue
            self.sessions[name]=ort.InferenceSession(str(Path(models)/(name+'.onnx')),opt,providers=['CPUExecutionProvider'])
    def decode(self,path,stock=(),blocks=None):
        events={k:[] for k in self.stages};counts=Counter();timing=Counter();begin=time.perf_counter();cpu=time.process_time()
        def emit(stage,positions,logits,offset):
            pred=payloads(logits);valid=(crc_batch(pred)==0)&((pred[:,0]>>3)==17)
            for j in np.flatnonzero(valid):
                sample=float(offset+positions[j]);events[stage].append(dict(seconds=sample/4e6,sample_4msps=sample,message_hex=pred[j].tobytes().hex(),source='neural',experiment_source=stage,research_only=True))
        if blocks is None and self.block_filter is not None:
            count=(Path(path).stat().st_size//2+119999)//120000
            ids=[i for i in range(count) if self.block_filter(i*200000)]
            groups=[]
            for i in ids:
                if groups and groups[-1][1]==i:groups[-1]=(groups[-1][0],i+1)
                else:groups.append((i,i+1))
            from itertools import chain
            blocks=chain.from_iterable(self.front.blocks(path,.05,block_range=g) for g in groups)
            counts['far_inactive_blocks_skipped']=count-len(ids)
        for offset,core,iq in (self.front.blocks(path,.05) if blocks is None else blocks):
            mark=time.perf_counter();starts,scores=self.front.scores(iq,core,.3)
            safe=(starts>=8)&(starts+488<len(iq));starts=starts[safe];scores=scores[safe]
            ids=self.front.header_ids(iq,starts) if len(starts) else np.array([],int);positions=starts[ids];sc=scores[ids]
            hard,valid=energy_candidates(iq,positions);pending=np.flatnonzero(~valid.astype(bool))
            high=pending[sc[pending]>=.4];high=high[np.argsort(-sc[high],kind='stable')[:self.budget]]
            low=pending[np.argsort(-sc[pending],kind='stable')[:self.budget]]
            if self.selector is not None:
                far=self.selector(offset,positions,hard)
                priority=pending[far[pending]];other=pending[~far[pending]]
                priority=priority[np.argsort(-sc[priority],kind='stable')[:32]]
                other=other[np.argsort(-sc[other],kind='stable')[:8]]
                low=np.concatenate((priority,other));counts['far_shortlisted']+=len(priority);counts['exploration_shortlisted']+=len(other)
            counts['blocks']+=1;counts['ordinary_candidates']+=len(high);counts['timing_candidates']+=len(low);timing['front_s']+=time.perf_counter()-mark
            if len(high) and not self.timing_only:
                z=iq[positions[high,None]+np.arange(480)[None,:]]
                for name,transform in (('real_mix',features),('phase',phase_features)):
                    mark=time.perf_counter();emit(name,positions[high],self.sessions[name].run(None,{'iq_features':transform(z)})[0],offset);timing[name+'_s']+=time.perf_counter()-mark
            if len(low) and self.timing_enabled:
                mark=time.perf_counter();pos=positions[low]
                # Identical normalisation, only 40 acquisition samples instead of 480.
                small=iq[pos[:,None]+np.arange(40)[None,:]]
                shift=self.sessions['timing'].run(None,{'preamble_features':features(small)})[0][:,0]
                z=interpolate(iq,pos,shift,self.native)
                emit('learned_timing',pos+shift,self.sessions['phase'].run(None,{'iq_features':phase_features(z)})[0],offset);timing['learned_timing_s']+=time.perf_counter()-mark
        for key,rows in events.items():
            seen={};kept=[]
            for row in sorted(rows,key=lambda x:x['seconds']):
                p=row['message_hex'];t=row['seconds']
                if t-seen.get(p,-1e9)<=120e-6:continue
                seen[p]=t;kept.append(row)
            events[key]=kept
        return events,dict(wall_s=time.perf_counter()-begin,cpu_s=time.process_time()-cpu,counts=dict(counts),branch_seconds=dict(timing))
