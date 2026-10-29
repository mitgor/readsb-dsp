"""Bounded, experimental DSP branches. Offline/shadow only; no feed injection.

Branches are independently attributed in a fixed order. CRC search preserves the
received ICAO bits, tests at most two low-confidence flips, and rejects ambiguity.
Interpolation does not create additional RF bandwidth.
"""
import itertools,time
from collections import Counter
import numpy as np
from .dsp import PREAMBLE,SAMPLES,FS,features,baseline,payloads,crc_batch

DF17=np.array([1,0,0,0,1],bool)
SHIFTS=(-1.,-.5,-.25,.25,.5,1.)
# Linear CRC allows cheap syndrome lookup instead of recomputing 21 full frames.
BIT_SYNDROMES=crc_batch(np.packbits(np.eye(112,dtype=np.uint8),axis=1))


def window(iq,starts,shift=0.,margin=0):
    """Eight-tap windowed-sinc interpolation of original complex samples."""
    starts=np.asarray(starts,dtype=np.int64);length=SAMPLES+margin*2
    integer=int(np.floor(shift));fraction=shift-integer
    taps=np.arange(-3,5);weights=np.sinc(taps-fraction)*np.kaiser(8,5)
    weights=(weights/weights.sum()).astype(np.float32)
    positions=starts[:,None]+np.arange(-margin,SAMPLES+margin)[None,:]+integer
    out=np.zeros((len(starts),length),np.complex64)
    if fraction==0:return iq[positions]
    for tap,weight in zip(taps,weights):out+=iq[positions+tap]*weight
    return out


def logits_and_confidence(windows):
    power=np.abs(windows)**2;p=power[:,32:].reshape(-1,112,4)
    left=p[:,:,:2].sum(-1);right=p[:,:,2:].sum(-1)
    return left-right,np.abs(left-right)/(left+right+1e-9)


def soft_decode_reference(logits,confidence,limit=.35,k=6,allow_header=False):
    """Unique CRC solution among <=21 hypotheses. Never alter ICAO bits 8..31.
    No unrestricted bit guessing, packet synthesis, or future-track imputation.
    """
    original=payloads(logits);syndromes=crc_batch(original);out=[];stats=Counter()
    for i,syndrome in enumerate(syndromes):
        if not syndrome:continue
        eligible=np.r_[np.arange(5) if allow_header else np.array([],int),np.arange(32,112)]
        ids=eligible[np.argsort(confidence[i,eligible],kind='stable')[:k]]
        ids=ids[confidence[i,ids]<=limit];solutions=[]
        for count in (1,2):
            for flipped in itertools.combinations(ids,count):
                stats['hypotheses']+=1
                correction=0
                for bit in flipped:correction^=int(BIT_SYNDROMES[bit])
                if correction!=int(syndrome):continue
                row=original[i].copy()
                for bit in flipped:row[bit//8]^=1<<(7-bit%8)
                if row[0]>>3==17:solutions.append((row,tuple(map(int,flipped))))
        if len(solutions)==1:out.append((i,*solutions[0]))
        elif solutions:stats['ambiguous']+=1
    return out,dict(stats)


def soft_decode(logits,confidence,limit=.35,k=6,allow_header=False):
    # All <=2-bit syndromes are unique. Lookup first, then impose the SAME
    # weak-bit/header/address constraints as the <=21-hypothesis reference.
    out=[];hypotheses=0
    for i,row,bits,_ in broad_decode(logits):
        eligible=np.r_[np.arange(5) if allow_header else np.array([],int),np.arange(32,112)]
        ids=eligible[np.argsort(confidence[i,eligible],kind='stable')[:k]]
        allowed=set(map(int,ids[confidence[i,ids]<=limit]))
        if set(bits)<=allowed:out.append((i,row,bits));hypotheses+=len(allowed)*(len(allowed)+1)//2
    return out,{'hypotheses':hypotheses}


def carrier(windows):
    """Estimate coarse carrier offset from four known preamble pulses only."""
    positions=np.array([0,1,4,5,14,15,18,19]);frequencies=np.arange(-100000,100001,5000)
    rotation=np.exp(-2j*np.pi*frequencies[:,None]*positions[None,:]/FS)
    coherent=np.abs(windows[:,positions]@rotation.T)**2
    selected=frequencies[np.argmax(coherent,axis=1)]
    return windows*np.exp(-2j*np.pi*selected[:,None]*np.arange(windows.shape[1])[None,:]/FS),selected


def matched_logits(padded):
    """Complex matched correlations using pulse shape estimated from preamble.
    The estimated filter is an experimental short channel approximation.
    """
    packet=padded[:,4:4+SAMPLES]
    _,frequency=carrier(packet)
    z=padded*np.exp(-2j*np.pi*frequency[:,None]*(np.arange(padded.shape[1])-4)[None,:]/FS)
    offsets=np.arange(-1,3)
    shape=z[:,4+np.array([0,4,14,18])[:,None]+offsets[None,:]].mean(axis=1)
    starts=4+32+np.arange(112)*4
    left=z[:,starts[:,None]+offsets[None,:]]
    right=z[:,starts[:,None]+2+offsets[None,:]]
    a=np.abs(np.einsum('nbt,nt->nb',left,shape.conj()))**2
    b=np.abs(np.einsum('nbt,nt->nb',right,shape.conj()))**2
    return a-b,np.abs(a-b)/(a+b+1e-9)


def pulse_train(payload):
    bits=np.unpackbits(np.frombuffer(bytes.fromhex(payload),np.uint8))
    signal=np.zeros(SAMPLES,np.float64);signal[:32]=PREAMBLE
    data=signal[32:].reshape(112,4)
    data[bits==1,:2]=1;data[bits==0,2:]=1
    return signal


def cancel_packet(iq,start,payload):
    """Fit one known CRC-valid packet, then subtract its complex waveform.
    At most one cancellation per copy; bad fits/clipped input are rejected.
    """
    start=int(start)
    if start<4 or start+SAMPLES+4>len(iq):return None,{'reason':'boundary'}
    z=iq[start:start+SAMPLES].astype(np.complex128);train=pulse_train(payload)
    # Known pulse centres give a carrier estimate across the complete frame.
    indices=np.flatnonzero(train>0)
    good=indices[np.abs(z[indices])>=np.quantile(np.abs(z[indices]),.25)]
    if len(good)<100:return None,{'reason':'weak_reference'}
    phase=np.unwrap(np.angle(z[good]));weight=np.abs(z[good])**2
    frequency=np.polyfit(good/FS,phase,1,w=np.sqrt(weight))[0]/(2*np.pi)
    if abs(frequency)>100000:return None,{'reason':'carrier_out_of_bounds'}
    rotation=np.exp(2j*np.pi*frequency*np.arange(SAMPLES)/FS)
    design=[]
    for lag in range(-2,3):
        column=np.zeros(SAMPLES);lo=max(0,lag);hi=min(SAMPLES,SAMPLES+lag)
        column[lo:hi]=train[lo-lag:hi-lag];design.append(column*rotation)
    design=np.stack(design+[np.ones(SAMPLES)],axis=1)
    coef=np.linalg.lstsq(design,z,rcond=None)[0]
    # Keep DC/background; remove only the reconstructed aircraft waveform.
    model=design[:,:-1]@coef[:-1];residual=z-model
    ratio=float(np.vdot(residual,residual).real/max(np.vdot(z,z).real,1e-12))
    if not np.isfinite(ratio) or ratio>.45:return None,{'reason':'poor_fit','residual_power_ratio':ratio}
    return residual.astype(np.complex64),{'frequency_hz':float(frequency),'residual_power_ratio':ratio,'reason':'fit_accepted'}


class ClassicalDecoder:
    stages=('timing','soft','matched','header','sic')
    def __init__(self,neural,budget=32,sic_budget=2,stages=None):
        self.stages=tuple(stages) if stages is not None else type(self).stages
        self.neural=neural;self.budget=budget;self.sic_budget=sic_budget
    def decode(self,path,stock=(),blocks=None):
        slice_window=getattr(self,'window',window)
        outputs={stage:[] for stage in type(self).stages};stats=Counter();timings=Counter();seen={stage:{} for stage in self.stages};begin=time.perf_counter()
        def emit(stage,sample,row,**details):
            message=row.tobytes().hex() if isinstance(row,np.ndarray) else row
            if int(message[:2],16)>>3!=17:return
            previous=seen[stage].get(message,[])
            if any(abs(sample-other)<480 for other in previous):return
            previous.append(sample);seen[stage][message]=previous
            outputs[stage].append(dict(seconds=sample/FS,sample_4msps=float(sample),message_hex=message,source=stage,research_only=True,**details))
        source=blocks if blocks is not None else self.neural.blocks(path,.05)
        for block in source:
            offset,core,iq=block[:3]
            fused=len(block)>3
            if fused:starts,scores,selected=block[3:]
            if not fused:starts,scores=self.neural.scores(iq,core,.4)
            if not fused:
                keep=(starts>=8)&(starts+SAMPLES+8<len(iq));starts=starts[keep];scores=scores[keep]
            if not len(starts):continue
            # Work in bounded chunks before allocating any full-window tensors.
            regular=[];relaxed=[]
            for lo in range(0,len(starts),128) if not fused or "header" in self.stages else ():
                ids=np.arange(lo,min(lo+128,len(starts)));x=slice_window(iq,starts[ids]);logits,confidence=logits_and_confidence(x)
                valid=(crc_batch(payloads(logits))==0)&np.all((logits[:,:5]>0)==DF17,axis=1)
                mismatch=(logits[:,:5]>0)!=DF17;count=mismatch.sum(axis=1)
                for j,index in enumerate(ids):
                    if valid[j]:continue
                    if count[j]==0:regular.append((index,float(scores[index])))
                    elif count[j]==1 and confidence[j,:5][mismatch[j]][0]<.25:relaxed.append((index,float(scores[index])))
            regular=sorted(sorted(regular,key=lambda r:(-r[1],r[0]))[:self.budget])
            relaxed=sorted(sorted(relaxed,key=lambda r:(-r[1],r[0]))[:self.budget])
            if fused:regular=[(r[0],r[1]) for r in selected]
            stats['regular_windows']+=len(regular);stats['header_windows']+=len(relaxed)
            if regular:
                positions=starts[[r[0] for r in regular]];x=slice_window(iq,positions);logits,confidence=logits_and_confidence(x)
                mark=time.process_time()
                native_dsp=fused and hasattr(self.neural,'header_ids')
                if native_dsp:
                    from .native import dsp_candidates
                    ci,cm,cr=getattr(self.neural,'dsp_candidates',dsp_candidates)(iq,positions,'timing' in self.stages,'matched' in self.stages)
                    for j,i in enumerate(ci):
                        method=int(cm[j]);shift=SHIFTS[method] if method<6 else 0
                        emit('timing' if method<6 else 'matched',offset+float(positions[i])+shift,cr[j],**({'shift_samples':shift} if method<6 else {}))
                for shift in SHIFTS if "timing" in self.stages and not native_dsp else ():
                    shifted=slice_window(iq,positions,shift);l,c=logits_and_confidence(shifted);pred=payloads(l);valid=(crc_batch(pred)==0)&((pred[:,0]>>3)==17)
                    for j in np.flatnonzero(valid):emit('timing',offset+float(positions[j])+shift,pred[j],shift_samples=shift)
                elapsed=time.process_time()-mark
                profile=getattr(getattr(self.neural,'optimized_backend',None),'last_native_dsp_cpu',None) if native_dsp else None
                if profile:
                    timings['timing']+=profile['timing'];timings['matched']+=profile['matched'];timings['shared']+=max(0.,elapsed-sum(profile.values()))
                elif native_dsp:timings['shared_timing_matched']+=elapsed
                else:timings['timing' if 'timing' in self.stages else 'shared']+=elapsed
                mark=time.process_time();fixed,counts=getattr(self.neural,'soft_decode',soft_decode)(logits,confidence) if "soft" in self.stages else ([],{});stats.update({'soft_'+k:v for k,v in counts.items()})
                for j,row,flips in fixed:emit('soft',offset+int(positions[j]),row,flipped_bits=flips)
                timings['soft' if 'soft' in self.stages else 'shared']+=time.process_time()-mark
                mark=time.process_time();l,c=matched_logits(slice_window(iq,positions,margin=4)) if 'matched' in self.stages and not native_dsp else (np.empty((0,112)),None);pred=payloads(l);valid=(crc_batch(pred)==0)&((pred[:,0]>>3)==17)
                for j in np.flatnonzero(valid):emit('matched',offset+int(positions[j]),pred[j])
                timings['matched' if 'matched' in self.stages else 'shared']+=time.process_time()-mark
            if relaxed and "header" in self.stages:
                mark=time.process_time();positions=starts[[r[0] for r in relaxed]];x=slice_window(iq,positions);l,c=logits_and_confidence(x)
                # Actual neural/header predictions and a bounded hypothesis list;
                # do not overwrite the header with the expected bit pattern.
                prediction=payloads(self.neural.session.run(None,{'iq_features':features(x)})[0]) if self.neural.session is not None else np.empty((0,14),np.uint8);valid=(crc_batch(prediction)==0)&((prediction[:,0]>>3)==17)
                for j in np.flatnonzero(valid):emit('header',offset+int(positions[j]),prediction[j],method='neural_relaxed_gate')
                fixed,counts=soft_decode(l,c,allow_header=True);stats.update({'header_'+k:v for k,v in counts.items()})
                for j,row,flips in fixed:emit('header',offset+int(positions[j]),row,method='soft_relaxed_gate',flipped_bits=flips)
                timings['header']+=time.process_time()-mark
            mark=time.process_time()
            references=[r for r in stock if offset+8<=r['seconds']*FS<offset+core-8] if 'sic' in self.stages else []
            def reference_power(r):
                position=round(r['seconds']*FS-offset)
                return float(np.mean(np.abs(iq[position:position+SAMPLES])**2))
            references=sorted(references,key=reference_power,reverse=True)[:self.sic_budget]
            for reference in references:
                position=round(reference['seconds']*FS-offset)
                residual,fit=cancel_packet(iq,position,reference['message_hex']);stats['sic_attempts']+=1
                stats['sic_fit_'+fit['reason']]+=1
                if residual is None:stats['sic_rejected_fits']+=1;continue
                lo=max(0,position-SAMPLES);hi=min(len(iq),position+2*SAMPLES)
                original=iq[lo:hi]
                raw_starts,_=self.neural.scores(original,len(original)-SAMPLES,.4)
                raw_starts=raw_starts[(raw_starts>=4)&(raw_starts+SAMPLES<len(original))][:self.budget]
                direct=[]
                if len(raw_starts):
                    raw_logits,_=logits_and_confidence(slice_window(original,raw_starts));raw_pred=payloads(raw_logits)
                    raw_valid=(crc_batch(raw_pred)==0)&((raw_pred[:,0]>>3)==17)
                    direct=[(int(raw_starts[j]),raw_pred[j].tobytes().hex()) for j in np.flatnonzero(raw_valid)]
                local=original.copy();local[position-lo:position-lo+SAMPLES]=residual
                candidates,score=self.neural.scores(local,len(local)-SAMPLES,.4)
                candidates=candidates[(candidates>=4)&(candidates+SAMPLES<len(local))]
                candidates=candidates[:self.budget]
                if len(candidates):
                    l,c=logits_and_confidence(slice_window(local,candidates));pred=payloads(l);valid=(crc_batch(pred)==0)&((pred[:,0]>>3)==17)
                    for j in np.flatnonzero(valid):
                        message=pred[j].tobytes().hex()
                        if any(message==other and abs(int(candidates[j])-t)<480 for t,other in direct):
                            stats['sic_direct_counterfactual_duplicates']+=1;continue
                        if message!=reference['message_hex']:emit('sic',offset+lo+int(candidates[j]),pred[j],cancelled_message=reference['message_hex'],fit=fit)
            timings['sic' if 'sic' in self.stages else 'shared']+=time.process_time()-mark
            # Dedupe history is bounded even for long file inputs.
            for stage in self.stages:
                seen[stage]={p:[s for s in times if s>offset-FS] for p,times in seen[stage].items() if times[-1]>offset-FS}
        return outputs,dict(wall_s=time.perf_counter()-begin,branch_seconds=dict(timings),counts=dict(stats),budget_per_50ms=self.budget,sic_budget_per_50ms=self.sic_budget)

# Exhaustive 1/2-bit *error pattern* table. Each lookup diagnoses one hard-sliced
# candidate; it is not an exhaustive search of RF timing/frequency hypotheses.
_BROAD_TABLE=None

def broad_decode(logits,confidence=None):
    """Research comparison only: correct any one/two of all 112 received bits.
    CRC-valid rows are not returned. Ambiguous syndromes are never accepted.
    Does not itself validate RF likelihood, identities, positions or frame age.
    """
    global _BROAD_TABLE
    if _BROAD_TABLE is None:
        table={}
        for length in (1,2):
            for bits in itertools.combinations(range(112),length):
                syndrome=0
                for bit in bits:syndrome^=int(BIT_SYNDROMES[bit])
                table[syndrome]=bits if syndrome not in table else None
        _BROAD_TABLE=table
    pred=payloads(logits);syndromes=crc_batch(pred);out=[]
    for i,syndrome in enumerate(syndromes):
        bits=_BROAD_TABLE.get(int(syndrome)) if syndrome else None
        if bits is None:continue
        row=pred[i].copy()
        for bit in bits:row[bit//8]^=1<<(7-bit%8)
        if row[0]>>3!=17:continue
        out.append((i,row,bits,None if confidence is None else tuple(float(confidence[i,b]) for b in bits)))
    return out
