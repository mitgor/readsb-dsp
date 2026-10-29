"""Offline feedback hypotheses. These functions never publish to live feeds."""
import ctypes as C
from pathlib import Path
import numpy as np
from .dsp import FS,crc_batch
from .classical import pulse_train
_LIB=None

def soft_feedback(iq,starts,iterations=2):
 global _LIB
 iq=np.ascontiguousarray(iq,np.complex64);starts=np.ascontiguousarray(starts,np.int64)
 if iq.ndim!=1 or starts.ndim!=1 or len(starts)>64 or type(iterations) is not int or iterations not in (1,2):raise ValueError('Invalid feedback bounds')
 if _LIB is None:
  _LIB=C.CDLL(str(Path(__file__).with_name('_soft_feedback.so')));arr=lambda t:np.ctypeslib.ndpointer(dtype=t,flags='C_CONTIGUOUS');f=_LIB.rescue_soft_feedback;f.argtypes=[arr(np.float32),C.c_int64,arr(np.int64),C.c_int64,C.c_int,arr(np.float32),arr(np.float32),arr(np.float64)];f.restype=C.c_int
 l=np.empty((len(starts),112),np.float32);c=np.empty_like(l);freq=np.empty(len(starts),np.float64)
 if _LIB.rescue_soft_feedback(iq.view(np.float32),len(iq),starts,len(starts),iterations,l,c,freq):raise ValueError('Invalid feedback RF')
 return l,c,freq

def guarded_cancel(iq,start,payload):
 """One stock-reference subtraction; disjoint bit groups check waveform fit.
 No target bits are inferred or supplied by aircraft tracks. Original is intact.
 """
 try:row=np.frombuffer(bytes.fromhex(payload),np.uint8)
 except ValueError:return None,dict(reason='invalid_reference')
 if len(row)!=14 or row[0]>>3!=17 or crc_batch(row[None])[0]!=0:return None,dict(reason='invalid_reference')
 if start<4 or start+484>len(iq):return None,dict(reason='boundary')
 z=iq[start:start+480].astype(np.complex128)
 if not np.isfinite(z).all():return None,dict(reason='nonfinite')
 train=pulse_train(payload);q=np.arange(480);bits=np.floor_divide(q-32,4);test=(bits>=0)&(bits%4==3)
 # Guard bands avoid training on taps which spill into held-out bit groups.
 excluded=np.convolve(test.astype(int),np.ones(5,int),mode='same')>0;fit=~excluded
 on=np.flatnonzero((train>0)&fit);on=on[abs(z[on])>=np.quantile(abs(z[on]),.25)]
 if len(on)<35:return None,dict(reason='weak_reference')
 phase=np.unwrap(np.angle(z[on]));w=np.abs(z[on]);slope=np.polyfit(on/FS,phase,1,w=w)[0];freq=slope/(2*np.pi)
 if abs(freq)>100000:return None,dict(reason='carrier_bounds')
 rotation=np.exp(1j*slope*q/FS);design=[]
 for lag in range(-2,3):
  col=np.zeros(480);lo=max(0,lag);hi=min(480,480+lag);col[lo:hi]=train[lo-lag:hi-lag];design.append(col*rotation)
 design=np.stack(design+[np.ones(480)],axis=1)
 coef,_,rank,singular=np.linalg.lstsq(design[fit],z[fit],rcond=None)
 if rank<6 or singular[-1]<=0 or singular[0]/singular[-1]>1e5:return None,dict(reason='ill_conditioned')
 model=design[:,:5]@coef[:5];residual=z-model
 ratio=lambda mask:float(np.vdot(residual[mask],residual[mask]).real/max(np.vdot(z[mask],z[mask]).real,1e-12))
 train_ratio=ratio(fit);test_ratio=ratio(test)
 meta=dict(reason='fit_accepted',frequency_hz=float(freq),train_ratio=train_ratio,heldout_ratio=test_ratio,training_samples=int(fit.sum()),heldout_samples=int(test.sum()))
 if train_ratio>.45 or test_ratio>.65:return None,dict(meta,reason='fit_rejected')
 result=iq.copy();result[start:start+480]=residual.astype(np.complex64)
 return result,meta
