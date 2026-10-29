"""Offline alternating two-source nuisance estimation; no external packet bits."""
import ctypes as C
from pathlib import Path
import numpy as np
from .dsp import PREAMBLE
from .coherent_fast import native_windows
from .overlap_research import checked
_LIB=None

def library():
 global _LIB
 if _LIB is None:
  _LIB=C.CDLL(str(Path(__file__).with_name('_joint_channel.so')));arr=lambda t:np.ctypeslib.ndpointer(dtype=t,flags='C_CONTIGUOUS');_LIB.joint_channel_decode.argtypes=[arr(np.float32),C.c_int,arr(np.int32),arr(np.float32),arr(np.float32),arr(np.uint8),C.c_int,arr(np.float32)];_LIB.joint_channel_decode.restype=C.c_int
 return _LIB

def waveform(bits):
 bits=np.asarray(bits,bool);out=np.zeros(480);out[:32]=PREAMBLE;out[32:]=np.stack((bits,bits,~bits,~bits),axis=-1).ravel();return out

def columns(bits,starts,freq,n,taps=3):
 out=[];t=np.arange(n)
 for b,s,f in zip(bits,starts,freq):
  w=waveform(b);full=np.zeros(n);full[s:s+480]=w;rotation=np.exp(2j*np.pi*f*(t-s)/4e6)
  for lag in range(-1,2) if taps==3 else (0,):
   col=np.zeros(n);lo=max(0,lag);hi=min(n,n+lag);col[lo:hi]=full[lo-lag:hi-lag];out.append(col*rotation)
 return np.stack(out+[np.ones(n)],axis=1)

def native_decode(z,starts,freq,h,bits):
 z=checked(z);starts=np.ascontiguousarray(starts,np.int32);h=np.ascontiguousarray(h,np.complex64);bits=np.ascontiguousarray(bits,np.uint8)
 if starts.shape!=(2,) or h.shape!=(2,3) or bits.shape!=(2,112) or np.any(starts<2) or np.any(starts+482>len(z)) or not np.isfinite(h).all():raise ValueError('Invalid joint-channel inputs')
 rot=np.ascontiguousarray(np.exp(2j*np.pi*np.asarray(freq)[:,None]*(np.arange(len(z))[None,:]-starts[:,None])/4e6),np.complex64);l=np.empty((2,112),np.float32)
 if library().joint_channel_decode(z.view(np.float32),len(z),starts,rot.view(np.float32),h.view(np.float32),bits,2,l):raise ValueError('Invalid native channel decode')
 return l

def estimate(z,starts,rounds=2,taps=3):
 z=checked(z);starts=np.asarray(starts,np.int32)
 if starts.shape!=(2,) or np.any(starts<2) or np.any(starts+482>len(z)) or rounds not in (1,2) or taps not in (1,3):raise ValueError('Invalid estimator bounds')
 initial=native_windows(z,starts.astype(np.int64));bits=initial[0]>0;positions=np.flatnonzero(PREAMBLE);grid=np.arange(-100000,100001,5000);rot=np.exp(-2j*np.pi*grid[:,None]*positions/4e6);windows=z[starts[:,None]+np.arange(480)];coarse=grid[np.argmax(abs(windows[:,positions]@rot.T)**2,axis=1)];freq=np.where(np.isfinite(initial[3]),initial[3],coarse).astype(float)
 # Hold out full groups, with a one-sample guard for the channel response.
 time=np.arange(len(z));test=(time%40>=28)&(time%40<36);fit=~(np.convolve(test.astype(int),np.ones(3,int),mode='same')>0);normal=max(float(np.mean(abs(z)**2)),1e-12)
 def solve(b,f):
  a=columns(b,starts,f,len(z),taps);x=a[fit];gram=x.conj().T@x;reg=1e-3*max(float(np.trace(gram).real)/len(gram),1e-9);coef=np.linalg.solve(gram+reg*np.eye(len(gram)),x.conj().T@z[fit]);res=z-a@coef;score=float(np.mean(abs(res[fit])**2));return score,a,coef,res
 seed_score,_,_,seed_res=solve(bits,freq);history=[]
 for iteration in range(rounds):
  # Fixed frequency trust region, two coordinate sweeps at each iteration.
  # No CRC or reference payload is consulted when choosing an estimator.
  for step in (5000.,1250.):
   for source in range(2):
    options=[]
    for shift in (-2,-1,0,1,2):
     f=freq.copy();f[source]=np.clip(f[source]+shift*step,-120000,120000);score,_,_,_=solve(bits,f);options.append((score,abs(shift),shift,f))
    freq=min(options,key=lambda q:q[:3])[-1]
  score,a,coef,res=solve(bits,freq);h=np.zeros((2,3),np.complex64)
  if taps==3:h[:]=coef[:-1].reshape(2,3)
  else:h[:,1]=coef[:-1]
  logits=native_decode(z-coef[-1],starts,freq,h,bits);bits=logits>0;history.append(dict(frequency_hz=freq.tolist(),fit_ratio=score/normal))
 score,a,coef,res=solve(bits,freq);held=float(np.mean(abs(res[test])**2))/normal;train=score/normal;condition=float(np.linalg.cond(a[fit].conj().T@a[fit]+1e-6*np.eye(a.shape[1])))
 accepted=bool(train<.65 and held<.85 and condition<1e6)
 return logits,dict(accepted=accepted,fit_ratio=train,heldout_ratio=held,seed_fit_ratio=seed_score/normal,condition=condition,frequencies_hz=freq.tolist(),history=history,rounds=rounds,taps=taps)
