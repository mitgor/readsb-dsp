"""Offline single-source pulse-tail retry; no reference payload or carrier search."""
import numpy as np
from .dsp import PREAMBLE

def waveform(bits):
 return np.r_[PREAMBLE,np.stack((bits,bits,~bits,~bits),axis=1).ravel()].astype(float)

def decode(z,frequency,bits,iterations=2):
 z=np.asarray(z,np.complex128);bits=np.asarray(bits,bool).copy()
 if z.shape!=(480,) or bits.shape!=(112,) or not np.isfinite(z).all() or not np.isfinite(frequency) or abs(frequency)>120000 or iterations not in (1,2):raise ValueError('Invalid bounded pulse-tail inputs')
 y=z*np.exp(-2j*np.pi*frequency*np.arange(480)/4e6);taps=np.array([-1,0,1]);logits=np.empty(112)
 for _ in range(iterations):
  w=waveform(bits);a=np.zeros((480,4),np.complex128);a[:,3]=np.exp(-2j*np.pi*frequency*np.arange(480)/4e6)
  for k,lag in enumerate(taps):
   lo=max(0,lag);hi=min(480,480+lag);a[lo:hi,k]=w[lo-lag:hi-lag]
  gram=a.conj().T@a;reg=.001*max(float(np.trace(gram).real)/4,1e-9);h=np.linalg.solve(gram+reg*np.eye(4),a.conj().T@y);res=y-a@h
  for b in range(112):
   q=32+4*b;delta=np.zeros(480)
   delta[q:q+2]=1;delta[q+2:q+4]=-1;wave=np.zeros(480,dtype=complex)
   for k,lag in enumerate(taps):
    lo=max(0,lag);hi=min(480,480+lag);wave[lo:hi]+=h[k]*delta[lo-lag:hi-lag]
   # Simultaneous decisions with all other bits held fixed; do not consult CRC.
   residual=res+(wave if bits[b] else 0);logits[b]=2*np.vdot(wave,residual).real-np.vdot(wave,wave).real
  bits=logits>0
 return logits

_LIB=None
def native(iq,starts,frequency,bits):
 import ctypes as C
 from pathlib import Path
 global _LIB
 iq=np.ascontiguousarray(iq,np.complex64);starts=np.ascontiguousarray(starts,np.int64);frequency=np.ascontiguousarray(frequency,np.float64);bits=np.ascontiguousarray(bits,np.uint8)
 n=len(starts)
 if iq.ndim!=1 or starts.ndim!=1 or n>8 or frequency.shape!=(n,) or bits.shape!=(n,112) or np.any(bits>1) or not np.isfinite(frequency).all() or np.any(abs(frequency)>120000) or np.any(starts<0) or np.any(starts+480>len(iq)):raise ValueError('Invalid native retry bounds')
 if _LIB is None:
  _LIB=C.CDLL(str(Path(__file__).with_name('_pulse_tail_research.so')));arr=lambda t:np.ctypeslib.ndpointer(dtype=t,flags='C_CONTIGUOUS');_LIB.rescue_pulse_tail.argtypes=[arr(np.float32),C.c_int64,arr(np.int64),arr(np.float64),arr(np.uint8),C.c_int,arr(np.float64)];_LIB.rescue_pulse_tail.restype=C.c_int
 logits=np.empty((n,112),np.float64)
 if n and _LIB.rescue_pulse_tail(iq.view(np.float32),len(iq),starts,frequency,bits,n,logits):raise ValueError('Native pulse-tail retry failed')
 return logits

def retry_from_cache(iq,offset,cached,baseline):
 from .dsp import payloads,crc_batch
 candidates=[]
 for starts,out in cached:
  for j in np.flatnonzero(out[2].astype(bool)&~out[7]):
   s=int(starts[j])
   if not np.isfinite(out[3][j]) or abs(out[3][j])>120000:continue
   if any(abs(offset+s-r['sample_4msps'])<=1 for r in baseline if r['source']!='broad_crc'):continue
   candidates.append((int(out[4][j]),s,float(out[3][j]),out[0][j]>0))
 chosen=[]
 for r in sorted(candidates,key=lambda r:(-r[0],r[1])):
  if all(abs(r[1]-q[1])>2 for q in chosen):chosen.append(r)
  if len(chosen)==8:break
 if not chosen:return [],dict(windows=0)
 starts=np.array([r[1] for r in chosen],np.int64);freq=np.array([r[2] for r in chosen]);bits=np.stack([r[3] for r in chosen]);logits=native(iq,starts,freq,bits);rows=payloads(logits);valid=(crc_batch(rows)==0)&(rows[:,0]>>3==17)
 return [dict(sample_4msps=offset+int(starts[j]),seconds=(offset+int(starts[j]))/4e6,message_hex=rows[j].tobytes().hex(),source='coherent',research_method='cached_carrier_pulse_tail',raw_crc_valid=True,training_eligible=False) for j in np.flatnonzero(valid)],dict(windows=len(chosen))

def observed_block(engine,offset,core,iq):
 """Observe existing fits in isolated replay; never attach this to live workers."""
 from unittest.mock import patch
 from . import sequence_live,coherent_pair
 cache=[];ordinary=sequence_live.native_windows;pair=coherent_pair.pair_windows
 def remember(function):
  def wrapped(z,starts):
   result=function(z,starts)
   if z is iq:cache.append((starts.copy(),result))
   return result
  return wrapped
 with patch.object(sequence_live,'native_windows',remember(ordinary)),patch.object(coherent_pair,'pair_windows',remember(pair)):
  rows,_=engine.block(offset,core,iq,[])
 return rows,cache
