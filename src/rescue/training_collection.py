"""Bounded stock-label/DSP research sampling; no decoding output or SD access.

Original UC8 is authoritative. DSP descriptors are reproducible diagnostics, never
supervised labels. Unbiased segments are excluded from supervised training.
"""
import bisect,hashlib,time
from collections import Counter
import numpy as np
from scipy.signal import upfirdn
from .dsp import FIR,features,payloads,baseline,crc_batch
from .classical import logits_and_confidence,matched_logits
from .telemetry import distance_bin
RATE=2400000
VERSION='dsp-collection-v1'

def resample(raw):
    z=(np.frombuffer(raw,np.uint8).reshape(-1,2).astype(np.float32)-127.5)/128
    y=upfirdn(FIR,z,up=5,down=3,axis=0)[17:]
    return (y[:,0]+1j*y[:,1]).astype(np.complex64)

def descriptors(raw,event_sample,event_sample_4msps=None):
    iq=resample(raw);start=round(event_sample*5/3) if event_sample_4msps is None else int(event_sample_4msps)
    if start<4 or start+484>len(iq):raise ValueError('Missing waveform context')
    packet=iq[start:start+480][None];l,c=logits_and_confidence(packet)
    ml,mc=matched_logits(iq[start-4:start+484][None]);row=payloads(l)
    power=np.abs(packet[0])**2
    return {'version':VERSION,'sample_rate':4000000,'bit_confidence':c[0].round(5).tolist(),
        'energy_hard_hex':row[0].tobytes().hex(),'energy_crc':int(crc_batch(row)[0]),
        'matched_hard_hex':payloads(ml)[0].tobytes().hex(),'matched_bit_confidence':mc[0].round(5).tolist(),
        'power_mean':float(power.mean()),'power_peak':float(power.max()),
        'preamble_off_power_median':float(np.median(power[:32][np.array([i not in (0,1,4,5,14,15,18,19) for i in range(32)])])),
        'adc_rail_fraction':float(np.mean((np.frombuffer(raw,np.uint8)==0)|(np.frombuffer(raw,np.uint8)==255))),
        'confidence_is_probability':False,'label_from_dsp':False}

class DatasetCollector:
    def __init__(self,archive,seed=None):
        self.archive=archive;self.rng=np.random.default_rng(seed);self.minute=None;self.quota=Counter();self.count=Counter();self.last_probe=-float('inf');self.last_segment=-float('inf')
    def report(self):return {'version':VERSION,'counts':dict(self.count),'minute_quota':dict(self.quota),'probe_interval_s':10,'evaluation_interval_s':300,'evaluation_segment_ms':50,'label_policy':'stock-assisted only; DSP/neural/failed/background quarantined','far_threshold_nm':180}
    def collect(self,raw,epoch,first,wall,primary,frames,extras,corrections,health,distance):
        begin=time.monotonic();minute=int(wall//60)
        if minute!=self.minute:self.minute=minute;self.quota.clear()
        context=[f for f in frames if first*5<=f['ticks']<(first+len(raw)//2)*5]
        def save(event,label,budget,cap,trusted=False):
            if self.quota[budget]>=cap:return False
            sample=round((event['ticks']-first*5)/5);lo=sample-2400;hi=sample+2400
            if lo<0 or hi>len(raw)//2:return False
            target=event.get('message_hex');stamp=wall+sample/RATE;d,age=distance(target,stamp) if target else (None,None)
            snippet=raw[2*lo:2*hi]
            record={'record':'training_window','schema_version':2,'collector':VERSION,'label_provenance':label,
                'training_eligible':trusted,'target_hex':target,'sample_rate':RATE,'format':'uc8','sample_start':first+lo,
                'event_sample_in_window':2400,'epoch':epoch,'unix':wall+lo/RATE,'distance_nm':d,'position_age_s':age,
                'gain_db':health.get('gain_db'),'signal_byte':event.get('signal_byte'),'neural_source':event.get('source'),
                'preamble_score':event.get('preamble_score'),'flipped_bits':event.get('flipped_bits'),'flip_confidences':event.get('flip_confidences'),
                'sampling_stratum':budget,'hardware_continuity_verified':False,'evaluation_only':False,
                'stock_context':[{'ticks':f['ticks'],'message_hex':f['message_hex'],'signal_byte':f.get('signal_byte')} for f in context if abs(f['ticks']-event['ticks'])<12000]}
            try:record['dsp']=descriptors(snippet,2400)
            except (ValueError,IndexError,FloatingPointError):self.count['descriptor_error']+=1;return False
            if self.archive.add(record,snippet):self.quota[budget]+=1;self.count['saved_'+budget]+=1;return True
            self.count['archive_not_retained']+=1;return False
        # Dedicated far-label budget is independent of successful rescue volume.
        for f in sorted(primary,key=lambda r:r.get('signal_byte',255)):
            d,_=distance(f['message_hex'],wall+(f['ticks']-first*5)/12e6)
            far=d is not None and d>=180
            save(f,'stock_crc_assisted','stock_far' if far else 'stock_near',40 if far else 12,True)
        for r in (*extras,*corrections):
            source=r['source'];d,_=distance(r['message_hex'],wall+(r['ticks']-first*5)/12e6)
            far=d is not None and d>=180
            save(r,source+'_candidate_unverified','candidate_'+source+('_far' if far else '_near'),6 if far else 3)
        # Independent random background: not asserted to be signal-free.
        sample=int(self.rng.integers(3000,len(raw)//2-3000))
        save({'ticks':(first+sample)*5},'unlabelled_background','background',6)
        if wall-self.last_probe>=10:
            self.last_probe=wall;length=120000;lo=int(self.rng.integers(600,max(601,len(raw)//2-length-600)))//3*3
            segment=raw[2*lo:2*(lo+length)];iq=resample(segment)
            from .native import candidate_scores
            starts,scores=candidate_scores(iq,min(len(iq)-488,195000),.4)
            choices=list(self.rng.permutation(len(starts))[:64])
            for j in choices:
                local=int(starts[j]);tick=(first+lo)*5+local*3
                if any(abs(f['ticks']-tick)<=1440 for f in context):continue
                packet=iq[local:local+480][None];row=payloads(baseline(features(packet)))
                if crc_batch(row)[0]==0:continue
                # The failed slice isn't a label or proof that an aircraft exists.
                event={'ticks':tick,'preamble_score':float(scores[j]),'source':'failed_preamble'}
                if save(event,'failed_preamble_unlabelled','failed_preamble',6):break
        if wall-self.last_segment>=300:
            self.last_segment=wall;lo=int(self.rng.integers(600,len(raw)//2-120600))//3*3;length=120000
            record={'record':'evaluation_segment','schema_version':2,'collector':VERSION,'evaluation_only':True,'training_eligible':False,
                'sample_rate':RATE,'format':'uc8','epoch':epoch,'sample_start':first+lo,'unix':wall+lo/RATE,'sample_count':length,
                'gain_db':health.get('gain_db'),'selection':'uniform random time within processed stock-aligned windows, independent of rescue success',
                'stock_context':[{'ticks':f['ticks'],'message_hex':f['message_hex'],'signal_byte':f.get('signal_byte')} for f in frames if (first+lo)*5-360000000<=f['ticks']<(first+lo+length)*5]}
            if self.archive.add(record,raw[2*lo:2*(lo+length)]):self.count['saved_evaluation_segment']+=1
        self.count['calls']+=1;self.count['wall_s']+=time.monotonic()-begin
