"""Isolated compact-export branch; sequence-on retains full diagnostics."""
import time
from collections import Counter
import numpy as np
from .coherent_fast import FastCoherentDecoder,native_windows
from .research_sequence import PulseSequence
from .native import header_ids,energy_candidates
from .dsp import PREAMBLE
from .coherent_compact import compact_windows

class CompactSequenceDecoder(FastCoherentDecoder):
    def __init__(self,h,backend,threshold=.35,budget=48):
        super().__init__(source='coherent',threshold=threshold,budget=budget)
        self.backend=backend;self.sequence=PulseSequence(h)
        from .pipeline_v3 import library
        self.sequence.native_library=library()
    def decode(self,path,blocks=None,raw_events=False):
        begin=time.process_time();wall=time.perf_counter();cpu=Counter();counts=Counter();groups={k:[] for k in ('coherent','sequence','acquisition')};block_cpu=[]
        for offset,core,iq in blocks:
            mark=time.process_time();normal,_=self.backend.coherent_scores(iq,core,self.threshold)
            normal=normal[(normal>=8)&(normal+488<len(iq))];normal=normal[header_ids(iq,normal)]
            _,valid=energy_candidates(iq,normal);pending=normal[~valid]
            if len(pending):
                p=np.abs(iq[pending[:,None]+np.arange(32)])**2
                rank=p[:,PREAMBLE.astype(bool)].mean(1)/(p[:,~PREAMBLE.astype(bool)].mean(1)+1e-8)
                pending=pending[np.argsort(-rank,kind='stable')[:self.budget]]
            power,_=self.backend.prepare(iq);acquire,_=self.backend.extended(power,int(core))
            starts=np.unique(np.r_[pending,acquire]);cpu['acquisition_screen_s']+=time.process_time()-mark;mark=time.process_time()
            if getattr(self,'sequence_enabled',True):
                _,_,tracked,freq,inliers,rows,flips,valid=native_windows(iq,starts)
            else:rows,flips,valid=compact_windows(iq,starts)
            cpu['coherent_s']+=time.process_time()-mark;mark=time.process_time()
            pi=np.searchsorted(starts,pending);ai=np.searchsorted(starts,acquire)
            def emit(source,positions,values,repairs,accepted):
                for j in np.flatnonzero(accepted):
                    sample=int(offset+positions[j]);groups[source].append(dict(sample_4msps=sample,seconds=sample/4e6,message_hex=values[j].tobytes().hex(),source=source,experiment_source=source,flipped_bits=[int(b) for b in repairs[j] if b>=0],research_only=True))
            emit('coherent',pending,rows[pi],flips[pi],valid[pi]);emit('acquisition',acquire,rows[ai],flips[ai],valid[ai])
            sv=np.zeros(0,dtype=bool)
            if getattr(self,'sequence_enabled',True):
                sr,sf,sv,_,_=self.sequence.decode(iq,pending,freq[pi]);emit('sequence',pending,sr,sf,sv)
            cpu['sequence_s']+=time.process_time()-mark
            counts.update(blocks=1,ordinary_windows=len(normal),coherent_windows=len(pending),extended_windows=len(acquire),sequence_windows=len(pending) if getattr(self,'sequence_enabled',True) else 0,unique_carrier_windows=len(starts),shared_carrier_windows=len(pending)+len(acquire)-len(starts),sequence_outputs=int(sv.sum()),acquisition_outputs=int(valid[ai].sum()))
            block_cpu.append(time.process_time()-mark)
        events=groups['coherent']+groups['sequence']+groups['acquisition']
        if not raw_events:
            from .workers import merge_events
            events=merge_events([events])
        return {'coherent':events},dict(cpu_s=time.process_time()-begin,wall_s=time.perf_counter()-wall,counts=dict(counts),branch_cpu_s=dict(cpu))
