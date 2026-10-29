"""Bounded offline/shadow rescue worker; emits research JSON, no forwarding."""
import time
import numpy as np
import onnxruntime as ort
from .dsp import iq_blocks,candidate_scores,features,baseline,payloads,crc_batch,FS,SAMPLES

class RescueDecoder:
    def __init__(self,model,threshold=.4,budget=64,block_seconds=.05,threads=1,frontend='numpy',broad_crc=False,neural=True,methods=(),coherent=False,coherent_threshold=.3,coherent_budget=24):
        if not 0<threshold<=1 or budget<1:raise ValueError('Invalid gate or budget')
        self.broad_crc=broad_crc
        self.pulse_model=None
        self.neural_enabled=neural;self.methods=tuple(methods);self.stock=()
        self.coherent=None
        if coherent:
            from .coherent_fast import FastCoherentDecoder
            self.coherent=FastCoherentDecoder(source="coherent",threshold=coherent_threshold,budget=coherent_budget)
        self.classical=None
        if self.methods:
            from .classical import ClassicalDecoder
            self.classical=ClassicalDecoder(self,stages=self.methods)
        if broad_crc and frontend!='native':raise ValueError('Broad CRC requires native frontend')
        self.threshold=threshold;self.budget=budget;self.block_seconds=block_seconds
        if frontend=='native':
            from . import native
            native.library();self.blocks=native.iq_blocks;self.scores=native.candidate_scores;self.header_ids=native.header_ids
        elif frontend=='numpy':self.blocks=iq_blocks;self.scores=candidate_scores
        else:raise ValueError('Unknown frontend')
        options=ort.SessionOptions();options.intra_op_num_threads=threads;options.inter_op_num_threads=1
        options.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL
        self.session=ort.InferenceSession(str(model),options,providers=['CPUExecutionProvider']) if neural else None
        self.model=str(model)

    def decode(self,path,stock=(),block_range=None,raw_events=False,source_first=0,total_samples=None):
        stats=dict(blocks=0,candidates=0,baseline_valid=0,header_rejected=0,neural_windows=0,budget_dropped=0,late_blocks=0,max_block_s=0.,preprocess_s=0.,inference_s=0.)
        events=[];seen=None if raw_events or getattr(self,'coherent',None) else {};start=time.perf_counter();last=start
        options={} if block_range is None else {'block_range':block_range}
        if total_samples is not None:options.update(source_first=source_first,total_samples=total_samples)
        blocks=self.blocks(path,self.block_seconds,**options)
        for offset,core,iq in blocks:
            t=time.perf_counter();stats['preprocess_s']+=t-last
            if getattr(self,'broad_crc',False):
                from .native import broad_candidates
                starts,scores,power=self.scores(iq,core,self.threshold,with_power=True)
                # Same edge exclusions as the frozen broad comparison.
                eligible=np.flatnonzero((starts>=8)&(starts+488<len(iq)))
                mark=time.process_time()
                ci,cr,cf,cc=broad_candidates(power,starts[eligible])
                stats['broad_crc_s']=stats.get('broad_crc_s',0)+time.process_time()-mark
                stats['broad_raw']=stats.get('broad_raw',0)+len(ci)
                for j,i in enumerate(ci):
                    index=int(eligible[i]);bits=[int(b) for b in cf[j] if b>=0]
                    # Separate provisional events: never change frozen dedupe/NN output.
                    events.append(dict(sample_4msps=offset+int(starts[index]),seconds=(offset+int(starts[index]))/FS,
                        message_hex=cr[j].tobytes().hex(),source='broad_crc',preamble_score=float(scores[index]),
                        flipped_bits=bits,flip_confidences=[float(c) for c in cc[j,:len(bits)]],
                        crc=0,provisional=True,research_only=True))
            else:starts,scores=self.scores(iq,core,self.threshold)
            stats['blocks']+=1;stats['candidates']+=len(starts)
            energy_mark=time.process_time()
            if len(starts):
                # Upper bound work before features, so noise cannot create a huge tensor.
                # Baseline is evaluated in small batches over ALL candidates.
                # Batch the cheap header gate once per 50 ms block. Fancy
                # indexing avoids one Python slice/list entry per noise peak.
                if hasattr(self,'header_ids'):
                    ids=self.header_ids(iq,starts)
                else:
                    short=features(iq[starts[:,None]+np.arange(52)[None,:]])
                    p=short[:,0,32:52].reshape(-1,5,4)
                    bits=p[:,:,:2].sum(-1)>p[:,:,2:].sum(-1)
                    ids=np.flatnonzero(np.all(bits==np.array([1,0,0,0,1],bool),axis=1))
                stats['header_rejected']+=len(starts)-len(ids)
                pending=[]
                if len(ids):
                    pos=starts[ids]
                    if not getattr(self,'neural_enabled',True) and hasattr(self,'header_ids'):
                        from .native import energy_candidates
                        pred,valid=energy_candidates(iq,pos)
                    else:
                        x=features(iq[pos[:,None]+np.arange(SAMPLES)[None,:]])
                        pred=payloads(baseline(x));valid=(crc_batch(pred)==0)&((pred[:,0]>>3)==17)
                    stats['baseline_valid']+=int(valid.sum())
                    for j in np.flatnonzero(valid):
                        index=int(ids[j])
                        self._event(events,seen,offset+int(starts[index]),pred[j],'energy',float(scores[index]))
                    for j in np.flatnonzero(~valid):
                        index=int(ids[j]);pending.append((index,float(scores[index]),int(j)))
                chosen=sorted(sorted(pending,key=lambda r:(-r[1],r[0]))[:self.budget])
                stats['budget_dropped']+=max(0,len(pending)-len(chosen))
                stats['cpu_method_energy_s']=stats.get('cpu_method_energy_s',0)+time.process_time()-energy_mark
                if chosen and getattr(self,"neural_enabled",True):
                    ids=np.array([r[0] for r in chosen]);pos=starts[ids]
                    x=x[[r[2] for r in chosen]]
                    neural_mark=time.process_time();infer=time.perf_counter();out=self.session.run(None,{'iq_features':x})[0]
                    stats['inference_s']+=time.perf_counter()-infer
                    stats['cpu_method_neural_s']=stats.get('cpu_method_neural_s',0)+time.process_time()-neural_mark
                    stats['neural_windows']+=len(pos)
                    pred=payloads(out);valid=(crc_batch(pred)==0)&((pred[:,0]>>3)==17)
                    for j in np.flatnonzero(valid):
                        before=len(events)
                        self._event(events,seen,offset+int(pos[j]),pred[j],'neural',float(scores[ids[j]]))
                        if len(events)>before and hasattr(self.session,'last_candidate_mask'):
                            origin=getattr(self.session,'last_model_origin',None)
                            events[-1]['model_origin']=('rf_companion' if self.session.last_candidate_mask[j] else 'frozen') if origin is None else ('frozen','dsp_companion','raw_companion')[int(origin[j])]
            if getattr(self,"classical",None):
                # Reuse the same FIR output, preamble peaks and header screening.
                safe=[r for r in pending if starts[r[0]]>=8 and starts[r[0]]+488<len(iq)] if len(starts) else []
                selected=sorted(sorted(safe,key=lambda r:(-r[1],r[0]))[:self.classical.budget])
                rows,detail=self.classical.decode(None,stock=stock,blocks=[(offset,core,iq,starts,scores,selected)])
                for stage,items in rows.items():
                    for item in items:
                        previous_count=len(events)
                        self._event(events,seen,item['sample_4msps'],np.frombuffer(bytes.fromhex(item['message_hex']),np.uint8),stage,item.get('preamble_score',0.))
                        if len(events)>previous_count:events[-1].update(item)
                for stage,seconds in detail['branch_seconds'].items():
                    stats[stage+'_s']=stats.get(stage+'_s',0)+seconds
                    key='cpu_method_'+stage+'_s';stats[key]=stats.get(key,0)+seconds
            if getattr(self,'coherent',None):
                # Share the native FIR/IQ block; retain the validated 24-window
                # acquisition policy. Global worker merge owns seam deduplication.
                rows,detail=self.coherent.decode(None,blocks=[(offset,core,iq)],raw_events=True)
                for item in rows['coherent']:
                    before=len(events)
                    self._event(events,seen,item['sample_4msps'],np.frombuffer(bytes.fromhex(item['message_hex']),np.uint8),'coherent',0.)
                    if len(events)>before:events[-1].update(item)
                stats['coherent_cpu_s']=stats.get('coherent_cpu_s',0)+detail['cpu_s']
                for key,value in detail['counts'].items():
                    name=key if key.startswith('coherent_') else 'coherent_'+key
                    stats[name]=stats.get(name,0)+value
            if self.pulse_model is not None:
                from .pulse_live import decode_candidates
                rows,pulse=decode_candidates(iq,starts,scores,self.optimized_backend,self.soft_decode,self.pulse_model)
                stats['cpu_method_pulse_s']=stats.get('cpu_method_pulse_s',0)+pulse['cpu_s']
                stats['pulse_windows']=stats.get('pulse_windows',0)+pulse['windows']
                for position,row,score,flips in rows:
                    before=len(events)
                    self._event(events,seen,offset+position,row,'pulse',score)
                    if len(events)>before:events[-1]['flipped_bits']=flips
            now=time.perf_counter();elapsed=now-last
            stats['max_block_s']=max(stats['max_block_s'],elapsed)
            stats['late_blocks']+=elapsed>self.block_seconds
            # Keep only recent dedupe state, so live-length input is bounded.
            if seen is not None:
                seen={key:[s for s in times if offset+core-s<FS] for key,times in seen.items()}
                seen={key:times for key,times in seen.items() if times}
            last=now
        stats['cpu_method_crc_s']=stats.get('broad_crc_s',0)
        stats['wall_s']=time.perf_counter()-start
        if not raw_events:
            if getattr(self,'coherent',None):
                from .workers import merge_events
                events=merge_events([events])
            else:events.sort(key=lambda r:(r['sample_4msps'],r['source']))
        stats['outputs']=len(events)
        return events,stats

    @staticmethod
    def _event(events,seen,s,row,source,score):
        msg=row.tobytes().hex();key=msg
        if seen is not None:
            if any(abs(s-previous)<SAMPLES for previous in seen.get(key,[])):return
            seen.setdefault(key,[]).append(s)
        events.append(dict(sample_4msps=s,seconds=s/FS,message_hex=msg,source=source,preamble_score=score,crc=0,provisional=True,research_only=True))
