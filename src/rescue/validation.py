"""Validation helpers: original Beast stream, semantic fields and timed comparisons."""
import bisect,math
from functools import lru_cache
from collections import defaultdict
import numpy as np
import pyModeS
from .merge import TOLERANCE,READSB_HISTORY_SECONDS,nearby,df17

def beast_frames(data):
    """Decode escaped Beast records, retaining the receiver's 48-bit clock.

    Unsupported control records are skipped by resynchronizing at the next
    nonescaped marker. No corrected/new messages are manufactured here.
    """
    out=[];i=0;lengths={0x31:9,0x32:14,0x33:21}
    while i+1<len(data):
        if data[i]!=0x1a:i+=1;continue
        kind=data[i+1]
        if kind not in lengths:i+=2;continue
        j=i+2;body=bytearray();valid=True
        while len(body)<lengths[kind] and j<len(data):
            b=data[j]
            if b==0x1a:
                if j+1>=len(data):valid=False;break
                if data[j+1]!=0x1a:valid=False;break
                j+=1
            body.append(b);j+=1
        if valid and len(body)==lengths[kind]:
            out.append({'ticks_12mhz':int.from_bytes(body[:6],'big'),'message_hex':body[7:].hex(),'signal_byte':body[6],'kind':kind})
            i=j
        else:i=max(i+1,j)
    return out

def live_for_clip(frames,start_tick,duration):
    out=[]
    for r in frames:
        ticks=(r['ticks_12mhz']-start_tick)%(1<<48)
        t=ticks/12e6-64e-6-READSB_HISTORY_SECONDS
        if 0<=t<duration:out.append({'seconds':t,'message_hex':r['message_hex'],'source':'readsb'})
    return sorted(out,key=lambda r:r['seconds'])

def index_events(events):
    result=defaultdict(list)
    for r in sorted(events,key=lambda r:r['seconds']):result[r['message_hex']].append(r['seconds'])
    return result

def present(index,r,tolerance=TOLERANCE):return nearby(index.get(r['message_hex'],[]),r['seconds'],tolerance)

@lru_cache(maxsize=200000)
def fields(payload):
    try:
        decoded=pyModeS.decode(payload)
        # normalize third-party library scalar types for JSON serialization
        return {k:v.item() if isinstance(v,np.generic) else v for k,v in decoded.items()}
    except Exception as e:return {'decode_error':str(e)}

def category(tc):
    if tc in range(1,5):return 'identification'
    if tc in range(5,9):return 'surface_position'
    if tc in range(9,19):return 'barometric_position'
    if tc==19:return 'velocity'
    if tc in range(20,23):return 'gnss_position'
    return {28:'status',29:'target_state',31:'operational_status'}.get(tc,'other')

def semantic_support(event,primary):
    decoded=fields(event['message_hex']);icao=event['message_hex'][2:8]
    relevant=[]
    for r in primary:
        if r['message_hex'][2:8]==icao and abs(r['seconds']-event['seconds'])<=10 and df17(r['message_hex']):
            d=fields(r['message_hex'])
            if category(d.get('typecode'))==category(decoded.get('typecode')):relevant.append((r,d))
    relevant.sort(key=lambda pair:abs(pair[0]['seconds']-event['seconds']))
    result={'decoded':decoded,'category':category(decoded.get('typecode')),'nearby_stock_same_category':len(relevant),'support':[]}
    if not relevant:return result
    other,known=relevant[0];dt=abs(other['seconds']-event['seconds'])
    result['nearest_stock']={'delta_seconds':other['seconds']-event['seconds'],'message_hex':other['message_hex'],'decoded':known}
    if decoded.get('callsign') and decoded.get('callsign')==known.get('callsign'):result['support'].append('callsign_matches_stock')
    if decoded.get('altitude') is not None and known.get('altitude') is not None:
        delta=abs(decoded['altitude']-known['altitude']);result['altitude_delta_ft']=delta
        if delta<=max(200,150*dt):result['support'].append('altitude_consistent_with_nearby_stock')
    if decoded.get('groundspeed') is not None and known.get('groundspeed') is not None:
        delta=abs(decoded['groundspeed']-known['groundspeed']);result['groundspeed_delta_knots']=delta
        if delta<=max(20,5*dt):result['support'].append('speed_consistent_with_nearby_stock')
    if decoded.get('track') is not None and known.get('track') is not None:
        delta=abs((decoded['track']-known['track']+180)%360-180);result['track_delta_degrees']=delta
        if delta<=max(10,3*dt):result['support'].append('track_consistent_with_nearby_stock')
    # Decode one opposite-format stock CPR packet together with the candidate.
    # This is independent track consistency evidence, not ground truth for RF.
    if decoded.get('cpr_format') is not None:
        opposite=[(r,d) for r,d in relevant if d.get('cpr_format') in (0,1) and d['cpr_format']!=decoded['cpr_format']]
        if opposite:
            r,d=opposite[0]
            try:
                pair=pyModeS.decode([event['message_hex'],r['message_hex']],timestamps=[event['seconds'],r['seconds']])
                result['cpr_pair_decode']=pair
            except Exception as e:result['cpr_pair_error']=str(e)
    result['support_is_independent_rf_ground_truth']=False
    return result
