"""Finite-file experiment runner. No sockets, SDR, live configuration or feed outputs."""
import time
from collections import Counter
from pathlib import Path
import numpy as np
import onnxruntime as ort
from .runtime import RescueDecoder
from .dsp import features,baseline,payloads,crc_batch,SAMPLES,FS
from .classical import window,logits_and_confidence,cancel_packet
from .research_dsp import phase_features,apply_cancellation,variable_windows

class ResearchDecoder:
    stages=('real_mix','phase','learned_timing','neural_sic')
    def __init__(self,models,budget=64,sic_budget=2):
        self.front=RescueDecoder('unused',frontend='native',neural=False)
        self.sessions={};self.budget=budget;self.sic_budget=sic_budget
        for name in ('real_mix','phase','timing','cancellation'):
            opt=ort.SessionOptions();opt.intra_op_num_threads=1;opt.inter_op_num_threads=1
            self.sessions[name]=ort.InferenceSession(str(Path(models)/(name+'.onnx')),opt,providers=['CPUExecutionProvider'])
    def decode(self,path,stock=(),limit_blocks=None):
        events={s:[] for s in self.stages};counts=Counter();timing=Counter();start=time.perf_counter()
        def emit(stage,positions,pred,offset,**detail):
            valid=(crc_batch(pred)==0)&((pred[:,0]>>3)==17)
            for j in np.flatnonzero(valid):
                sample=float(positions[j]+offset)
                events[stage].append(dict(seconds=sample/FS,sample_4msps=sample,message_hex=pred[j].tobytes().hex(),source='neural',experiment_source=stage,research_only=True,**detail))
        for bi,(offset,core,iq) in enumerate(self.front.blocks(path,.05)):
            if limit_blocks is not None and bi>=limit_blocks:break
            mark=time.perf_counter();starts,scores=self.front.scores(iq,core,.3)
            safe=(starts>=8)&(starts+488<len(iq));starts=starts[safe];scores=scores[safe]
            # Same true DF17 gate and bounded budget as the current neural worker.
            ids=self.front.header_ids(iq,starts) if len(starts) else np.array([],int)
            positions=starts[ids];sc=scores[ids]
            pending=np.array([],int)
            if len(positions):
                raw=iq[positions[:,None]+np.arange(480)]
                pred=payloads(baseline(features(raw)));valid=(crc_batch(pred)==0)&((pred[:,0]>>3)==17)
                pending=np.flatnonzero(~valid)
            high=pending[sc[pending]>=.4]
            high=high[np.argsort(-sc[high],kind='stable')[:self.budget]]
            low=pending[np.argsort(-sc[pending],kind='stable')[:self.budget]]
            timing['front_s']+=time.perf_counter()-mark;counts['blocks']+=1;counts['ordinary_candidates']+=len(high);counts['timing_candidates']+=len(low)
            if len(high):
                p=positions[high];z=raw[high]
                for name,transform in (('real_mix',features),('phase',phase_features)):
                    mark=time.perf_counter();pred=payloads(self.sessions[name].run(None,{'iq_features':transform(z)})[0]);emit(name,p,pred,offset);timing[name+'_s']+=time.perf_counter()-mark
            if len(low):
                mark=time.perf_counter();p=positions[low]
                shift=self.sessions['timing'].run(None,{'preamble_features':features(raw[low])[:,:,:40].copy()})[0][:,0]
                z=variable_windows(iq,p,shift)
                pred=payloads(self.sessions['phase'].run(None,{'iq_features':phase_features(z)})[0]);emit('learned_timing',p+shift,pred,offset);timing['learned_timing_s']+=time.perf_counter()-mark
            mark=time.perf_counter()
            refs=[r for r in stock if offset+8<=r['seconds']*FS<offset+core-8]
            refs=sorted(refs,key=lambda r:-float(np.mean(np.abs(iq[round(r['seconds']*FS-offset):round(r['seconds']*FS-offset)+480])**2)))[:self.sic_budget]
            for ref in refs:
                p=round(ref['seconds']*FS-offset);counts['sic_attempts']+=1
                residual,fit=apply_cancellation(iq,p,ref['message_hex'],self.sessions['cancellation']);counts['sic_'+fit['reason']]+=1
                if residual is None:continue
                lo=max(0,p-480);hi=min(len(iq),p+960);local=iq[lo:hi].copy();local[p-lo:p-lo+480]=residual
                pos,score=self.front.scores(local,len(local)-480,.4);safe=(pos>=4)&(pos+484<len(local));pos=pos[safe];score=score[safe]
                pos=pos[np.argsort(-score,kind='stable')[:self.budget]]
                if len(pos):
                    pred=payloads(logits_and_confidence(window(local,pos))[0]);valid=(crc_batch(pred)==0)&((pred[:,0]>>3)==17)
                    # Compare with identical conventional cancellation AND uncancelled local RF.
                    # Different old budgets must not masquerade as neural SIC improvement.
                    conventional,_=cancel_packet(iq,p,ref['message_hex'])
                    counter=[]
                    for residual_cf in (None,conventional):
                        local_cf=iq[lo:hi].copy()
                        if residual_cf is not None:local_cf[p-lo:p-lo+480]=residual_cf
                        pc,sc=self.front.scores(local_cf,len(local_cf)-480,.4)
                        safe_cf=(pc>=4)&(pc+484<len(local_cf));pc=pc[safe_cf];sc=sc[safe_cf]
                        pc=pc[np.argsort(-sc,kind='stable')[:self.budget]]
                        if len(pc):
                            pr=payloads(logits_and_confidence(window(local_cf,pc))[0]);vc=(crc_batch(pr)==0)&((pr[:,0]>>3)==17)
                            counter.extend((int(pc[j]),r.tobytes().hex()) for j,r in enumerate(pr) if vc[j])
                    keep=valid&np.array([r.tobytes().hex()!=ref['message_hex'] and not any(r.tobytes().hex()==other and abs(int(pos[j])-t)<=480 for t,other in counter) for j,r in enumerate(pred)])
                    counts['sic_counterfactual_duplicates']+=int(valid.sum()-keep.sum())
                    emit('neural_sic',pos[keep],pred[keep],offset+lo,cancelled_message=ref['message_hex'])
            timing['neural_sic_s']+=time.perf_counter()-mark
        # Same payload may recur; deduplicate only within 120us of the same transmission.
        for stage,rows in events.items():
            seen={};kept=[]
            for r in sorted(rows,key=lambda x:x['seconds']):
                t=r['seconds'];key=r['message_hex']
                if t-seen.get(key,-1e9)<=120e-6:continue
                seen[key]=t;kept.append(r)
            events[stage]=kept
        return events,dict(wall_s=time.perf_counter()-start,counts=dict(counts),branch_seconds=dict(timing))
