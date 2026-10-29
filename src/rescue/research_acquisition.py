"""Offline-only bounded acquisition/coherent/joint experiments; no live I/O.

These are engineering prototypes, not reproductions of the cited papers.
CRC is checked only AFTER waveform decisions; it never steers phase or joint fits.
No address/position information enters signal processing.
"""
import time
from collections import Counter
import numpy as np
from scipy.ndimage import uniform_filter1d
from scipy.signal import find_peaks
from .dsp import FS, SAMPLES, PREAMBLE, payloads, crc_batch
from .classical import carrier, logits_and_confidence, pulse_train, soft_decode
from .native import iq_blocks, candidate_scores, header_ids, energy_candidates, dsp_candidates

STAGES = ('cfar', 'coherent', 'joint')


def cfar_candidates(iq, core, budget=16):
    """Robust local-background detector; empirical threshold, not calibrated Pfa.

    Clip reference power to limit masking by strong neighbours, then compare the
    four pulse slots against the preamble quiet slots and local background.
    This is a CFAR-style prototype; filtered RF violates IID noise assumptions.
    """
    p = (iq.real * iq.real + iq.imag * iq.imag).astype(np.float32)
    floor = max(float(np.median(p)), 1e-7)
    background = uniform_filter1d(np.minimum(p, 8 * floor), size=257, mode='nearest')
    n = len(p) - 31
    on = sum(p[k:k+n] for k in np.flatnonzero(PREAMBLE)) / 8
    total = np.convolve(p, np.ones(32, np.float32), mode='valid')
    off = (total - 8 * on) / 24
    statistic = (on - off) / np.maximum(background[:n], 1e-7)
    peaks, _ = find_peaks(statistic, height=1.5, distance=3)
    peaks = peaks[(peaks >= 8) & (peaks < core) & (peaks + SAMPLES + 8 < len(iq))]
    if len(peaks):
        peaks = peaks[header_ids(iq, peaks)]
        # Bound expensive decoding, not merely the number of emitted packets.
        peaks = peaks[np.argsort(-statistic[peaks], kind='stable')[:budget]]
    return peaks, statistic[peaks]


def coherent_logits(windows):
    """Decision-directed residual CFO and coherent two-chip pulse comparison.

    Seed from preamble CFO. Use only reliable energy decisions to fit residual
    phase across the full packet, with a robust second fit. No CRC feedback.
    """
    if not len(windows):
        return np.empty((0,112)), np.empty((0,112)), []
    rotated, frequency = carrier(windows)
    hard, reliability = logits_and_confidence(windows)
    output=[]; confidence=[]; details=[]
    timebase=np.arange(SAMPLES)/FS
    for z, l, c, coarse in zip(rotated, hard, reliability, frequency):
        positions=32+4*np.arange(112)+np.where(l>0,0,2)
        values=(z[positions]+z[positions+1])/2
        good=(c>=.5) & (np.abs(values)>=np.quantile(np.abs(values),.35))
        if good.sum()<24:
            output.append(l);confidence.append(c);details.append({'tracked':False});continue
        t=(positions[good]+.5)/FS
        phase=np.unwrap(np.angle(values[good]))
        weights=np.minimum(np.abs(values[good]),np.median(np.abs(values[good]))*2)
        fit=np.polyfit(t,phase,1,w=weights)
        residual=np.angle(np.exp(1j*(phase-np.polyval(fit,t))))
        keep=np.abs(residual)<.8
        if keep.sum()>=24:fit=np.polyfit(t[keep],phase[keep],1,w=weights[keep])
        if not np.isfinite(fit).all() or abs(fit[0]/(2*np.pi))>30000:
            output.append(l);confidence.append(c);details.append({'tracked':False});continue
        tracked=z*np.exp(-1j*np.polyval(fit,timebase))
        # Learn a two-sample complex pulse template from reliable payload pulses.
        shape=np.mean(tracked[positions[good,None]+np.arange(2)[None,:]],axis=0)
        chips=tracked[32:].reshape(112,4)
        left=np.real(chips[:,:2]@shape.conj());right=np.real(chips[:,2:]@shape.conj())
        decision=left-right
        output.append(decision)
        confidence.append(np.abs(decision)/(np.abs(left)+np.abs(right)+1e-9))
        details.append({'tracked':True,'frequency_hz':float(coarse+fit[0]/(2*np.pi)),
                        'phase_inliers':int(keep.sum())})
    return np.asarray(output),np.asarray(confidence),details


def joint_decode(iq, starts, iterations=5):
    """Two-source alternating least-squares/PPM likelihood decisions.

    Both initial bit streams come from RF hard decisions, never known payloads.
    Each update compares complex pulse likelihoods after removing the other
    estimated source. Equal-energy PPM options give a simple real correlation.
    Rectangular pulse model is deliberately small; bandlimited RF may not fit it.
    """
    starts=np.asarray(starts,dtype=int)
    if len(starts)!=2 or starts[1]-starts[0]<4 or starts[1]-starts[0]>=SAMPLES:
        return [], {'reason':'not_overlapping'}
    lo=int(starts[0]);hi=int(starts[1]+SAMPLES)
    if lo<0 or hi>len(iq):return [], {'reason':'boundary'}
    windows=iq[starts[:,None]+np.arange(SAMPLES)[None,:]]
    _,freq=carrier(windows);freq=freq.astype(float)
    logits,_=logits_and_confidence(windows);rows=payloads(logits)
    positions=starts-lo
    rotation=[np.exp(2j*np.pi*f*np.arange(SAMPLES)/FS) for f in freq]
    z=iq[lo:hi].astype(np.complex128)
    def columns():
        result=[]
        for pos,row,rot in zip(positions,rows,rotation):
            col=np.zeros(len(z),np.complex128)
            col[pos:pos+SAMPLES]=pulse_train(row.tobytes().hex())*rot
            result.append(col)
        return np.stack(result+[np.ones(len(z))],axis=1)
    for _ in range(iterations):
        design=columns();coef=np.linalg.lstsq(design,z,rcond=None)[0]
        for source in range(2):
            other=1-source;pos=positions[source]
            residual=(z-design[:,other]*coef[other]-coef[2])[pos:pos+SAMPLES]
            # Refine each source's residual carrier from its current pulse
            # decisions after removing the other fitted source. No CRC feedback.
            bits=np.unpackbits(rows[source])
            on=32+4*np.arange(112)+np.where(bits,0,2)
            v=residual*rotation[source].conj()
            phasors=(v[on]+v[on+1])/2
            keep=np.abs(phasors)>=np.quantile(np.abs(phasors),.4)
            slope=np.polyfit((on[keep]+.5)/FS,np.unwrap(np.angle(phasors[keep])),1,
                             w=np.abs(phasors[keep]))[0]/(2*np.pi)
            if np.isfinite(slope) and abs(slope)<=15000 and abs(freq[source]+slope)<=100000:
                freq[source]+=slope
                rotation[source]=np.exp(2j*np.pi*freq[source]*np.arange(SAMPLES)/FS)
                template=pulse_train(rows[source].tobytes().hex())*rotation[source]
                coef[source]=np.vdot(template,residual)/max(np.vdot(template,template).real,1e-12)
            demod=residual*rotation[source].conj()*coef[source].conjugate()
            chips=np.real(demod[32:]).reshape(112,4)
            rows[source]=payloads((chips[:,:2].sum(1)-chips[:,2:].sum(1))[None,:])[0]
        # Even unchanged bits may need additional carrier refinement.
    design=columns();coef=np.linalg.lstsq(design,z,rcond=None)[0]
    error=z-design@coef
    ratio=float(np.vdot(error,error).real/max(np.vdot(z,z).real,1e-12))
    valid=(crc_batch(rows)==0)&((rows[:,0]>>3)==17)
    fit={'reason':'fit','residual_ratio':ratio,'iterations':iterations,'frequency_hz':list(map(float,freq))}
    if not np.isfinite(ratio) or ratio>.85:return [],fit
    return [(int(starts[j]),rows[j]) for j in np.flatnonzero(valid)],fit


class AcquisitionResearchDecoder:
    """One pass with explicit stage budgets; production never imports this class."""
    def __init__(self, stages=STAGES, cfar_budget=16, coherent_budget=24, joint_budget=4):
        if not set(stages)<=set(STAGES):raise ValueError('Unknown research stage')
        self.stages=tuple(stages);self.cfar_budget=cfar_budget
        self.coherent_budget=coherent_budget;self.joint_budget=joint_budget

    def decode(self,path,blocks=None):
        outputs={k:[] for k in STAGES};counts=Counter();cpu=Counter();wall=time.perf_counter();begin=time.process_time()
        def emit(stage,start,row,**detail):
            outputs[stage].append(dict(sample_4msps=float(start),seconds=float(start)/FS,
                message_hex=row.tobytes().hex(),source='matched',experiment_source=stage,
                research_only=True,**detail))
        for offset,core,iq in (iq_blocks(path,.05) if blocks is None else blocks):
            mark=time.process_time()
            normal,scores=candidate_scores(iq,core,.3)
            safe=(normal>=8)&(normal+SAMPLES+8<len(iq));normal=normal[safe];scores=scores[safe]
            if len(normal):
                ids=header_ids(iq,normal);normal=normal[ids];scores=scores[ids]
            acquired,significance=cfar_candidates(iq,core,self.cfar_budget) if 'cfar' in self.stages else (np.array([],int),[])
            # Keep acquisition-only windows distinct from ordinary >=.4 peaks.
            existing=normal[scores>=.4]
            if len(existing) and len(acquired):
                keep=np.min(np.abs(acquired[:,None]-existing[None,:]),axis=1)>1
                acquired=acquired[keep]
            cpu['acquisition_s']+=time.process_time()-mark
            counts['cfar_windows']+=len(acquired);counts['ordinary_windows']+=len(normal)
            if len(acquired) and 'cfar' in self.stages:
                mark=time.process_time();rows,valid=energy_candidates(iq,acquired)
                for j in np.flatnonzero(valid):emit('cfar',offset+acquired[j],rows[j],method='energy')
                pending=acquired[~valid]
                if len(pending):
                    ids,methods,rows=dsp_candidates(iq,pending,True,True)
                    from .classical import SHIFTS
                    for j,i in enumerate(ids):
                        method=int(methods[j]);shift=SHIFTS[method] if method<6 else 0
                        emit('cfar',offset+pending[i]+shift,rows[j],method='timing' if method<6 else 'matched')
                    l,c=logits_and_confidence(iq[pending[:,None]+np.arange(SAMPLES)[None,:]])
                    for j,row,flips in soft_decode(l,c)[0]:emit('cfar',offset+pending[j],row,method='soft',flipped_bits=flips)
                cpu['cfar_decoding_s']+=time.process_time()-mark
            mark=time.process_time()
            pool=np.unique(np.r_[normal,acquired]);poolrows,valid=energy_candidates(iq,pool)
            pending=pool[~valid]
            # Rank by preamble contrast without identity/range knowledge.
            if len(pending):
                p=np.abs(iq[pending[:,None]+np.arange(32)[None,:]])**2
                rank=p[:,PREAMBLE.astype(bool)].mean(1)/(p[:,~PREAMBLE.astype(bool)].mean(1)+1e-8)
                pending=pending[np.argsort(-rank,kind='stable')[:self.coherent_budget]]
            cpu['screening_s']+=time.process_time()-mark
            if len(pending) and 'coherent' in self.stages:
                mark=time.process_time()
                l,c,detail=coherent_logits(iq[pending[:,None]+np.arange(SAMPLES)[None,:]])
                rows=payloads(l);valid=(crc_batch(rows)==0)&((rows[:,0]>>3)==17)
                for j in np.flatnonzero(valid):emit('coherent',offset+pending[j],rows[j],fit=detail[j])
                # Same limited soft repair as current decoder, never ICAO edits.
                for j,row,flips in soft_decode(l,c)[0]:emit('coherent',offset+pending[j],row,fit=detail[j],flipped_bits=flips)
                counts['coherent_windows']+=len(pending);counts['coherent_tracked']+=sum(d['tracked'] for d in detail)
                cpu['coherent_s']+=time.process_time()-mark
            if len(pending)>1 and 'joint' in self.stages:
                mark=time.process_time();pairs=[]
                for i,a in enumerate(pending):
                    for b in pending[i+1:]:
                        if 4<=abs(int(a)-int(b))<SAMPLES:pairs.append(tuple(sorted((int(a),int(b)))))
                for pair in pairs[:self.joint_budget]:
                    rows,fit=joint_decode(iq,pair);counts['joint_pairs']+=1
                    for pos,row in rows:emit('joint',offset+pos,row,fit=fit,paired_start=float(offset+pair[1 if pos==pair[0] else 0]))
                cpu['joint_s']+=time.process_time()-mark
        for key,events in outputs.items():
            seen={};keep=[]
            for row in sorted(events,key=lambda r:r['seconds']):
                p=row['message_hex'];t=row['seconds']
                if t-seen.get(p,-1e9)<=120e-6:continue
                seen[p]=t;keep.append(row)
            outputs[key]=keep
        return outputs,dict(cpu_s=time.process_time()-begin,wall_s=time.perf_counter()-wall,
            branch_cpu_s=dict(cpu),counts=dict(counts),budgets_per_50ms=dict(cfar=self.cfar_budget,coherent=self.coherent_budget,joint=self.joint_budget))
