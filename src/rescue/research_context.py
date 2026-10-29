"""Strict prior-stock distance attribution for research. No model-derived locations."""
import math
from .telemetry import distance_bin

def prior_distance(history,icao,unix,max_age=15):
    candidates=[]
    for fix,distance,observed in history.get(icao,()):
        if fix<=unix and observed<=unix and 0<=unix-fix<=max_age and math.isfinite(distance) and distance>=0:candidates.append((fix,distance,unix-fix))
    if not candidates:return None,None
    _,distance,age=max(candidates,key=lambda r:r[0]);return distance,age

def far_selector(meta):
    """Select received addresses within one bit of a PRIOR far stock address.
    Acquisition hint only; admission must independently verify actual predicted CRC/address.
    """
    import numpy as np
    history=meta['position_history'];cache={}
    def allowed_at(offset):
        if offset in cache:return cache[offset]
        stamp=meta['unix']+offset/4e6;allowed=set()
        for addr in history:
            distance,_=prior_distance(history,addr,stamp)
            if distance is None or distance<180:continue
            value=int(addr,16);allowed.add(value)
            allowed.update(value^(1<<bit) for bit in range(24))
        cache[offset]=allowed;return allowed
    def select(offset,positions,rows):
        allowed=allowed_at(offset)
        if not allowed:return np.zeros(len(rows),bool)
        address=(rows[:,1].astype(np.uint32)<<16)|(rows[:,2].astype(np.uint32)<<8)|rows[:,3]
        return np.array([int(value) in allowed for value in address],bool)
    select.active=lambda offset:bool(allowed_at(offset))
    return select
