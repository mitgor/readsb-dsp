"""Offline-only cached-carrier joint retry. No receiver/feeder integration.

The frozen pulse-tail ABI does not expose fitted taps. Reuse the existing saved
nine-tap pulse template; fit only two complex source gains and DC in C. Never
claim to reuse per-packet pulse-tail coefficients that are not available.
"""
import ctypes as C
from pathlib import Path
from unittest.mock import patch
import numpy as np
from . import pulse_tail_research as pt
from .dsp import payloads,crc_batch
_LIB=None

def native(iq,starts,frequency,shape,bits,fixed):
 global _LIB
 raw_starts=np.asarray(starts)
 if raw_starts.shape!=(2,) or raw_starts.dtype.kind not in 'iu' or np.any(raw_starts<0) or np.any(raw_starts>1024):raise ValueError('Invalid start range')
 iq=np.ascontiguousarray(iq,np.complex64);starts=np.ascontiguousarray(starts,np.int32);frequency=np.ascontiguousarray(frequency,np.float64);shape=np.ascontiguousarray(shape,np.complex128);bits=np.ascontiguousarray(bits,np.uint8);fixed=np.ascontiguousarray(fixed,np.uint8)
 if iq.ndim!=1 or not 500<=len(iq)<=1024 or starts.shape!=(2,) or starts[0]<4 or not 16<=starts[1]-starts[0]<=400 or starts[1]+484>len(iq) or frequency.shape!=(2,) or not np.isfinite(frequency).all() or np.any(abs(frequency)>120000) or shape.shape!=(9,) or not np.isfinite(shape).all() or bits.shape!=(2,112) or np.any(bits>1) or fixed.shape!=(2,) or np.any(fixed>1):raise ValueError('Invalid cheap joint inputs')
 if _LIB is None:
  _LIB=C.CDLL(str(Path(__file__).with_name('_cheap_joint.so')));arr=lambda t:np.ctypeslib.ndpointer(dtype=t,flags='C_CONTIGUOUS');f=_LIB.rescue_cheap_joint;f.argtypes=[arr(np.float32),C.c_int,arr(np.int32),arr(np.float64),arr(np.float64),arr(np.uint8),arr(np.uint8),arr(np.uint8),arr(np.float64)];f.restype=C.c_int
 result=np.empty((2,112),np.uint8);quality=np.empty(4,np.float64);code=_LIB.rescue_cheap_joint(iq.view(np.float32),len(iq),starts,frequency,shape.view(np.float64),bits,fixed,result,quality)
 if code<0:raise ValueError('Native cheap joint rejected bounds/fit')
 return result,bool(code),dict(train_residual_ratio=float(quality[0]),sample_group_residual_ratio=float(quality[1]),weaker_modeled_power_ratio=float(quality[2]),column_correlation=float(quality[3]))

def baseline_and_tail(engine,offset,core,iq):
 base,cache=pt.observed_block(engine,offset,core,iq);tail_cache=[];original=pt.native
 def remember(z,starts,freq,bits):
  out=original(z,starts,freq,bits);tail_cache.append((starts.copy(),freq.copy(),out));return out
 with patch.object(pt,'native',remember):tail,work=pt.retry_from_cache(iq,offset,cache,base)
 return base,tail,cache,tail_cache,work

def retry(iq,offset,cache,tail_cache,baseline,shape):
 candidates=[]
 for starts,out in cache:
  for j in np.flatnonzero(out[2]):
   s=int(starts[j]);f=float(out[3][j])
   if not np.isfinite(f) or abs(f)>120000 or s<4 or s+484>len(iq):continue
   valid=bool(out[7][j])
   candidates.append(dict(start=s,frequency=f,row=out[5][j] if valid else None,logits=out[0][j],fixed=valid,inliers=int(out[4][j])))
 unique=[];blocked=set()
 for r in sorted(candidates,key=lambda r:(-int(r['fixed']),-r['inliers'],r['start'])):
  if r['start'] not in blocked:unique.append(r);blocked.update(range(r['start']-2,r['start']+3))
 refined={}
 for starts,freq,logits in tail_cache:
  rows=payloads(logits);valid=(crc_batch(rows)==0)&(rows[:,0]>>3==17)
  for j,(s,f,l) in enumerate(zip(starts,freq,logits)):refined[int(s)]=(float(f),l,rows[j] if valid[j] else None)
 for r in unique:
  if not r['fixed'] and r['start'] in refined:
   f,l,row=refined[r['start']];r['frequency']=f;r['logits']=l;r['row']=row;r['fixed']=row is not None
 unique.sort(key=lambda r:r['start']);best=None;pair=None;hypotheses=0
 for i,a in enumerate(unique):
  for b in unique[i+1:]:
   delay=b['start']-a['start']
   if delay>400:break
   if delay<16 or (a['fixed'] and b['fixed']):continue
   # Two existing tracked preamble hypotheses; not proof of two real aircraft.
   hypotheses+=1;rank=(int(a['fixed'] or b['fixed']),min(a['inliers'],b['inliers']),a['inliers']+b['inliers'],-delay,-a['start'])
   if best is None or rank>best:best=rank;pair=(a,b)
 if pair is None:return [],dict(eligible_pairs=0,pairs=0,fit_accepted=0)
 a,b=pair
 for r in pair:r['bits']=np.unpackbits(r['row']) if r['row'] is not None else (r['logits']>0).astype(np.uint8)
 lo=a['start']-4;hi=b['start']+484;starts=np.array([a['start']-lo,b['start']-lo]);bits,accepted,quality=native(iq[lo:hi],starts,np.array([a['frequency'],b['frequency']]),shape,np.stack([a['bits'],b['bits']]),np.array([a['fixed'],b['fixed']],np.uint8));rows=np.packbits(bits,axis=1);valid=(crc_batch(rows)==0)&(rows[:,0]>>3==17);events=[]
 if accepted:
  for j,r in enumerate(pair):
   if not valid[j] or r['fixed']:continue
   events.append(dict(sample_4msps=float(offset+r['start']),seconds=(offset+r['start'])/4e6,message_hex=rows[j].tobytes().hex(),source='coherent',research_method='cheap_fixed_carrier_joint',raw_crc_valid=True,training_eligible=False,fit=quality))
 return events,dict(eligible_pairs=hypotheses,pairs=1,fit_accepted=int(accepted),raw_valid=int(valid.sum()) if accepted else 0)
