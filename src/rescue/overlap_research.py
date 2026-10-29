"""Bounded offline overlap algorithms. No receiver/service/feeder imports."""
import ctypes as C
from pathlib import Path
import numpy as np
from .dsp import PREAMBLE,payloads,crc_batch
from .coherent_fast import native_windows
_LIB=None

def lib():
 global _LIB
 if _LIB is None:
  _LIB=C.CDLL(str(Path(__file__).with_name('_overlap_research.so')))
  arr=lambda dtype:np.ctypeslib.ndpointer(dtype=dtype,flags='C_CONTIGUOUS')
  _LIB.overlap_project.argtypes=[arr(np.float32),C.c_int,arr(np.float64),C.c_int,arr(np.float32)];_LIB.overlap_project.restype=C.c_int
  _LIB.overlap_joint.argtypes=[arr(np.float32),C.c_int,arr(np.int32),arr(np.float32),arr(np.uint8),C.c_int,arr(np.float32)];_LIB.overlap_joint.restype=C.c_int
 return _LIB

def checked(z):
 z=np.ascontiguousarray(z,np.complex64)
 if z.ndim!=1 or not 480<=len(z)<=1600 or not np.isfinite(z).all():raise ValueError('Expected finite bounded RF')
 return z

def project(z,mode='widely_linear'):
 z=checked(z)
 # Track the desired carrier before a fixed short filter; without this,
 # a valid +/-100 kHz packet rotates many times across its payload.
 estimate=native_windows(z,np.array([0],np.int64));frequency=float(estimate[3][0])
 if not np.isfinite(frequency):
  positions=np.flatnonzero(PREAMBLE);grid=np.arange(-100000,100001,5000)
  frequency=float(grid[np.argmax(abs(np.exp(-2j*np.pi*grid[:,None]*positions/4e6)@z[positions])**2)])
 z=np.ascontiguousarray(z*np.exp(-2j*np.pi*frequency*np.arange(len(z))/4e6),np.complex64)
 p=PREAMBLE.astype(float);a=np.stack((z[:32],np.r_[0,z[:31]]),axis=1)
 # Entire final preamble pulse and its local background are held out.
 fit=np.arange(32)<14;test=(np.arange(32)>=14)&(np.arange(32)<24)
 if mode=='widely_linear':design=np.c_[a.real,a.imag,np.ones(32)]
 elif mode=='complex_linear':design=np.c_[a,np.ones(32)]
 else:raise ValueError('Unknown projection')
 x=design[fit];scale=max(float(np.mean(abs(x)**2)),1e-8);reg=.1*scale*np.eye(x.shape[1]);reg[-1,-1]*=.01
 gram=x.conj().T@x+reg;condition=float(np.linalg.cond(gram));w=np.linalg.solve(gram,x.conj().T@p[fit]);pred=(design@w).real
 error=float(np.mean((pred[test]-p[test])**2)/max(np.mean(p[test]**2),1e-8))
 if condition>1e6 or error>.8:return None,dict(reason='fit_rejected',condition=condition,heldout_error=error)
 if mode=='widely_linear':weights=np.array([w[0],w[2],w[1],w[3],w[4]],np.float64)
 else:weights=np.array([w[0].real,-w[0].imag,w[1].real,-w[1].imag,w[2].real],np.float64)
 out=np.empty(len(z),np.float32)
 if lib().overlap_project(z.view(np.float32),len(z),weights,0,out):raise ValueError('Native projection bounds')
 v=out[32:480].reshape(112,4);l=v[:,:2].sum(1)-v[:,2:].sum(1);c=abs(l)/(abs(v).sum(1)+1e-8)
 return (l,c),dict(reason='accepted',condition=condition,heldout_error=error)

def joint(z,starts,iterations=2,carriers=None):
 z=checked(z);starts=np.ascontiguousarray(starts,np.int32)
 if starts.shape!=(2,) or np.any(starts<0) or np.any(starts+480>len(z)) or iterations not in (1,2,3):raise ValueError('Invalid pair bounds')
 windows=z[starts[:,None]+np.arange(480)];initial=native_windows(z,starts.astype(np.int64));bits=np.ascontiguousarray(initial[0]>0,np.uint8)
 if carriers is None:
  positions=np.flatnonzero(PREAMBLE);f=np.arange(-100000,100001,5000);rot=np.exp(-2j*np.pi*f[:,None]*positions/4e6)
  selected=np.argmax(abs(windows[:,positions]@rot.T)**2,axis=1);freq=f[selected];h=(windows[:,positions]*np.exp(-2j*np.pi*freq[:,None]*positions/4e6)).mean(1)
  carriers=h[:,None]*np.exp(2j*np.pi*freq[:,None]*np.arange(480)/4e6)
 carriers=np.ascontiguousarray(carriers,np.complex64)
 if carriers.shape!=(2,480) or not np.isfinite(carriers).all():raise ValueError('Invalid carriers')
 l=np.empty((2,112),np.float32)
 if lib().overlap_joint(z.view(np.float32),len(z),starts,carriers.view(np.float32),bits,iterations,l):raise ValueError('Native pair bounds')
 return l

def raw_valid(logits):
 rows=payloads(np.atleast_2d(logits));valid=(crc_batch(rows)==0)&(rows[:,0]>>3==17)
 return rows,valid
