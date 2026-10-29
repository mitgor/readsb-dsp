"""Training-only DSP views. Supervised targets remain stock-assisted labels."""
import numpy as np
from .classical import window,carrier,cancel_packet
from .dsp import crc_batch

def views(chunks,rng):
    """Mixed raw, fractional timing and preamble-derived matched I/Q views.
    Keeps the production input shape unchanged. This isn't forced bit correction.
    """
    chunks=np.asarray(chunks,np.complex64)
    out=chunks[:,8:488].copy();choice=rng.choice(3,len(chunks),p=[.5,.3,.2])
    for i in np.flatnonzero(choice==1):out[i]=window(chunks[i],np.array([8]),shift=float(rng.uniform(-.65,.65)))[0]
    ids=np.flatnonzero(choice==2)
    if len(ids):
        z=chunks[ids];_,freq=carrier(z[:,8:488])
        z=z*np.exp(-2j*np.pi*freq[:,None]*(np.arange(496)-8)[None,:]/4e6)
        offsets=np.arange(-1,3)
        shape=z[:,8+np.array([0,4,14,18])[:,None]+offsets].mean(1)
        norm=np.maximum(np.sqrt((np.abs(shape)**2).sum(1)),1e-6)
        for j,i in enumerate(ids):
            values=z[j,8+np.arange(480)[:,None]+offsets]
            out[i]=(values@shape[j].conj()/norm[j]).astype(np.complex64)
    return out,choice

def cancellation_view(iq,target_start,target_hex,context,first_sample_12mhz):
    """Remove at most one independently stock-decoded overlapping interferer.
    Refuse cancellation of the supervised target or its own aircraft.
    """
    for row in sorted(context,key=lambda r:r.get('signal_byte') or 0,reverse=True):
        payload=row['message_hex']
        if payload==target_hex or payload[2:8]==target_hex[2:8]:continue
        data=np.frombuffer(bytes.fromhex(payload),np.uint8)
        if len(data)!=14 or data[0]>>3!=17 or crc_batch(data[None])[0]!=0:continue
        start=round((row['ticks']-first_sample_12mhz)/3)
        if abs(start-target_start)>=480:continue
        residual,fit=cancel_packet(iq,start,payload)
        if residual is None:continue
        changed=iq.copy();changed[start:start+480]=residual
        chunk=changed[target_start-8:target_start+488]
        if len(chunk)==496:return chunk,{'cancelled_hex':payload,'fit':fit,'target_is_stock_assisted':True}
    return None,None
