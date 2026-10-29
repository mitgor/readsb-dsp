#!/usr/bin/env python3
"""Research merge validation from previous pinned readsb 3.16.17 replay. No forwarding."""
import argparse,bisect,concurrent.futures,json,math,os,re,subprocess,sys,time
from collections import defaultdict,Counter
from pathlib import Path
from .dsp import crc_batch
import numpy as np
def crc(data):
    return int(crc_batch(np.frombuffer(bytes(data),dtype=np.uint8)[None,:])[0])

TOLERANCE=4e-6
# Pinned readsb 3.16.17 ifile path prefixes 326 history samples at 2.4 MS/s.
READSB_HISTORY_SECONDS=326/2400000

def parse_readsb(text):
    out=[]
    for ticks,payload in re.findall(r'@([0-9A-Fa-f]{12})([0-9A-Fa-f]{14}(?:[0-9A-Fa-f]{14})?);',text):
        # Account for end-of-bit-56 timing AND the pinned ifile history prefix.
        # Verified from readsb.c trailing_samples, sdr_ifile.c and demod_2400.c.
        out.append({'seconds':int(ticks,16)/12e6-64e-6-READSB_HISTORY_SECONDS,'message_hex':payload.lower(),'source':'readsb','receiver_ticks_12mhz':int(ticks,16)})
    return sorted(out,key=lambda x:x['seconds'])

def df17(payload):
    try: b=bytes.fromhex(payload)
    except (ValueError,TypeError): return False
    return len(b)==14 and b[0]>>3==17 and crc(b)==0

def nearby(times,t,tolerance=TOLERANCE):
    i=bisect.bisect_left(times,t-tolerance)
    return i<len(times) and times[i]<=t+tolerance

def merge(primary, neural):
    """Keep EVERY primary event. Add only nonduplicate provisional DF17 events.
    Timestamp values must share one capture/sample clock. Never use arrival time.
    """
    payload_times=defaultdict(list);icao_events=defaultdict(list)
    for r in sorted(primary,key=lambda x:x['seconds']):
        payload_times[r['message_hex']].append(r['seconds'])
        if df17(r['message_hex']): icao_events[r['message_hex'][2:8]].append((r['seconds'],r['message_hex']))
    icao_times={h:[t for t,_ in events] for h,events in icao_events.items()}
    merged=[dict(r) for r in primary];added=[];rejected=[];counts=Counter()
    for raw in sorted(neural,key=lambda x:x['seconds']):
        r=dict(raw);p=r.get('message_hex','').lower();t=r['seconds'];reason=None
        if not math.isfinite(t) or t<0 or not df17(p): reason='invalid_frame_or_time'
        elif nearby(payload_times[p],t): reason='duplicate'
        else:
            h=p[2:8];times=icao_times.get(h,[])
            # Require a CRC-valid primary sighting in the preceding 30 seconds.
            i=bisect.bisect_right(times,t)
            if not i or t-times[i-1]>30: reason='no_recent_primary_icao'
            else:
                start=bisect.bisect_left(times,t-TOLERANCE)
                end=bisect.bisect_right(times,t+TOLERANCE)
                if any(other!=p for _,other in icao_events[h][start:end]): reason='conflicts_with_primary'
        if reason:
            counts[reason]+=1;rejected.append({**r,'reason':reason});continue
        extra={'seconds':t,'message_hex':p,'source':r.get('source','neural'),'validation':'crc_and_recent_primary_icao','provisional':True,'research_only':True}
        merged.append(extra);added.append(extra);bisect.insort(payload_times[p],t);counts['added_provisional']+=1
    merged.sort(key=lambda x:(x['seconds'],x['source']))
    return merged,added,rejected,dict(counts)

def alignment(primary,neural):
    idx=defaultdict(list)
    for r in primary: idx[r['message_hex']].append(r['seconds'])
    errors=[]
    for r in neural:
        ts=idx.get(r['message_hex'],[])
        if ts:
            d=min(abs(t-r['seconds']) for t in ts)
            if d<.001: errors.append(d)
    errors.sort()
    median=errors[len(errors)//2] if errors else None
    return {'matches':len(errors),'median_abs_error_us':None if median is None else median*1e6,'verified':len(errors)>=20 and median<=2e-6}
