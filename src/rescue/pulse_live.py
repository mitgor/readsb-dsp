"""Optional native pulse filter reusing the production V3 frontend."""
import hashlib,json,time
from pathlib import Path
import numpy as np
from .dsp import payloads,crc_batch
from .pulse_native import scores as native_scores

MODEL_SHA256='bd9abaa59413fda4506ffb8c66f86418a7c33bc16b6c6d0521e42e904931b4fe'

def production_model(path):
    raw=Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=MODEL_SHA256:
        raise ValueError('Pulse model integrity check failed')
    model=json.loads(raw)
    if model.get('schema')!='pulse-discriminant-v1':
        raise ValueError('Unexpected pulse model schema')
    # Load and validate the native library before accepting an enabled worker.
    native_scores(np.zeros(496,np.float32),np.empty(0,np.int64),model)
    return model

def decode_candidates(iq,starts,scores,backend,soft_decode,model,budget=64):
    """Same bounded preamble/top-score policy as the validated C replay."""
    began=time.process_time()
    safe=(starts>=10)&(starts+490<len(iq))
    starts=starts[safe];scores=scores[safe]
    if not len(starts):return [],dict(cpu_s=time.process_time()-began,windows=0)
    ids=np.argsort(-scores,kind='stable')[:budget]
    positions=starts[ids]
    logits,confidence=native_scores(backend.prepare(iq)[0],positions,model)
    predicted=payloads(logits)
    fixed,_=soft_decode(logits,confidence)
    flips={int(j):tuple(int(b) for b in bits) for j,row,bits in fixed}
    for j,row,bits in fixed:predicted[j]=row
    valid=(crc_batch(predicted)==0)&((predicted[:,0]>>3)==17)
    rows=[(int(positions[j]),predicted[j],float(scores[ids[j]]),flips.get(int(j),())) for j in np.flatnonzero(valid)]
    return rows,dict(cpu_s=time.process_time()-began,windows=len(positions),valid=len(rows))
