"""Bounded coherent/sequence/acquisition branches with shared carrier work."""
import time
from collections import Counter
import numpy as np
from .coherent_fast import FastCoherentDecoder,native_windows
from .research_sequence import PulseSequence
from .native import header_ids,energy_candidates
from .dsp import PREAMBLE

class SequenceAcquisitionDecoder(FastCoherentDecoder):
    def __init__(self,h,backend,threshold=.35,budget=48):
        super().__init__(source='coherent',threshold=threshold,budget=budget)
        self.backend=backend;self.sequence=PulseSequence(h)
    def decode(self,path,blocks=None,raw_events=False):
        begin=time.process_time();wall=time.perf_counter();cpu=Counter();counts=Counter();groups={k:[] for k in ('coherent','sequence','acquisition')}
        coherent=getattr(self,'coherent_enabled',True);sequence=getattr(self,'sequence_enabled',True);acquisition=getattr(self,'acquisition_enabled',True)
        pair_retry=getattr(self,'pair_retry',False) and coherent
        for offset,core,iq in blocks:
            mark=time.process_time();normal=pending=np.empty(0,np.int64)
            if coherent or sequence:
                normal,_=self.backend.coherent_scores(iq,core,self.threshold)
                normal=normal[(normal>=8)&(normal+488<len(iq))];normal=normal[header_ids(iq,normal)]
                _,valid=energy_candidates(iq,normal);pending=normal[~valid]
                if len(pending):
                    p=np.abs(iq[pending[:,None]+np.arange(32)])**2
                    rank=p[:,PREAMBLE.astype(bool)].mean(1)/(p[:,~PREAMBLE.astype(bool)].mean(1)+1e-8)
                    pending=pending[np.argsort(-rank,kind='stable')[:self.budget]]
            screen=time.process_time()-mark;cpu['coherent_screen_s']+=screen
            # Shared coherent/sequence screening is apportioned equally; output
            # costs and sequence decisions are timed separately.
            if coherent:cpu['method_coherent_s']+=screen/(1+int(sequence))
            if sequence:cpu['method_sequence_s']+=screen/(1+int(coherent))
            mark=time.process_time();acquire=np.empty(0,np.int64)
            if acquisition:
                power,_=self.backend.prepare(iq);acquire,_=self.backend.extended(power,int(core))
            acquire_cpu=time.process_time()-mark;cpu['acquisition_screen_s']+=acquire_cpu;cpu['method_acquisition_s']+=acquire_cpu if acquisition else 0
            starts=np.unique(np.r_[pending,acquire]);mark=time.process_time()
            _,_,tracked,freq,inliers,rows,flips,valid=native_windows(iq,starts)
            carrier_cpu=time.process_time()-mark;cpu['coherent_s']+=carrier_cpu
            pi=np.searchsorted(starts,pending);ai=np.searchsorted(starts,acquire)
            # Attribute each shared carrier hypothesis equally among its enabled
            # consumers. These are amortized costs, not counterfactual savings.
            membership=np.zeros(len(starts),float);membership[pi]+=int(coherent)+int(sequence);membership[ai]+=int(acquisition)
            for name,index,enabled in (('coherent',pi,coherent),('sequence',pi,sequence),('acquisition',ai,acquisition)):
                if enabled and len(starts):cpu['method_'+name+'_s']+=carrier_cpu*float(np.sum(1/membership[index]))/len(starts)
            def emit(source,positions,values,repairs,accepted):
                mark=time.process_time()
                for j in np.flatnonzero(accepted):
                    sample=int(offset+positions[j]);groups[source].append(dict(sample_4msps=sample,seconds=sample/4e6,message_hex=values[j].tobytes().hex(),source=source,experiment_source=source,flipped_bits=[int(b) for b in repairs[j] if b>=0],research_only=True))
                cpu['method_'+source+'_s']+=time.process_time()-mark
            if coherent:emit('coherent',pending,rows[pi],flips[pi],valid[pi])
            pair_valid=np.zeros(0,dtype=bool)
            failed=pending[~valid[pi]] if pair_retry else np.empty(0,np.int64)
            if len(failed):
                from .coherent_pair import pair_windows
                mark=time.process_time();result=pair_windows(iq,failed)
                elapsed=time.process_time()-mark;cpu['coherent_pair_s']+=elapsed;cpu['method_coherent_s']+=elapsed
                pair_valid=result[-1]
                emit('coherent',failed,result[5],result[6],pair_valid)
            if acquisition:emit('acquisition',acquire,rows[ai],flips[ai],valid[ai])
            sv=np.zeros(0,dtype=bool)
            if sequence:
                mark=time.process_time();sr,sf,sv,_,_=self.sequence.decode(iq,pending,freq[pi]);elapsed=time.process_time()-mark;cpu['sequence_s']+=elapsed;cpu['method_sequence_s']+=elapsed;emit('sequence',pending,sr,sf,sv)
            counts.update(blocks=1,ordinary_windows=len(normal),coherent_windows=len(pending),extended_windows=len(acquire),sequence_windows=len(pending) if sequence else 0,unique_carrier_windows=len(starts),shared_carrier_windows=len(pending)+len(acquire)-len(starts),sequence_outputs=int(sv.sum()),acquisition_outputs=int(valid[ai].sum()) if acquisition else 0,coherent_pair_windows=len(failed),coherent_pair_outputs=int(pair_valid.sum()))
        events=groups['coherent']+groups['sequence']+groups['acquisition']
        if not raw_events:
            from .workers import merge_events
            events=merge_events([events])
        return {'coherent':events},dict(cpu_s=time.process_time()-begin,wall_s=time.perf_counter()-wall,counts=dict(counts),branch_cpu_s=dict(cpu))
